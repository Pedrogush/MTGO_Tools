# Windows Installer Build

Build on Windows: `.\build_installer.ps1`
Build on Linux: `./build_installer.sh`
Test: `.\test_installer.ps1` or `./test_installer.sh`

This directory contains Inno Setup configuration and build scripts for creating a professional Windows installer. The installer includes license agreement, custom install directory selection, Start Menu and Desktop shortcuts, and bundles all dependencies including the PyInstaller executable, .NET bridge, and vendor data.

Prerequisites: Inno Setup 6, Python 3.11+ with PyInstaller, and optionally .NET 9 SDK (used to publish a self-contained bridge that bundles the .NET runtime). On Linux the build script uses Wine to run Inno Setup and will automatically download it if not present. Output is created at dist/installer/MTGOMetagameBuilder_Setup_v0.2.exe.

To customize edit installer.iss to change version, app name, included files, or shortcuts. For distribution sign the installer and generate checksums. The build and test scripts are CI/CD friendly.

Notes:
- Mana symbol assets are auto-fetched (and bundled) during the build if `assets/mana` is missing.

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
