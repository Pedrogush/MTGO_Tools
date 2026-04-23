# Automation CLI

The automation package exposes a local socket server inside the wxPython app and
a CLI for manual testing, E2E scripts, and debugging UI regressions.

## Common Workflow

```bash
python -m automation.cli open-app --wait
python -m automation.cli ping
python -m automation.cli screenshot --path screenshots/current.png
python -m automation.cli close-app
```

`open-app --wait` launches `main.py --automation` and blocks until the
automation server responds. Use `--port` if you need to avoid the default port:

```bash
python -m automation.cli --port 19857 open-app --wait
python -m automation.cli --port 19857 ping
python -m automation.cli --port 19857 close-app
```

## Screenshots

All screenshots use the Win32 `PrintWindow` API (`PW_RENDERFULLCONTENT`), which
renders the window through DWM regardless of whether other windows are covering
it — unlike a plain screen-blit which reads raw screen pixels. The capture
works even when the app is behind other windows.

`--headless` is accepted on the `screenshot` command for backward compatibility
but is now a no-op; every screenshot is inherently headless.

### Capturing the main window

```bash
python -m automation.cli screenshot --path screenshots/main.png
```

### Capturing a secondary window

Use `open-widget` to open the window first, then `screenshot-window` to capture
it. Supported window names: `opponent_tracker`, `timer_alert`, `match_history`,
`metagame`, `top_cards`, `mana_keyboard`.

```bash
python -m automation.cli open-widget match_history
python -m automation.cli screenshot-window match_history --path screenshots/history.png
```

`screenshot-window` returns an error if the named window is not currently open.

## WSL Interop Note

On a normal WSL setup, `cmd.exe /c ...` can run the Windows venv directly. If
bare `cmd.exe` returns `Exec format error` because WSLInterop binfmt registration
is missing, invoke it through `/init`:

```bash
/init /mnt/c/Windows/System32/cmd.exe /c "cd /d C:\Users\Pedro\Documents\GitHub\mtgo_tools && env\Scripts\python.exe -m automation.cli --help"
```

This is only an interop workaround for launching Windows commands from WSL. It
does not change how the automation CLI commands behave once they are running.

## Close Behavior

`close-app` sends a graceful close request to the running app. The server
acknowledges the command before scheduling the wx frame close, so scripts should
receive a clean response:

```json
{"closed": true}
```
