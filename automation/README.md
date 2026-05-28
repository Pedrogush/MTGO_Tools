# Automation CLI

The automation package exposes a local socket server inside the wxPython app and
a CLI for manual testing, E2E scripts, and debugging UI regressions.

## Scope: Dev/Test Only

The automation server is intended **strictly for local development, E2E tests,
and debugging UI regressions**. It is **not** a supported runtime feature for
end users and is **not** enabled in packaged/installed builds.

Security boundary:

- The server is **disabled by default**. It only starts when `main.py` is
  launched with the explicit `--automation` flag (see `main.py`'s
  `parse_args()`).
- The packaged Inno Setup installer (`packaging/installer.iss`) and PyInstaller
  spec (`packaging/magic_online_metagame_crawler.spec`) do **not** pass
  `--automation`, so end-user installs never expose this surface.
- When enabled, the server binds to `127.0.0.1` only (loopback), so it is not
  reachable from other machines on the network.
- The server has **no authentication**. Any local process on the developer
  machine can connect and drive the UI, take screenshots to arbitrary paths,
  and close the app. Do not enable `--automation` on a multi-user machine or
  while running untrusted local processes.
- If the automation surface is ever exposed beyond a developer workstation
  (e.g. as a runtime feature for users), it should first gain a local auth
  token (shared secret negotiated at launch) and a path-allowlist for
  screenshot destinations.

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
