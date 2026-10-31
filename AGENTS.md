# AGENTS.md

Instructions for AI coding agents (Claude Code, Codex, Cursor, Copilot, …) and human contributors
working on this repository or any fork of it.

## What this project is

`ont-english-proxy` is a local reverse proxy that shows the web UI of Huawei GPON ONTs with
China-region firmware in English. It runs on the user's own computer (`127.0.0.1:8181`), forwards
requests to the modem (default `192.168.100.1`) and rewrites only what the browser displays.

| File | Purpose |
|---|---|
| `ont_english_proxy.py` | The whole proxy: one file, Python standard library only |
| `translations.json` | `menu` (exact menu names), `replace` (text anywhere), `dictionaries` (missing dictionary keys) |
| `tests/test_proxy.py` | Offline unit tests with synthetic data, no modem needed |
| `tools/privacy_check.py` | Blocks commits that contain personal or device-identifying data |
| `.githooks/pre-commit` | Runs the privacy check before every commit |

## RULE 1: Privacy (strict, no exceptions)

This repository is public. **Nothing from a user's device, network or computer may ever be committed**:
not in code, tests, docs, translations, issues, commit messages or screenshots.

Never commit:

- Serial numbers, GPON/ONT SN (`HWTC…`, `48575443…`), MAC addresses, PON password, LOID, device IDs
- Public or private IP addresses other than generic defaults (`192.168.100.1`, `192.168.1.1`, `192.168.0.1`, `127.0.0.1`, `0.0.0.0`)
- Usernames, passwords, session cookies, tokens (`x.X_HW_Token`, `onttoken`), nonces, captured headers
- ISP or operator names tied to a specific user, account numbers, phone/VoIP numbers, SIP credentials
- Wi-Fi SSIDs or keys, names or hostnames of devices on the user's LAN
- Real log excerpts (logs contain IPs, MACs, times and serials); rewrite them as synthetic examples
- File paths or names from a user's computer (`/Users/<name>/`, `/home/<name>/`, `C:\Users\<name>\`)
- Email addresses or real names (beyond what a contributor chooses for their own git identity)
- Huawei's own files (`.asp`, `.cus`, dictionaries, CSS, images) copied from a device: they are
  copyrighted and may carry device-specific data. The proxy rewrites them at runtime; the repo never stores them.
- Raw captures: HAR files, pcaps, page dumps, cookies (`.gitignore` already blocks the common ones)

When you need example data, **invent it** (e.g. `HWTC00000000`, `00:00:00:00:00:00`, `192.0.2.10` from the
documentation range). A model name and firmware version (e.g. `EG8145X6`, `V5R020C00S080`) are fine:
thousands of identical units share them. They are not personal.

Before every commit, run:

```
python3 tools/privacy_check.py
```

It must pass. If it flags a false positive, change the content (use documentation IPs, placeholders),
don't weaken the check without a clear reason in the PR.

If you are an AI agent and a user pastes device output, logs or screenshots into the conversation,
use them only to derive **generic** rules (e.g. a Chinese phrase and its English translation). Never copy
identifiers from them into files.

## RULE 2: Never change the user's modem

The proxy must stay display-only. When working on it, agents must not:

- Click Apply/Save/Submit/Reboot/Restore/Upgrade or anything that changes settings
- Send POST requests to `set.cgi` or any other configuration endpoint
- Log out the user or open a second admin session (the modem allows only one)
- Try telnet/SSH, default credentials or any login on the user's behalf

Read-only GET requests through the user's own existing session are fine for investigating untranslated
pages. If unsure whether a request changes something, stop and ask the user.

The proxy itself must keep passing cookies, tokens and request bodies through **unchanged**.

## RULE 3: Keep it simple and portable

- Python **3.7+**, **standard library only**. No `pip install`, no third-party packages.
- Must work on **macOS, Linux and Windows**: use `os.path`, no shell calls, no POSIX-only APIs,
  console output must not crash on non-UTF-8 consoles.
- One proxy file. Listen on `127.0.0.1` by default; never default to `0.0.0.0`.
- Never log cookies, tokens or query strings by default.

## Translation conventions

- `menu` values: **20 characters max**, no `&` (the UI escapes it to `&amp;`), no quotes or backslashes.
- `replace` values must be safe inside JavaScript strings: no `"`, `'` or `\`.
- Prefer Huawei's own English wording (from English firmware) when known.
- Longer, more specific phrases are matched first, so add full phrases rather than single characters.
- Keys starting with `_` are comments.

## How to verify a change

```
python3 -m unittest discover -s tests      # offline tests, no modem needed
python3 tools/privacy_check.py             # must pass before committing
python3 ont_english_proxy.py --open        # manual check against a real modem (if you have one)
```

Turn off browser auto-translate when checking the UI manually.
