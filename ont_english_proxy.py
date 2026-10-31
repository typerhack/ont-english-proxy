#!/usr/bin/env python3
"""
ont-english-proxy — serve a Huawei ONT web UI (China firmware) in English.

A small reverse proxy on localhost. Standard library only, no dependencies.

    python3 ont_english_proxy.py --open     # foreground, Ctrl+C stops; http://127.0.0.1:8181
    python3 ont_english_proxy.py start      # background (opens the browser)
    python3 ont_english_proxy.py status
    python3 ont_english_proxy.py stop
    python3 ont_english_proxy.py --port 9000 --upstream 192.168.100.1

What it does:
  1. Requests for  /…/chinese/…  are sent to the modem as  /…/english/…
     (the device ships full English dictionaries and CSS).
  2. HTML/JS responses: curLanguage = 'chinese'  ->  'english'.
  3. English dictionary files get a fallback appended: any key (or whole object)
     missing in English is filled from the Chinese file, so nothing renders blank.
     Your own translations in translations.json ("dictionaries") win over both.
  4. Hardcoded Chinese strings in pages are replaced via translations.json ("replace").
  5. Everything else passes through untouched: cookies, tokens, POST bodies.

Note: the session cookie is per-host, so log in through the proxy
(log out of the direct 192.168.100.1 tab first — the modem allows one admin session).
"""
import argparse
import http.client
import http.server
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.realpath(__file__))
VERSION = "1.1.0"
STATUS_PATH = "/__ont-english-proxy__/status"  # answered locally, never forwarded

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "content-length",
}

# Dictionary files whose English copy gets the Chinese fallback merged in.
DICT_PATH = re.compile(r"^/(?:frameaspdes|resource)/english/[^/?]+\.(?:js|html)$", re.I)
CUR_LANG = re.compile(rb"""\b((?:cur|current)Lang(?:uage)?\s*=\s*)(['"])chinese\2""", re.I)
VAR_DECL = re.compile(r"\bvar\s+([A-Za-z_$][\w$]*)\s*=")

JS_CJK_ESCAPE = re.compile(rb"(?<!\\)\\u(3[0-9a-fA-F]{3}|[4-9][0-9a-fA-F]{3}|[fF][fF][0-9a-fA-F]{2})")


def _unescape_cjk(m):
    cp = int(m.group(1), 16)
    if 0x3000 <= cp <= 0x303F or 0x4E00 <= cp <= 0x9FFF or 0xFF00 <= cp <= 0xFFEF:
        return chr(cp).encode("utf-8")
    return m.group(0)


TEXT_TYPES = ("text/html", "javascript", "text/css", "text/plain", "application/json")


class Config:
    upstream_host = "192.168.100.1"
    upstream_port = 80
    timeout = 30
    verbose = False
    translations_path = os.path.join(HERE, "translations.json")
    dict_overrides: dict = {}
    replace_pairs: list = []
    quoted_pairs: list = []
    _mtime = None
    _lock = threading.Lock()

    @classmethod
    def reload_translations(cls):
        """Re-read translations.json when it changes (edit it while the proxy runs)."""
        try:
            mtime = os.path.getmtime(cls.translations_path)
        except OSError:
            return
        with cls._lock:
            if mtime == cls._mtime:
                return
            try:
                with open(cls.translations_path, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError) as e:
                print(f"[ont-english-proxy] translations.json not loaded: {e}", file=sys.stderr)
                return
            cls.dict_overrides = {k: v for k, v in (data.get("dictionaries", {}) or {}).items()
                                  if isinstance(v, dict)}
            repl = {k: v for k, v in (data.get("replace", {}) or {}).items() if not k.startswith("_")}
            # longest first so "未连接" wins over "连接"
            cls.replace_pairs = sorted(
                ((k.encode("utf-8"), v.encode("utf-8")) for k, v in repl.items()),
                key=lambda kv: -len(kv[0]),
            )
            menu = {k: v for k, v in (data.get("menu", {}) or {}).items() if not k.startswith("_")}
            # exact whole-string matches inside quotes: "首页" -> "Home" (menu array, titles)
            cls.quoted_pairs = [(q + k.encode("utf-8") + q, q + v.encode("utf-8") + q)
                                for k, v in menu.items() for q in (b'"', b"'")]
            cls._mtime = mtime
            print(f"[ont-english-proxy] translations loaded: {len(menu)} menu names, {len(repl)} replacements, "
                  f"{sum(len(v) for v in cls.dict_overrides.values())} dictionary overrides")


def rewrite_path(path: str) -> str:
    base, sep, query = path.partition("?")
    return base.replace("/chinese/", "/english/") + sep + query


