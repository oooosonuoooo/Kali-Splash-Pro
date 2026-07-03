# Maintenance Log

## 2026-07-03 Production Readiness Pass

Backup created before edits:

```text
/home/sonu/Downloads/New Folder/Kali-Splash-Pro.backup-20260703-095815.tar.gz
```

Remote state checked:

```text
origin/main = 7cbe58121a4ff8bfa32d358420fd4543c37a2f94
local main  = 7cbe58121a4ff8bfa32d358420fd4543c37a2f94
```

Findings and fixes:

- `manager.py` parsed `.desktop` `Exec=` lines with whitespace splitting, so paths like `New Folder` were reported broken. Replaced this with `shlex.split`.
- Autostart validation accepted any existing `player.py`, including stale checkouts. It now compares the real path against the current checkout.
- Manager status refresh could call `messagebox` from a background thread on malformed config. Config loading now supports quiet background reads.
- Manager dependency status missed `xset`, although `player.py` requires it to detect X readiness.
- Manager log refresh could raise from a Tk callback if the log disappeared or became unreadable. Refresh now uses a guarded reader.
- `install.sh` could attempt duplicate apt package names when both `xrandr` and `xset` were missing. Package collection now deduplicates.
- `check.sh` did not check `xset`, had unsafe JSON validation, and used fragile `sed` parsing for quoted paths. It now uses env-based JSON reads and Python `shlex`.
- `player.py` allowed a second lock acquisition in the same process, replacing the stored file descriptor. It now rejects duplicate acquisition.
- Runtime files and generated caches were present in the repo. Added `.gitignore` and `config.example.json`; keep live `config.json` and logs local.

Verification commands:

```bash
python3 -m py_compile src/player.py src/manager.py
bash -n install.sh check.sh uninstall.sh
python3 -m unittest discover -s tests -v
./check.sh
```
