# Manual Verification Checklist

Run these checks on Kali/XFCE/X11 before tagging a production release.

## Install / Repair

```bash
./install.sh
```

Expected:

- Dependencies are reported present or installed successfully.
- `~/.local/share/applications/kali-splash-pro.desktop` exists.
- Existing `~/.config/autostart/kali-splash-startup.desktop` is repaired to this checkout.
- No legacy `~/.config/systemd/user/kali-splash.service` remains.

## Health Check

```bash
./check.sh
```

Expected:

- Python syntax checks pass.
- `python3`, `mpv`, `xdotool`, `xrandr`, `xset`, and `python3-tk` pass.
- Config is valid JSON.
- Video paths exist.
- Autostart validates and points to this checkout.

## Manager Smoke Test

```bash
python3 src/manager.py
```

Expected:

- Window opens without terminal traceback.
- Monitor list appears.
- Dependency chips are green for installed tools.
- Enable/Disable Autostart updates status.
- View Logs opens and refreshes cleanly.
- Preview launches mpv for a configured video.

## Player Smoke Test

```bash
python3 src/player.py
```

Expected:

- One mpv instance opens per configured monitor.
- Video is fullscreen and on top.
- The player exits after playback.
- `splash_debug.log` records start, display readiness, launches, and finish.

## Autostart Reboot Test

1. Enable autostart in the Manager.
2. Reboot into Kali XFCE/X11.
3. Confirm the configured video plays once at session startup.
4. Run `./check.sh` after login and confirm no warnings.
