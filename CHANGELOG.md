# Changelog

## 2026-07-05

- Added per-monitor playlists with optional shuffle in the Manager.
- Added backward-compatible player config normalization for legacy string paths and new playlist objects.
- Updated startup selection so each monitor launches only one valid video, choosing randomly when shuffle is enabled.
- Updated health/install config checks, docs, and example config for playlist support.

## 2026-07-03

- Fixed autostart validation for repository paths containing spaces.
- Fixed stale-autostart detection so the Manager reports entries that point to another checkout.
- Fixed health-check false failures and broken `config.json` validation.
- Added `xset` to dependency checks because the player requires it for X server readiness detection.
- Fixed duplicate lock acquisition in `player.py` to avoid replacing/leaking the lock file descriptor.
- Hardened Manager background refresh so it does not show Tk dialogs from a worker thread.
- Hardened log-window refresh error handling.
- Added stdlib regression tests for desktop Exec parsing, monitor parsing, and duplicate lock behavior.
- Added `.gitignore` and `config.example.json`; runtime `config.json`, logs, caches, and build artifacts are excluded from release commits.