def build_fallback_js(zh_text: str, en_text: str, overrides: dict) -> str:
    """JS appended to an English dictionary: fill gaps from Chinese, then apply overrides."""
    zh_names = list(dict.fromkeys(VAR_DECL.findall(zh_text)))
    names = set(zh_names) | set(VAR_DECL.findall(en_text))
    ov = {n: v for n, v in overrides.items() if n in names}
    ret = ",".join(f"{json.dumps(n)}:(typeof {n}!=='undefined'?{n}:undefined)" for n in zh_names)
    return (
        "\n;/* ont-english-proxy: fill missing English keys from Chinese, then apply translations.json */\n"
        "(function(){try{\n"
        "var zh=(function(){\n" + zh_text + "\n;return {" + ret + "};})();\n"
        "var ov=" + json.dumps(ov, ensure_ascii=False) + ";\n"
        "var n,k,z,e;\n"
        "for(n in zh){z=zh[n];if(z==null)continue;e=window[n];"
        "if(typeof e==='undefined'||e===null){window[n]=z;continue;}"
        "if(typeof z==='object'&&typeof e==='object'){for(k in z){if(!(k in e))e[k]=z[k];}}}\n"
        "for(n in ov){if(typeof window[n]!=='object'||!window[n])window[n]={};"
        "for(k in ov[n])window[n][k]=ov[n][k];}\n"
        "}catch(x){if(window.console)console.warn('ont-english-proxy: merge failed',x);}})();\n"
    )


