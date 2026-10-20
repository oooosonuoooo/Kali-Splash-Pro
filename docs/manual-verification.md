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
- Add, remove, clear, and reorder playlist items for a monitor.
- Shuffle checkbox saves to `config.json`.
- Dependency chips are green for installed tools.
- Enable/Disable Autostart updates status.
- View Logs opens and refreshes cleanly.
- Preview launches mpv for the selected playlist item, or a playlist pick if none is selected.

### Folder import and playlist persistence

- Select **Add Folder** for a folder containing more than nine supported videos, including names with spaces and mixed-case extensions.
- Confirm every direct child video appears in the playlist and the view scrolls to the last new entry.
- Save with an old unavailable path still present; confirm the new entries save and the unavailable path is retained with a status message.
- Preview representative hardware-decoded and software-decoded video formats and confirm the mpv GPU output initializes.
- Click **Optimize for GPU** for AV1 entries; confirm copies appear in `~/.cache/kali-splash-pro/h264/` and the source files remain unchanged.
- Preview an optimized clip and confirm mpv reports NVDEC hardware decoding; startup should prefer the optimized copy while it exists.

## Player Smoke Test

```bash
python3 src/player.py
```

Expected:

- One selected video opens per configured monitor.
- Video is fullscreen and on top.
- The player exits after playback.
- `splash_debug.log` records start, display readiness, launches, and finish.

## Autostart Reboot Test

1. Enable autostart in the Manager.
2. Reboot into Kali XFCE/X11.
3. Confirm one configured video plays per monitor at session startup.
4. Run `./check.sh` after login and confirm no warnings.
