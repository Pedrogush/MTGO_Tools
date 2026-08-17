#!/usr/bin/env bash
# Set up and launch MTGO Tools on Linux / WSLg.
#
# The app is Windows-first (see ARCHITECTURE.md), but the UI is plain wxPython
# and runs unmodified on GTK3. Two things are needed that a Windows checkout
# does not provide:
#
#   1. A Linux venv. requirements.txt pins wxPython only for Windows, and PyPI
#      ships no Linux wheel for it, so wx must come from the wxPython "extras"
#      index (prebuilt GTK3 wheels, per distro release). The .NET/Win32 pins
#      (pythonnet, pyautogui, pynput) are skipped - they only back the MTGO
#      bridge and screen automation, which need the Windows MTGO client anyway.
#
#   2. The system libraries the wx wheel links against. If you have root:
#        sudo apt-get install -y libsdl2-2.0-0 libsm6 libnotify4 libpcre2-32-0
#      If you do not, "--fetch-libs" downloads those .debs and unpacks them into
#      the venv, and the launcher puts them on LD_LIBRARY_PATH.
#
# Usage:
#   scripts/run_linux.sh --setup [--fetch-libs]   # one-time
#   scripts/run_linux.sh [app args...]            # launch
#
# Optional: libwebkit2gtk-4.1-0 enables the deck stats panel's HTML view. It
# cannot be side-loaded (its helper processes are compiled to an absolute
# /usr/lib path), so it needs a real install. Without it the panel falls back to
# summary-only stats, which is handled in widgets/panels/deck_stats_panel.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${MTGO_TOOLS_LINUX_VENV:-$HOME/mtgo-venv}"
SYSLIBS="$VENV/syslibs"

# wxPython publishes prebuilt GTK3 wheels per Ubuntu release; 4.2.2 is the
# newest with a noble build. Adjust if you are on a different distro release.
WX_VERSION="4.2.2"
WX_INDEX="https://extras.wxpython.org/wxPython4/extras/linux/gtk3/ubuntu-24.04/"

# Runtime .so names the wx wheel needs that a minimal Ubuntu desktop lacks,
# plus the transitive audio stack SDL2 pulls in.
DEB_PACKAGES=(
  libsm6 libice6 libnotify4 libpcre2-32-0
  libsdl2-2.0-0 libxss1 libasound2t64 libdecor-0-0 libpulse0 libsamplerate0
  libapparmor1 libdbus-1-3 libsndfile1 libflac12t64 libasyncns0
  libmp3lame0 libmpg123-0t64 libogg0 libopus0 libvorbis0a libvorbisenc2
)

fetch_libs() {
  local tmp
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  echo "Downloading runtime libraries into $SYSLIBS ..."
  mkdir -p "$SYSLIBS"
  (
    cd "$tmp"
    for pkg in "${DEB_PACKAGES[@]}"; do
      # One at a time: apt-get aborts the whole batch on a single bad candidate.
      apt-get download "$pkg" >/dev/null 2>&1 || echo "  skipped (no candidate): $pkg"
    done
    for deb in *.deb; do dpkg-deb -x "$deb" x; done
    cp -a x/usr/lib/x86_64-linux-gnu/*.so* "$SYSLIBS"/ 2>/dev/null || true
    cp -a x/usr/lib/x86_64-linux-gnu/pulseaudio/*.so* "$SYSLIBS"/ 2>/dev/null || true
  )
  echo "Unpacked $(ls -1 "$SYSLIBS" | wc -l) files."
}

setup() {
  [ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip
  "$VENV/bin/pip" install -f "$WX_INDEX" "wxPython==$WX_VERSION"
  # requirements.txt minus the Windows-only pins.
  "$VENV/bin/pip" install \
    "msgspec>=0.18.6" requests==2.32.5 loguru==0.7.3 beautifulsoup4==4.14.3 \
    curl-cffi==0.14.0 defusedxml==0.7.1 pillow==12.1.0 pytesseract==0.3.13 \
    matplotlib==3.10.8 "numpy>=1.26" lxml==6.0.2 pygetwindow==0.0.9

  if [ "${FETCH_LIBS:-0}" = "1" ]; then fetch_libs; fi

  if ! LD_LIBRARY_PATH="$SYSLIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
       "$VENV/bin/python" -c "import wx" 2>/dev/null; then
    echo
    echo "wx still cannot load. Missing system libraries:"
    LD_LIBRARY_PATH="$SYSLIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
      ldd "$VENV"/lib/python3*/site-packages/wx/_core*.so 2>/dev/null |
      grep 'not found' | awk '{print "  " $1}' | sort -u
    echo "Install them with apt, or re-run with --fetch-libs."
    exit 1
  fi
  echo "Setup OK: $("$VENV/bin/python" -c 'import wx; print(wx.version())')"
}

case "${1:-}" in
  --setup)
    shift
    [ "${1:-}" = "--fetch-libs" ] && { FETCH_LIBS=1; shift; }
    setup
    exit 0
    ;;
  --fetch-libs)
    shift
    fetch_libs
    exit 0
    ;;
esac

if [ ! -x "$VENV/bin/python" ]; then
  echo "No Linux venv at $VENV. Run: scripts/run_linux.sh --setup --fetch-libs" >&2
  exit 1
fi

[ -d "$SYSLIBS" ] && export LD_LIBRARY_PATH="$SYSLIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
cd "$REPO_ROOT"
exec "$VENV/bin/python" main.py "$@"
