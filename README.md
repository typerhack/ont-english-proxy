**English** | [فارسی](README.fa.md)

# ont-english-proxy

**Use your Huawei fiber modem (GPON ONT) web interface in English, even with China-region firmware.**

Many Huawei ONTs (for example `EG8145X6`) sold or supplied with China firmware only show a Chinese web
interface. The firmware already contains English language files, but it forces Chinese and hides the
language switch. Your provider may not offer an update.

`ont-english-proxy` is a small program that runs on your own computer, sits between your browser and the
modem, and shows the same interface in English:

- **Nothing is changed on the modem.** No flashing, no settings changes, no firmware upgrade.
- **Nothing to install** except Python. One file, no extra packages.
- Works on **macOS, Linux and Windows**.
- The menu, settings pages and logs are translated. Anything still missing is easy to add.

```
Browser  ──►  http://127.0.0.1:8181  (ont-english-proxy on your computer)  ──►  http://192.168.100.1  (modem)
```

---

## Contents

1. [Is my modem supported?](#1-is-my-modem-supported)
2. [Install Python](#2-install-python)
3. [Download ont-english-proxy](#3-download-ont-english-proxy)
4. [Run it](#4-run-it)
5. [Stop it](#5-stop-it)
6. [Update to the latest version](#6-update-to-the-latest-version)
7. [Options](#7-options)
8. [Troubleshooting](#8-troubleshooting)
9. [Fixing remaining Chinese text](#9-fixing-remaining-chinese-text)
10. [Saving settings through the proxy](#10-saving-settings-through-the-proxy)
11. [How it works](#11-how-it-works)
12. [Contributing](#12-contributing)
13. [Privacy and security](#13-privacy-and-security)

---

## 1. Is my modem supported?

Tested:

| Model | Firmware | Result |
|---|---|---|
| EG8145X6 | V5R020C00S080 | Works: menu, settings pages, logs |

Likely to work: other Huawei ONTs whose login page is at `http://192.168.100.1` and looks like the
Huawei "EchoLife / OptiXstar" style interface. Quick check: with the modem login page open, visit
`http://192.168.100.1/frameaspdes/english/ssmpdes.js`. If you see English text, the English language
files are on your modem and the proxy should work.

Tried it on another model? Please [open an issue](#12-contributing) with the model and firmware version
(no serial numbers or screenshots with personal data, please).

## 2. Install Python

You need **Python 3.7 or newer**. Check in a terminal:

| OS | Check | If missing |
|---|---|---|
| **macOS** | Open *Terminal*, run `python3 --version` | Accept the "install developer tools" prompt, or install from [python.org](https://www.python.org/downloads/), or `brew install python` |
| **Windows** | Open *Command Prompt*, run `py --version` | Install from [python.org](https://www.python.org/downloads/) (keep "py launcher" checked) |
| **Linux** | `python3 --version` | `sudo apt install python3` (Debian/Ubuntu), `sudo dnf install python3` (Fedora) |

Nothing else is needed: no `pip install`.

## 3. Download ont-english-proxy

**Option A: with git** (easiest to update later)

```
git clone https://github.com/typerhack/ont-english-proxy.git
cd ont-english-proxy
```

Don't have git?

- **macOS:** run `git --version` in Terminal. If git is missing, macOS offers to install it; click *Install*.
  (That installs Apple's small command line tools, which include git, not the full Xcode app.)
- **Windows:** download and install from [git-scm.com](https://git-scm.com/download/win).
- **Linux:** `sudo apt install git` (Debian/Ubuntu) or `sudo dnf install git` (Fedora).

**Option B: without git**

On the GitHub page click **Code → Download ZIP**, unzip it, and open a terminal in the unzipped folder:

- macOS: right-click the folder → *New Terminal at Folder* (or `cd ~/Downloads/ont-english-proxy-main`)
- Windows: open the folder, type `cmd` in the address bar, press Enter
- Linux: right-click → *Open in Terminal*

## 4. Run it

1. **Log out of the modem** in your browser if you're logged in. The modem allows only one admin login at a time.
2. Start the proxy from the `ont-english-proxy` folder:

   | OS | Command |
   |---|---|
   | macOS / Linux | `python3 ont_english_proxy.py --open` |
   | Windows | `py ont_english_proxy.py --open` |

   You should see:

   ```
   [ont-english-proxy] translations loaded: 90 menu names, 42 replacements, 0 dictionary overrides
   [ont-english-proxy] http://127.0.0.1:8181  ->  http://192.168.100.1   (Ctrl+C to stop)
   ```

3. Your browser opens **http://127.0.0.1:8181**. Log in with your normal modem username and password.
   The interface is now in English.
4. Keep the terminal window open while you use it.

> Tip: turn off your browser's automatic translation for this page, so you see the real result.

### Run it in the background (recommended for daily use)

| Command | What it does |
|---|---|
| `python3 ont_english_proxy.py start` | Starts in the background and opens the browser (add `--no-open` to skip) |
| `python3 ont_english_proxy.py status` | Shows whether it's running, its address and log file |
| `python3 ont_english_proxy.py stop` | Stops it |
| `python3 ont_english_proxy.py logs` | Shows the latest log lines (`-f` to follow live, `-n 200` for more) |

For debugging, start with extra detail: `start -v`, then watch with `logs -f`.

On Windows use `py` instead of `python3`. Running `start` twice is safe; it won't start a second copy.
The background log is in `~/.ont-english-proxy/proxy.log`.

### Shortcut: one command from anywhere (optional)

Create an `ont-en` command, using the real path of your `ont-english-proxy` folder:

| Shell | Add this line to | Line |
|---|---|---|
| macOS (zsh) | `~/.zshrc` | `alias ont-en='python3 /path/to/ont-english-proxy/ont_english_proxy.py'` |
| Linux (bash) | `~/.bashrc` | `alias ont-en='python3 /path/to/ont-english-proxy/ont_english_proxy.py'` |
| Windows PowerShell | `$PROFILE` (run `notepad $PROFILE`) | `function ont-en { py C:\path\to\ont-english-proxy\ont_english_proxy.py @args }` |

Open a new terminal, then from any folder:

```
ont-en start      # background + browser
ont-en status
ont-en logs -f    # watch the log live (Ctrl+C stops watching, not the proxy)
ont-en stop
ont-en --open     # foreground instead; Ctrl+C stops
```

## 5. Stop it

- Started with `start`: run `python3 ont_english_proxy.py stop` (or `ont-en stop`).
- Started in the foreground: press **Ctrl+C** in its terminal window.

Then use the modem directly again at `http://192.168.100.1` if you like.

## 6. Update to the latest version

- **With git:** in the folder, run `git pull`
- **Without git:** download the ZIP again and replace the folder. Keep a copy of `translations.json`
  if you've added your own translations.

## 7. Options

```
python3 ont_english_proxy.py [run|start|stop|status|logs] [options]

run                  foreground (default); Ctrl+C stops
start | stop | status  background control
logs                 show the background log

--port 8181          local port (pick another if 8181 is taken, e.g. --port 9000)
--upstream HOST[:P]  modem address (default 192.168.100.1)
--listen 127.0.0.1   listen address; keep it local (see Privacy and security)
--translations FILE  use a different translations file
--open               run: open the browser automatically
--no-open            start: don't open the browser
-n, --lines N        logs: how many recent lines (default 50)
-f, --follow         logs: keep showing new lines
-v, --verbose        log full request lines (may include tokens in URLs; don't share these logs)
```

Example for a modem at a different address: `python3 ont_english_proxy.py --upstream 192.168.1.1 --open`

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| `cannot listen on 127.0.0.1:8181 … already in use` | It's already running: check with `status`, stop with `stop`. Or use `--port 9000` |
| `modem unreachable` in the browser | Check that `http://192.168.100.1` opens directly; use `--upstream` if your modem has another address |
| Login page loads, but login fails or bounces back | Log out of the modem in every other tab/device, wait a minute, try again (one admin session only) |
| Something doesn't work and you want to see why | `logs` shows recent requests and errors; restart with `start -v` for full detail |
| Still some Chinese text | Normal for a few rare labels. See [Fixing remaining Chinese text](#9-fixing-remaining-chinese-text) |
| Page looks unchanged after editing translations | Reload the page (Cmd+Shift+R / Ctrl+F5) |
| `python3: command not found` (Windows) | Use `py` instead of `python3` |

## 9. Fixing remaining Chinese text

All translations are in **`translations.json`**. Edit it with any text editor; the proxy reloads it
automatically, so just refresh the page.

| Section | Use for | Example |
|---|---|---|
| `menu` | Exact menu/page names | `"首页": "Home"` |
| `replace` | Text anywhere in pages and logs (longest match wins) | `"已连接": "Connected"` |
| `dictionaries` | Labels missing from the modem's English language files | `"DevInfoDes": { "somekey": "English text" }` |

Rules: menu names at most 20 characters and no `&`; no quotes or backslashes in translations.

Found a missing translation? Please share it (see [Contributing](#12-contributing)) so everyone benefits.

## 10. Saving settings through the proxy

Changes you **Apply/Save** through the proxy **really are saved on the modem**: the proxy forwards them
unchanged. It only changes what you see. After saving, reload the page to confirm the value stuck.
For critical changes (WAN, PON/ONT authentication, firmware) you may prefer the direct modem interface.

## 11. How it works

| What the proxy does | Why |
|---|---|
| Requests for `…/chinese/…` files are sent to the modem as `…/english/…` | The modem has English dictionaries and styles; it just never asks for them |
| `curLanguage = 'chinese'` → `'english'` in pages | Pages use Huawei's own English layout and logic |
| Labels missing in English fall back to Chinese, then `translations.json` | Nothing shows up blank |
| Menu names come from `translations.json` → `menu` | The menu is Chinese-only on the modem |
| Escaped Chinese text in logs is decoded and translated | Logs are sent as `\uXXXX` escapes |
| Browser caching is disabled | Translation changes show up on a normal reload |

Cookies, login tokens and form submissions are forwarded **unchanged**.

## 12. Contributing

Translations, fixes and reports for other models are very welcome.

```
# 1. Fork on GitHub, then:
git clone https://github.com/<your-username>/ont-english-proxy.git
cd ont-english-proxy
git config core.hooksPath .githooks        # enables the privacy hooks (see below)

# 2. Make a branch and your change
git checkout -b add-translations

# 3. Test
python3 -m unittest discover -s tests      # offline tests, no modem needed
python3 tools/privacy_check.py

# 4. Commit, push, open a Pull Request on GitHub
git commit -am "Add translations for WLAN pages"
git push -u origin add-translations
```

Keep your fork up to date with this repository:

```
git remote add upstream https://github.com/typerhack/ont-english-proxy.git
git pull upstream main
```

Ground rules (full version in [AGENTS.md](AGENTS.md), which AI coding assistants also follow):

- **Never commit anything from your device or computer**: serial numbers, MAC/IP addresses, passwords,
  cookies, tokens, logs, Wi-Fi names, file paths, or Huawei's own files. Use made-up examples.
  The privacy check enforces this.
- Python standard library only; must keep working on macOS, Linux and Windows.
- The proxy must never change modem settings by itself.

**Privacy hooks** (enabled by `git config core.hooksPath .githooks`):

| Hook | What it does |
|---|---|
| `pre-commit` | Blocks commits containing serials, MAC/IP addresses, emails, personal paths, cookies or Huawei files |
| `post-commit` | Rewrites each new commit's timestamps to UTC: git normally records your timezone, which reveals your region |
| `pre-push` | Blocks pushing any commit that still has a non-UTC timestamp (e.g. after a rebase) |

### Timezone protection: read this before pushing

Every git commit normally records your **local timezone** (e.g. `+0330`), which reveals the region you
live in. This repository **only accepts UTC timestamps** (`+0000`):

- With the hooks enabled, normal commits are converted to UTC automatically. Nothing to do.
- If a push is **blocked** ("these commits contain your local timezone"), typically after a rebase,
  cherry-pick or a commit made without hooks, fix the commits and push again:

  | Shell | Command |
  |---|---|
  | macOS / Linux / Git Bash | `TZ=UTC0 git rebase --ignore-date origin/main` |
  | Windows PowerShell | `$env:TZ='UTC0'; git rebase --ignore-date origin/main; Remove-Item Env:TZ` |
  | Windows cmd | `set TZ=UTC0 && git rebase --ignore-date origin/main && set TZ=` |

  Then `git push` as usual.
- Committing without the hooks? Prefix the command yourself: `TZ=UTC0 git commit -m "…"`

Pull requests with non-UTC commits will be asked to fix them this way.

Git also publishes the name and email in your commits. To keep your email private, use your GitHub
noreply address: `git config user.email <id>+<username>@users.noreply.github.com`
(find it under GitHub → Settings → Emails).

## 13. Privacy and security

- The proxy listens on `127.0.0.1` only, so other devices on your network can't use it. Don't use
  `--listen 0.0.0.0` on a network you don't trust: the modem connection is plain HTTP.
- Your password and session are never stored or logged by the proxy.
- No data leaves your network: the proxy only talks to your modem.

## License

[MIT](LICENSE)

## Disclaimer

Not affiliated with or endorsed by Huawei. Use at your own risk. Huawei's web interface files are not
included in this repository; the proxy only rewrites what your own modem serves.
