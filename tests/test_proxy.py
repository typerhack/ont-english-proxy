"""
Offline tests for ont-english-proxy. No modem needed: a fake modem with synthetic data runs on 127.0.0.1.

    python3 -m unittest discover -s tests

All data here is invented (see AGENTS.md, RULE 1: never put real device data in tests).
"""
import http.client
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ont_english_proxy as proxy  # noqa: E402


def esc(text):
    """JS-escape every character as \\uXXXX (built programmatically to keep this file plain)."""
    return "".join("\\" + "u" + format(ord(c), "04x") for c in text)


FAKE_FILES = {
    "/frameaspdes/english/ssmpdes.js": "﻿var framedesinfo = {\n\tframe001: \"User Name\"\n};\n",
    "/frameaspdes/chinese/ssmpdes.js": "﻿var framedesinfo = {\n\tframe001: \"用户名\",\n\tframe999: \"告警\"\n};\n"
                                       "var OnlyChineseDes = {\n\tk1: \"已连接\"\n};\n",
    "/Cuscss/english/frame.css": "body{color:#000}",
    "/index.asp": "<script>var curLanguage = 'chinese';</script><p>已连接</p>",
    "/asp/getMenuArray.asp": '[{ name: "首页", id: "MainPage" }, { name: "首页设置", id: "X" }]',
    "/log.asp": "<script>var log = \"[" + esc("告警日志") + "]\";</script>",
}


class FakeModem(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    seen = []

    def _send(self, status, body, ctype="text/html"):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        FakeModem.seen.append(self.path)
        path = self.path.split("?")[0]
        if path in FAKE_FILES:
            ctype = "text/css" if path.endswith(".css") else "application/javascript" if path.endswith(".js") else "text/html"
            self._send(200, FAKE_FILES[path], ctype)
        else:
            self._send(404, "not found")

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
        self._send(200, json.dumps({"body": body, "cookie": self.headers.get("Cookie"),
                                    "host": self.headers.get("Host")}), "application/octet-stream")

    def log_message(self, *a):
        pass


class ProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modem = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeModem)
        threading.Thread(target=cls.modem.serve_forever, daemon=True).start()
        proxy.Config.upstream_host, proxy.Config.upstream_port = "127.0.0.1", cls.modem.server_address[1]

        cls.tmp = tempfile.mkdtemp()
        proxy.Config.translations_path = os.path.join(cls.tmp, "translations.json")
        with open(proxy.Config.translations_path, "w", encoding="utf-8") as f:
            json.dump({"menu": {"首页": "Home"}, "replace": {"已连接": "Connected", "告警日志": "Alarm Log"},
                       "dictionaries": {"framedesinfo": {"frame999": "Alarm"}}}, f, ensure_ascii=False)
        proxy.Config._mtime = None
        proxy.Config.reload_translations()

        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), proxy.Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.modem.shutdown()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        conn.close()
        return resp, data

    # --- unit -----------------------------------------------------------
    def test_rewrite_path(self):
        self.assertEqual(proxy.rewrite_path("/resource/chinese/a.html?x=/chinese/"),
                         "/resource/english/a.html?x=/chinese/")

    def test_only_cjk_escapes_are_decoded(self):
        h = proxy.Handler.__new__(proxy.Handler)
        h.headers = {"Host": "127.0.0.1:1"}
        src = (esc("告警") + " " + esc("é") + " " + "\\" + esc("告")).encode()
        out = h._rewrite_text(src).decode()
        self.assertTrue(out.startswith("告警 "))           # CJK escapes decoded
        self.assertIn(esc("é"), out)                       # non-CJK escape untouched
        self.assertIn("\\" + esc("告"), out)                # escaped backslash untouched

    # --- end to end through the proxy -------------------------------------
    def test_css_path_rewritten_to_english(self):
        resp, data = self.request("GET", "/Cuscss/chinese/frame.css?123")
        self.assertEqual(resp.status, 200)
        self.assertEqual(data, FAKE_FILES["/Cuscss/english/frame.css"])
        self.assertEqual(resp.getheader("Cache-Control"), "no-store")

    def test_page_language_and_replacements(self):
        _, data = self.request("GET", "/index.asp")
        self.assertIn("curLanguage = 'english'", data)
        self.assertIn("<p>Connected</p>", data)

    def test_menu_exact_match_only(self):
        _, data = self.request("GET", "/asp/getMenuArray.asp")
        self.assertIn('"Home"', data)
        self.assertIn('"首页设置"', data)  # not an exact name: left alone

    def test_escaped_log_text_translated(self):
        _, data = self.request("GET", "/log.asp")
        self.assertIn("[Alarm Log]", data)

    def test_post_passes_through_unchanged(self):
        resp, data = self.request("POST", "/set.cgi?x=1", body="a=1&x.X_HW_Token=abc",
                                  headers={"Cookie": "Cookie=body:Language:chinese:id=-1",
                                           "Content-Type": "application/x-www-form-urlencoded"})
        echo = json.loads(data)
        self.assertEqual(echo["body"], "a=1&x.X_HW_Token=abc")
        self.assertEqual(echo["cookie"], "Cookie=body:Language:chinese:id=-1")
        self.assertEqual(echo["host"], "127.0.0.1:%d" % self.modem.server_address[1])

    def test_dictionary_fallback(self):
        _, data = self.request("GET", "/frameaspdes/chinese/ssmpdes.js")
        self.assertIn('"User Name"', data)
        self.assertIn("ont-english-proxy: fill missing English keys", data)
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed: JS execution check skipped")
        script = ("const vm=require('vm');const c={};c.window=c;vm.createContext(c);"
                  "vm.runInContext(require('fs').readFileSync(0,'utf8'),c);"
                  "console.log(JSON.stringify([c.framedesinfo,c.OnlyChineseDes]));")
        out = subprocess.run([node, "-e", script], input=data, capture_output=True, text=True, check=True).stdout
        fd, only_zh = json.loads(out)
        self.assertEqual(fd["frame001"], "User Name")   # English kept
        self.assertEqual(fd["frame999"], "Alarm")       # translations.json override
        self.assertEqual(only_zh["k1"], "Connected")    # missing object filled from Chinese, then replaced