def looks_like_js_dict(body: bytes) -> bool:
    head = body[:2048].lstrip(b"\xef\xbb\xbf \t\r\n")
    return b"<html" not in body[:2048].lower() and (head.startswith(b"var") or b"var " in head)


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ont-english-proxy"

    # ---- plumbing -------------------------------------------------------
    def _proxy_origin(self) -> str:
        return f"http://{self.headers.get('Host') or '127.0.0.1'}"

    def _upstream_origin(self) -> str:
        c = Config
        return f"http://{c.upstream_host}" + ("" if c.upstream_port == 80 else f":{c.upstream_port}")

    def _upstream_headers(self) -> dict:
        h = {}
        proxy_o, up_o = self._proxy_origin(), self._upstream_origin()
        for k, v in self.headers.items():
            lk = k.lower()
            # drop conditional headers: the browser must never reuse a copy translated by an older rule set
            if lk in HOP_BY_HOP or lk in ("host", "accept-encoding", "if-modified-since", "if-none-match") \
                    or lk.startswith("proxy-"):
                continue
            if lk in ("referer", "origin"):
                v = v.replace(proxy_o, up_o)
                if lk == "referer":
                    v = rewrite_path_in_url(v)
            h[k] = v
        h["Host"] = Config.upstream_host + ("" if Config.upstream_port == 80 else f":{Config.upstream_port}")
        h["Accept-Encoding"] = "identity"
        return h

    def _fetch(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection(Config.upstream_host, Config.upstream_port, timeout=Config.timeout)
        try:
            conn.request(method, path, body=body, headers=headers or self._upstream_headers())
            resp = conn.getresponse()
            data = resp.read() if method != "HEAD" else b""
            return resp.status, resp.reason, resp.getheaders(), data
        finally:
            conn.close()

    def _send_local(self, status, text, ctype="text/plain; charset=utf-8"):
        msg = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(msg)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(msg)

    def _handle(self):
        if self.path == STATUS_PATH and self.command == "GET":
            # Answered by the proxy itself (never reaches the modem): used by `status` / `stop`.
            info = {"app": "ont-english-proxy", "version": VERSION, "pid": os.getpid(),
                    "upstream": self._upstream_origin()}
            self._send_local(200, json.dumps(info), "application/json")
            return
        Config.reload_translations()
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        up_path = rewrite_path(self.path)
        try:
            status, reason, headers, data = self._fetch(self.command, up_path, body)
        except OSError as e:
            self._send_local(502, f"ont-english-proxy: modem unreachable ({e})")
            return

        ctype = next((v for k, v in headers if k.lower() == "content-type"), "").lower()
        base_path = up_path.split("?", 1)[0]

        if self.command == "GET" and status == 200 and DICT_PATH.match(base_path) and looks_like_js_dict(data):
            data = self._with_fallback(base_path, data)
        elif data and (any(t in ctype for t in TEXT_TYPES) or base_path.lower().endswith((".asp", ".js"))):
            data = self._rewrite_text(data)

        self.send_response(status, reason)
        for k, v in headers:
            lk = k.lower()
            if lk in HOP_BY_HOP:
                continue
            if lk in ("cache-control", "expires", "pragma", "etag", "last-modified"):
                continue
            if lk == "location":
                v = v.replace(self._upstream_origin(), self._proxy_origin())
            self.send_header(k, v)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _with_fallback(self, en_path: str, en_body: bytes) -> bytes:
        zh_path = en_path.replace("/english/", "/chinese/")
        try:
            status, _, _, zh_body = self._fetch("GET", zh_path)
        except OSError:
            return en_body
        if status != 200 or not looks_like_js_dict(zh_body):
            return en_body
        zh_text = zh_body.decode("utf-8-sig", errors="replace")
        en_text = en_body.decode("utf-8-sig", errors="replace")
        js = build_fallback_js(zh_text, en_text, Config.dict_overrides)
        return self._rewrite_text(en_body + js.encode("utf-8"))

    def _rewrite_text(self, data: bytes) -> bytes:
        # Logs etc. arrive as JS escapes (\u544a\u8b66). Turn only CJK escapes into real
        # characters so the replace rules can match them; they are safe inside JS strings.
        data = JS_CJK_ESCAPE.sub(_unescape_cjk, data)
        data = CUR_LANG.sub(rb"\1\2english\2", data)
        data = data.replace(self._upstream_origin().encode(), self._proxy_origin().encode())
        for old, new in Config.quoted_pairs:
            data = data.replace(old, new)
        for old, new in Config.replace_pairs:
            data = data.replace(old, new)
        return data

    do_GET = do_POST = do_HEAD = do_PUT = do_DELETE = do_OPTIONS = _handle

    def log_message(self, fmt, *args):
        # Never log query strings / cookies (they can carry tokens).
        line = fmt % args
        if not Config.verbose:
            line = re.sub(r"\?[^ ]*", "?…", line)
        sys.stderr.write(f"[ont-english-proxy] {line}\n")


def rewrite_path_in_url(url: str) -> str:
    m = re.match(r"^(https?://[^/]+)(/.*)?$", url)
    if not m:
        return url
    return m.group(1) + rewrite_path(m.group(2) or "/")


# ---- start / stop / status -------------------------------------------------
# State lives in ~/.ont-english-proxy/ (override with ONT_ENGLISH_PROXY_HOME): state.json + proxy.log.

def state_dir():
    return os.environ.get("ONT_ENGLISH_PROXY_HOME") or os.path.join(os.path.expanduser("~"), ".ont-english-proxy")


def _state_path():
    return os.path.join(state_dir(), "state.json")


def log_path():
    return os.path.join(state_dir(), "proxy.log")


def read_state():
    try:
        with open(_state_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_state(state):
    os.makedirs(state_dir(), exist_ok=True)
    tmp = _state_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, _state_path())


def remove_state(only_pid=None):
    st = read_state()
    if st is None or (only_pid is not None and st.get("pid") != only_pid):
        return
    try:
        os.remove(_state_path())
    except OSError:
        pass


def probe(host, port, timeout=1.0):
    """Ask a running proxy who it is (handled locally, never forwarded to the modem)."""
    try:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.request("GET", STATUS_PATH)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        if resp.status == 200:
            info = json.loads(data.decode("utf-8"))
            if info.get("app") == "ont-english-proxy":
                return info
    except (OSError, ValueError):
        pass
    return None


def _local_host(listen):
    return "127.0.0.1" if listen in ("0.0.0.0", "", "::") else listen


def find_running(a):
    """Running instance from the state file, else one on the requested port. None if not running."""
    st = read_state()
    if st:
        info = probe(st["host"], st["port"])
        if info and info.get("pid") == st.get("pid"):
            return dict(st, **info)
        remove_state()  # stale
    host = _local_host(a.listen)
    info = probe(host, a.port)
    if info:
        return dict(info, host=host, port=a.port, url=f"http://{host}:{a.port}")
    return None


def _open_browser(url):
    import webbrowser
    webbrowser.open(url)


def cmd_run(a):
    host, _, port = a.upstream.partition(":")
    Config.upstream_host, Config.upstream_port = host, int(port or 80)
    Config.translations_path = a.translations
    Config.verbose = a.verbose
    Config.reload_translations()

    try:
        srv = http.server.ThreadingHTTPServer((a.listen, a.port), Handler)
    except OSError as e:
        print(f"[ont-english-proxy] cannot listen on {a.listen}:{a.port} ({e}). "
              f"Is it already running? Check with: status   (or use another port: --port 9000)", file=sys.stderr)
        return 1
    srv.daemon_threads = True
    url = f"http://{_local_host(a.listen)}:{a.port}"
    write_state({"pid": os.getpid(), "host": _local_host(a.listen), "port": a.port, "url": url,
                 "upstream": a.upstream, "log": log_path(), "started": int(time.time())})
    print(f"[ont-english-proxy] {url}  ->  http://{a.upstream}   (Ctrl+C to stop)")
    if a.open:
        _open_browser(url)

    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # `stop` -> clean exit, state removed
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        remove_state(only_pid=os.getpid())
    return 0


def cmd_start(a):
    running = find_running(a)
    if running:
        print(f"ont-english-proxy is already running: {running['url']}  (pid {running['pid']})")
        if not a.no_open:
            _open_browser(running["url"])
        return 0

    os.makedirs(state_dir(), exist_ok=True)
    mode = "wb" if os.path.exists(log_path()) and os.path.getsize(log_path()) > 1_000_000 else "ab"
    log = open(log_path(), mode)
    args = [sys.executable, os.path.realpath(__file__), "run", "--listen", a.listen, "--port", str(a.port),
            "--upstream", a.upstream, "--translations", a.translations] + (["-v"] if a.verbose else [])
    kw = {"stdin": subprocess.DEVNULL, "stdout": log, "stderr": subprocess.STDOUT, "close_fds": True,
          "cwd": state_dir()}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0x8) | \
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
    else:
        kw["start_new_session"] = True
    child = subprocess.Popen(args, **kw)
    log.close()

    host = _local_host(a.listen)
    for _ in range(100):  # up to ~10 s
        info = probe(host, a.port, timeout=0.5)
        if info and info.get("pid") == child.pid:
            url = f"http://{host}:{a.port}"
            print(f"ont-english-proxy started: {url}  ->  http://{a.upstream}")
            print(f"  commands: status | stop      log: {log_path()}")
            if not a.no_open:
                _open_browser(url)
            return 0
        if child.poll() is not None:
            break
        time.sleep(0.1)

    print("ont-english-proxy failed to start. Last log lines:", file=sys.stderr)
    try:
        with open(log_path(), encoding="utf-8", errors="replace") as f:
            for line in f.readlines()[-5:]:
                print("  " + line.rstrip(), file=sys.stderr)
    except OSError:
        pass
    if child.poll() is None:
        child.terminate()
    return 1


