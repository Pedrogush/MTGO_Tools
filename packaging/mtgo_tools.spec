# -*- mode: python ; coding: utf-8 -*-

import os
import pathlib
import sys

block_cipher = None

def _spec_path() -> pathlib.Path:
    if "__file__" in globals():
        return pathlib.Path(__file__).resolve()
    if sys.argv:
        return pathlib.Path(sys.argv[0]).resolve()
    return pathlib.Path(".").resolve()

project_root = _spec_path().parents[1]

def tree(src: pathlib.Path, dest: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    if not src.exists():
        return result
    for root, _dirs, files in os.walk(src):
        for file in files:
            path = pathlib.Path(root) / file
            rel = path.relative_to(src)
            target_dir = pathlib.Path(dest) / rel.parent
            result.append((str(path), str(target_dir)))
    return result

datas = []
# Nothing under vendor/ is frozen into this bundle.
#
# vendor/mtgo_format_data (Badaro/MTGOFormatData) and vendor/mtgo_archetype_parser
# (Badaro/MTGOArchetypeParser) used to be listed here. They are not any more:
# no module in this repository reads either tree -- the only references anywhere
# are scripts/update_vendor_data.py and this packaging directory -- and
# MTGOFormatData publishes no license at all (no LICENSE upstream, no terms in its
# README, none in GitHub's metadata), so bundling it was redistribution without a
# grant. Both trees remain available in a developer checkout via
# scripts/update_vendor_data.py; they simply do not ship. See ATTRIBUTIONS.md and
# the matching note in packaging/installer.iss.
#
# vendor/mtgosdk is excluded too: the MTGO bridge is a separate self-contained
# .NET publish that the Inno Setup installer ships into {app}\mtgo_integration, and
# nothing in it is part of this bundle. That is also why MTGOSDK's NOTICE is not
# added here -- this frozen executable redistributes no MTGOSDK binaries, so
# Apache-2.0 section 4(d) does not attach to it. The installer, which does ship
# those binaries, carries the NOTICE (packaging/installer.iss).
for rel in [
    "assets/mana",
    "help",
]:
    src = project_root / rel
    if src.exists():
        datas += tree(src, rel)

# MTGOBridge.exe is no longer bundled in the PyInstaller output.
# It is downloaded to {app}/mtgo_integration/ by the Inno Setup installer.
binaries = []

# wxPython's Edge/WebView2 backend loads WebView2Loader.dll by bare name at
# runtime, so no .pyd imports it and PyInstaller's dependency analysis never sees
# it. Shipping without it does not disable the WebView: wxWidgets silently hands
# back the IE backend instead, which is Trident in IE7 document mode and has no
# flexbox -- which is how the installed build rendered every deck-stats bar at
# full panel width while the same code from source looked right.
#
# It is bundled into ``wx/`` so the layout matches site-packages, and
# ``widgets.charts.view.ensure_webview2_loader`` loads it from there by absolute
# path. Both strings are cross-checked against that module by
# tests/test_webview_backend.py.
WEBVIEW2_LOADER_NAME = "WebView2Loader.dll"
WEBVIEW2_LOADER_DEST = "wx"

import importlib.util  # noqa: E402

_wx_spec = importlib.util.find_spec("wx")
_wx_dir = pathlib.Path(_wx_spec.origin).parent if _wx_spec and _wx_spec.origin else None
_webview2_loader = _wx_dir / WEBVIEW2_LOADER_NAME if _wx_dir else None
if _webview2_loader and _webview2_loader.exists():
    binaries += [(str(_webview2_loader), WEBVIEW2_LOADER_DEST)]
elif sys.platform == "win32":
    # Fail the build rather than ship a bundle whose charts render on IE.
    raise SystemExit(
        f"{WEBVIEW2_LOADER_NAME} not found next to the wx package "
        f"({_wx_dir}); the packaged app would fall back to the IE WebView backend"
    )

entry_point = project_root / "main.py"
app_icon = project_root / "assets" / "icons" / "hammer.ico"

# Bundle the app icon as data too, so the running app can set it as the window /
# taskbar icon at runtime (utils/app_icon.py). The EXE icon= below only covers
# the .exe file icon.
datas += [(str(app_icon), "assets/icons")]

# The repo-root VERSION file is the single source of truth for the running
# version (utils/constants/app.py reads it via resource_path). The in-app update
# check compares it against the latest published release, so a build that
# shipped without it could never tell whether it was current.
datas += [(str(project_root / "VERSION"), ".")]

# Hidden imports: modules PyInstaller's static analysis can't see, so we find
# them dynamically. wxPython's richtext extension loads wx._xml/_html/_adv at
# runtime, and the first-party packages lazily import their submodules via a
# package __getattr__. debugpy backs the MTGO_TOOLS_INSTALL_DEBUG hook in main.py.
from PyInstaller.utils.hooks import collect_submodules  # noqa: E402

# collect_submodules imports each package, so the project root must be on sys.path
# (at spec-eval time only the spec's own directory is).
sys.path.insert(0, str(project_root))

hiddenimports = ["debugpy", "wx._xml", "wx._html", "wx._adv"]
for _pkg in ("widgets", "services", "repositories", "controllers", "utils", "automation"):
    hiddenimports += collect_submodules(_pkg)

# dulwich backs the deck version history. Its porcelain layer reaches several
# submodules through late/conditional imports (compat shims, the optional C
# object-store accelerators), so static analysis alone under-collects it and the
# first deck save in a packaged build would be the place that found out.
hiddenimports += collect_submodules("dulwich")

a = Analysis(
    [str(entry_point)],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="mtgo_tools",
    icon=str(app_icon),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
