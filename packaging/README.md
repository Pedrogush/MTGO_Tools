# Windows Installer Build

Build on Windows: `.\build_installer.ps1`
Build on Linux: `./build_installer.sh`
Test the installer file: `.\test_installer.ps1` or `./test_installer.sh`
Test the install/uninstall path: `.\test_install_uninstall.ps1` (Windows only)

This directory contains Inno Setup configuration and build scripts for creating a professional Windows installer. The installer includes license agreement, custom install directory selection, Start Menu and Desktop shortcuts, and bundles all dependencies including the PyInstaller executable, .NET bridge, and vendor data.

The install is **per-user and requires no administrator privileges** (`PrivilegesRequired=lowest`): the app installs under `%LOCALAPPDATA%\Programs` and writes all of its runtime data (config, cache, logs, downloaded card data) under `%LOCALAPPDATA%\MTGO Tools` — never next to the executable. Uninstall removes the app, the post-install bridge download, and the regenerable data (cache/logs/data), while preserving user settings (config) and saved decks (`~\Documents\mtgo_decks`).

`test_install_uninstall.ps1` verifies that lifecycle end-to-end: it installs silently, seeds simulated runtime data, uninstalls, and asserts the machine is left clean — no orphaned registry key, no leftover install directory or bridge download, regenerable data gone, user data preserved. This is the test that catches stray-registry-key / leftover-file bugs that a file-only check (`test_installer.ps1`) can't.

**Debugging an installed build:** the shipped executable is windowed (no console), but `debugpy` is bundled so you can attach an IDE debugger the same way you would in the editor. Set `MTGO_TOOLS_INSTALL_DEBUG=1` (or `MTGO_TOOLS_INSTALL_DEBUG=<port>`) before launching to have it listen on 127.0.0.1:5678, then use your IDE's "attach to process/port". Set `MTGO_TOOLS_INSTALL_DEBUG_WAIT=1` to block startup until the debugger attaches (for breaking on early startup code). The hook is inert unless the env var is set. File logs are always written to `%LOCALAPPDATA%\MTGO Tools\logs`; set `MTGO_LOG_LEVEL=DEBUG` for verbose output.

Prerequisites: Inno Setup 6, Python 3.11+ with PyInstaller, and the **.NET 9 SDK** (required — used to publish the self-contained MTGO bridge that is shipped inside the installer). The SDK can be installed with no admin rights via `Invoke-WebRequest https://dot.net/v1/dotnet-install.ps1 -OutFile dotnet-install.ps1; .\dotnet-install.ps1 -Channel 9.0`; the build script auto-detects a per-user SDK under `%LOCALAPPDATA%\Microsoft\dotnet`. On Linux the build script uses Wine to run Inno Setup and will automatically download it if not present. Output is created at dist/installer/MTGOTools_Setup_v0.2.exe. The PyInstaller spec is `mtgo_tools.spec`, which produces a single-file `dist/mtgo_tools.exe`.

To customize edit installer.iss to change version, app name, included files, or shortcuts. For distribution sign the installer and generate checksums. The build and test scripts are CI/CD friendly.

Notes:
- Mana symbol assets are auto-fetched (and bundled) during the build if `assets/mana` is missing. They come from the `Pedrogush/mana` fork of `andrewgioia/mana`, which pins the source so upstream changes never affect us until the fork is synced. The app also self-fetches these assets on first run (see `scripts/fetch_mana_assets.py`).

## MTGO bridge (bundled)

The .NET `MTGOBridge` (source in `dotnet/MTGOBridge/`) is **built from source and
shipped inside the installer** — there is no install-time download. `build_installer.ps1`
publishes it self-contained (`dotnet publish -r win-x64 --self-contained -p:PublishSingleFile=true`),
which bundles the .NET runtime, and `installer.iss` copies the publish output into
`{app}\mtgo_integration\`. The app resolves it there at runtime
(`services/mtgo_bridge_service/discovery.py`). This makes MTGO integration work out of
the box on a clean machine: no network dependency at install time and no separate .NET
runtime requirement for the user.

The bridge is **mandatory**: `build_installer.ps1` fails if the .NET 9 SDK is missing or
the publish output is absent, rather than producing an installer without MTGO integration.
Pass `-SkipDotNetBuild` to reuse an already-published bridge (e.g. for faster iteration on
the installer itself); the published artifact must still exist or the build aborts.

To change the bridge, edit the C# under `dotnet/MTGOBridge/` and rebuild the installer —
the new binary is picked up automatically. The trade-off of bundling is installer size:
the self-contained bridge adds the .NET runtime (~60-70 MB) to the setup .exe.