def cmd_stop(a):
    running = find_running(a)
    if not running:
        print("ont-english-proxy is not running")
        remove_state()
        return 0
    pid = running["pid"]
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as e:
        print(f"could not stop pid {pid}: {e}", file=sys.stderr)
        return 1
    for _ in range(50):
        if not probe(running["host"], running["port"], timeout=0.3):
            break
        time.sleep(0.1)
    else:
        if hasattr(signal, "SIGKILL"):
            os.kill(pid, signal.SIGKILL)
    remove_state()
    print(f"ont-english-proxy stopped (was {running['url']}, pid {pid})")
    return 0


def cmd_status(a):
    running = find_running(a)
    if not running:
        print("ont-english-proxy is not running")
        return 1
    print(f"ont-english-proxy is running")
    print(f"  url:      {running['url']}")
    print(f"  modem:    {running.get('upstream')}")
    print(f"  pid:      {running['pid']}")
    if running.get("started"):
        mins = int((time.time() - running["started"]) // 60)
        print(f"  uptime:   {mins // 60}h {mins % 60}m")
    print(f"  log:      {running.get('log') or log_path()}")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Serve a Huawei ONT web UI in English (local reverse proxy).",
        epilog="commands: run (default, foreground; Ctrl+C stops) | start (background) | stop | status")
    ap.add_argument("command", nargs="?", default="run", choices=["run", "start", "stop", "status"],
                    help="what to do (default: run in the foreground)")
    ap.add_argument("--listen", default="127.0.0.1", help="address to listen on (default 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8181, help="port to listen on (default 8181)")
    ap.add_argument("--upstream", default="192.168.100.1", help="modem host[:port] (default 192.168.100.1)")
    ap.add_argument("--translations", default=Config.translations_path, help="path to translations.json")
    ap.add_argument("-v", "--verbose", action="store_true", help="log full request lines")
    ap.add_argument("--open", action="store_true", help="run: open the proxied UI in the default browser")
    ap.add_argument("--no-open", action="store_true", help="start: don't open the browser")
    a = ap.parse_args()
    a.translations = os.path.abspath(a.translations)

    # Windows consoles may not encode every character; never crash on logging. Flush per line.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace", line_buffering=True)
        except (AttributeError, ValueError):
            pass

    return {"run": cmd_run, "start": cmd_start, "stop": cmd_stop, "status": cmd_status}[a.command](a)


if __name__ == "__main__":
    sys.exit(main())