class LifecycleTests(unittest.TestCase):
    """start / status / stop as separate processes, like a user would run them."""

    SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ont_english_proxy.py")

    @classmethod
    def setUpClass(cls):
        cls.modem = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeModem)
        threading.Thread(target=cls.modem.serve_forever, daemon=True).start()
        cls.home = tempfile.mkdtemp()
        with socket_free_port() as port:
            cls.port = port

    @classmethod
    def tearDownClass(cls):
        cls.cli("stop")
        cls.modem.shutdown()
        shutil.rmtree(cls.home, ignore_errors=True)

    @classmethod
    def cli(cls, *args):
        env = dict(os.environ, ONT_ENGLISH_PROXY_HOME=cls.home)
        cmd = [sys.executable, cls.SCRIPT, *args, "--port", str(cls.port),
               "--upstream", "127.0.0.1:%d" % cls.modem.server_address[1]]
        return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)

    def test_lifecycle(self):
        r = self.cli("status")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("not running", r.stdout)

        r = self.cli("start", "--no-open")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("started", r.stdout)

        r = self.cli("start", "--no-open")                 # second start: no duplicate
        self.assertIn("already running", r.stdout)

        r = self.cli("status")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("http://127.0.0.1:%d" % self.port, r.stdout)

        # the background proxy really proxies and translates
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("GET", "/index.asp")
        self.assertIn("curLanguage = 'english'", conn.getresponse().read().decode("utf-8"))
        conn.close()

        r = self.cli("stop")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("stopped", r.stdout)
        self.assertEqual(self.cli("status").returncode, 1)
        self.assertFalse(os.path.exists(os.path.join(self.home, "state.json")))


class socket_free_port:
    def __enter__(self):
        import socket
        self.s = socket.socket()
        self.s.bind(("127.0.0.1", 0))
        return self.s.getsockname()[1]

    def __exit__(self, *exc):
        self.s.close()


if __name__ == "__main__":
    unittest.main()
