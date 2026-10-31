#!/usr/bin/env python3
"""
Privacy check: fail if files that would be committed contain personal or device-identifying data.

    python3 tools/privacy_check.py          # check all tracked + new (non-ignored) files

Runs automatically as a git pre-commit hook after:  git config core.hooksPath .githooks
See AGENTS.md, "RULE 1: Privacy". Use placeholders instead of real values:
HWTC00000000, 00:00:00:00:00:00, 192.0.2.10 (documentation IP range), user@example.com.
"""
import ipaddress
import os
import re
import subprocess
import sys

MAX_BYTES = 1_000_000

# Files that must never be committed (device captures, Huawei UI files, secrets).
FORBIDDEN_EXT = {".asp", ".cus", ".har", ".pcap", ".pcapng", ".cookie", ".cookies", ".jar", ".bin", ".cfg"}
FORBIDDEN_DIRS = ("resources/", "pages/", "captures/", "dumps/")
FORBIDDEN_NAMES = {".cookie", "HANDOFF.md", "FINDINGS.md"}

# Generic factory defaults / loopback: shared by millions of devices, not personal.
ALLOWED_IPS = {"192.168.100.1", "192.168.1.1", "192.168.0.1", "127.0.0.1", "0.0.0.0"}
DOC_NETS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]

IPV4 = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?![\w.])")
MAC = re.compile(r"(?<![\w:-])([0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5})(?![\w:-])")
HW_SERIAL = re.compile(r"(?:HWTC|48575443)([0-9A-Fa-f]{8})")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
HOME_PATH = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\\\?Users\\\\?)([A-Za-z0-9._-]+)")
LONG_HEX = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{32,}(?![0-9A-Fa-f])")
COOKIE = re.compile(r"Cookie=body:[^\s\"']*id=(?!-1\b)[0-9A-Za-z]+")

ALLOWED_EMAIL_DOMAINS = ("example.com", "example.org", "example.net", "users.noreply.github.com")
ALLOWED_HOME_NAMES = {"name", "user", "username", "you", "runner"}


def files_to_check():
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                             capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        sys.exit("privacy check: run this inside the git repository")
    return [p for p in out.decode("utf-8", "replace").split("\0") if p and os.path.isfile(p)]


def ip_ok(ip):
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # not an IP (e.g. a version number like 1.2.300.4)
    if ip in ALLOWED_IPS or ip.startswith("255.") or any(addr in n for n in DOC_NETS):
        return True
    return False


def scan_text(text):
    for n, line in enumerate(text.splitlines(), 1):
        for m in IPV4.finditer(line):
            if not ip_ok(m.group(1)):
                yield n, f"IP address {m.group(1)} (use 192.0.2.x for examples)"
        for m in MAC.finditer(line):
            if set(re.sub(r"[:-]", "", m.group(1)).lower()) - {"0", "f"}:
                yield n, "MAC address (use 00:00:00:00:00:00)"
        for m in HW_SERIAL.finditer(line):
            if set(m.group(1)) != {"0"}:
                yield n, "Huawei serial / GPON SN (use HWTC00000000)"
        for m in EMAIL.finditer(line):
            if not m.group(0).lower().endswith(ALLOWED_EMAIL_DOMAINS):
                yield n, f"email address {m.group(0)}"
        for m in HOME_PATH.finditer(line):
            if m.group(1).lower() not in ALLOWED_HOME_NAMES:
                yield n, "path from a personal computer (home directory)"
        if LONG_HEX.search(line):
            yield n, "long hex string (token/session/serial?)"
        if COOKIE.search(line):
            yield n, "session cookie"


def main():
    problems = []
    for path in files_to_check():
        norm = path.replace("\\", "/")
        base = os.path.basename(norm)
        if norm.startswith("tools/privacy_check.py"):
            continue  # contains the patterns themselves
        if (os.path.splitext(base)[1].lower() in FORBIDDEN_EXT or base in FORBIDDEN_NAMES
                or norm.startswith(FORBIDDEN_DIRS)):
            problems.append((path, 0, "file type/location must never be committed (device data or Huawei files)"))
            continue
        if os.path.getsize(path) > MAX_BYTES:
            problems.append((path, 0, "file larger than 1 MB (device dump?)"))
            continue
        with open(path, "rb") as f:
            raw = f.read()
        if b"\0" in raw[:8192]:
            continue  # binary (images): review screenshots manually for personal data
        for n, why in scan_text(raw.decode("utf-8", "replace")):
            problems.append((path, n, why))

    email = os.environ.get("GIT_AUTHOR_EMAIL") or subprocess.run(
        ["git", "config", "user.email"], capture_output=True, text=True).stdout.strip()
    if email and not email.endswith("users.noreply.github.com"):
        print("privacy check: note: commits will publish your git email "
              f"({email[:2]}…@{email.split('@')[-1]}). Consider your GitHub noreply address:\n"
              "  git config user.email <id>+<username>@users.noreply.github.com", file=sys.stderr)

    if problems:
        print("privacy check FAILED — personal/device data must not be committed (see AGENTS.md):", file=sys.stderr)
        for path, n, why in problems:
            print(f"  {path}{':' + str(n) if n else ''}: {why}", file=sys.stderr)
        sys.exit(1)
    print("privacy check passed")


if __name__ == "__main__":
    main()
