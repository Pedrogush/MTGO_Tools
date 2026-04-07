# Automation CLI

The automation package exposes a local socket server inside the wxPython app and
a CLI for manual testing, E2E scripts, and debugging UI regressions.

## Common Workflow

```bash
python -m automation.cli open-app --wait
python -m automation.cli ping
python -m automation.cli screenshot --path screenshots/current.png
python -m automation.cli screenshot --headless --path screenshots/background.png
python -m automation.cli close-app
```

`open-app --wait` launches `main.py --automation` and blocks until the
automation server responds. Use `--port` if you need to avoid the default port:

```bash
python -m automation.cli --port 19857 open-app --wait
python -m automation.cli --port 19857 ping
python -m automation.cli --port 19857 close-app
```

## Headless Screenshots

`screenshot --headless` is self-contained once the app is running with
automation enabled. If the main window is minimized or hidden, the server
temporarily restores it, captures the screenshot, and returns it to the previous
minimized or hidden state afterward.

No extra shell, `cmd.exe`, or manual window-management step is required by
`screenshot --headless` itself. The only WSL-specific concern is how you invoke
the Windows Python process when running the CLI from WSL.

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
