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

## Video capture (recording a transition)

`start-video` / `stop-video` record the main window on a **background thread**,
so they capture frames *while* a main-thread action (e.g. a layout toggle) is
running — something a single screenshot cannot do.

```bash
python -m automation.cli start-video --max-frames 120 --method screen
python -m automation.cli click left_toggle          # drive the UI while it records
python -m automation.cli stop-video --out-dir my_capture
```

`stop-video` writes one PNG per frame (named `frame_<idx>_<t_ms>ms.png`) plus a
`manifest.json` to `--out-dir`, and returns a compact summary (count, fps,
duration, manifest path) — the per-frame list lives in the manifest because the
transport does a single 64 KB `recv`.

`--method` selects the grabber:

- `screen` (default) — copies the **literal on-screen pixels** via a screen-DC
  `BitBlt`. This is the one that catches transient / ghost rendering artefacts
  that exist only in the on-screen surface. It reads true screen pixels, so the
  app must be the active, top-most window (no occluding windows) during capture.
- `printwindow` — uses `PrintWindow` (re-renders the widget tree). Faithful to
  the *logical* state, but **blind** to on-screen-only artefacts. Use it as a
  contrast control, not to verify a repaint bug.

### Driving + analyzing a panel transition

`automation/capture_panel_transition.py` orchestrates a record-toggle-record
session per side-panel toggle and flags frames that match neither the
pre-toggle nor post-toggle rest state (a "third state"):

```bash
python -m automation.capture_panel_transition --out-dir transition_capture --method screen
```

See `docs/sb_panel_third_state/HANDOFF.md` for a worked investigation
that used this tooling.

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
