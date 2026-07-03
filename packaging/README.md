# Windows Installer Build

Build on Windows: `.\build_installer.ps1`
Build on Linux: `./build_installer.sh`
Test the installer file: `.\test_installer.ps1` or `./test_installer.sh`
Test the install/uninstall path: `.\test_install_uninstall.ps1` (Windows only)

This directory contains Inno Setup configuration and build scripts for creating a professional Windows installer. The installer includes license agreement, custom install directory selection, Start Menu and Desktop shortcuts, and bundles all dependencies including the PyInstaller executable, .NET bridge, and vendor data.

The install is **per-user and requires no administrator privileges** (`PrivilegesRequired=lowest`): the app installs under `%LOCALAPPDATA%\Programs` and writes all of its runtime data (config, cache, logs, downloaded card data) under `%LOCALAPPDATA%\MTGO Metagame Deck Builder` — never next to the executable. Uninstall removes the app, the post-install bridge download, and the regenerable data (cache/logs/data), while preserving user settings (config) and saved decks (`~\Documents\mtgo_decks`).

`test_install_uninstall.ps1` verifies that lifecycle end-to-end: it installs silently, seeds simulated runtime data, uninstalls, and asserts the machine is left clean — no orphaned registry key, no leftover install directory or bridge download, regenerable data gone, user data preserved. This is the test that catches stray-registry-key / leftover-file bugs that a file-only check (`test_installer.ps1`) can't.

**Debugging an installed build:** the shipped executable is windowed (no console), but `debugpy` is bundled so you can attach an IDE debugger the same way you would in the editor. Set `MTGO_TOOLS_INSTALL_DEBUG=1` (or `MTGO_TOOLS_INSTALL_DEBUG=<port>`) before launching to have it listen on 127.0.0.1:5678, then use your IDE's "attach to process/port". Set `MTGO_TOOLS_INSTALL_DEBUG_WAIT=1` to block startup until the debugger attaches (for breaking on early startup code). The hook is inert unless the env var is set. File logs are always written to `%LOCALAPPDATA%\MTGO Metagame Deck Builder\logs`; set `MTGO_LOG_LEVEL=DEBUG` for verbose output.

Prerequisites: Inno Setup 6, Python 3.11+ with PyInstaller, and optionally .NET 9 SDK (used to publish a self-contained bridge that bundles the .NET runtime). On Linux the build script uses Wine to run Inno Setup and will automatically download it if not present. Output is created at dist/installer/MTGOMetagameBuilder_Setup_v0.2.exe. The PyInstaller spec is `mtgo_tools.spec`, which produces a single-file `dist/mtgo_tools.exe`.

To customize edit installer.iss to change version, app name, included files, or shortcuts. For distribution sign the installer and generate checksums. The build and test scripts are CI/CD friendly.

Notes:
- Mana symbol assets are auto-fetched (and bundled) during the build if `assets/mana` is missing. They come from the `Pedrogush/mana` fork of `andrewgioia/mana`, which pins the source so upstream changes never affect us until the fork is synced. The app also self-fetches these assets on first run (see `scripts/fetch_mana_assets.py`).

## Bridge release flow

The .NET `MTGOBridge` artifact is **downloaded at install time** rather than
bundled inside the installer. This keeps the installer small and lets the
bridge be re-released independently of the main app. To guarantee integrity
the download is pinned to a tagged release URL **and** verified against a
known SHA-256.

`build_installer.ps1` still publishes the local bridge (used for local
testing and for catching build breakage); the published binaries are *not*
shipped in the installer.

Cutting a new bridge release:

1. Publish a release in the `Pedrogush/MTGOBridge` repo with a versioned zip
   asset (e.g. `MTGOBridge-vX.Y.Z.zip`).
2. Compute the SHA-256 of the published zip, e.g.
   `Get-FileHash -Algorithm SHA256 MTGOBridge-vX.Y.Z.zip` (PowerShell) or
   `sha256sum MTGOBridge-vX.Y.Z.zip` (Linux/macOS).
3. Edit `packaging/installer.iss` and update the three pinned constants
   together: `BRIDGE_RELEASE_URL`, `BRIDGE_ZIP_FILENAME`, and
   `BRIDGE_ZIP_SHA256`.
4. Rebuild the installer and confirm the post-install download succeeds with
   the new checksum.

If `BRIDGE_ZIP_SHA256` is empty the installer logs a warning and skips
verification — this is only intended for local debugging. Production
installers must ship with a populated hash.
