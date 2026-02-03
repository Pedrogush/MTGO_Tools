#!/bin/bash
# Build script for creating the MTGO Metagame Deck Builder installer
# This script runs on Linux but creates a Windows installer using Wine + Inno Setup
#
# Prerequisites:
# - Wine installed (for running Inno Setup on Linux)
# - Inno Setup installed in Wine (can be automated, see below)
# - PyInstaller for building the Python executable
# - .NET 9 SDK (optional, if you want to rebuild the bridge)

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$PROJECT_ROOT/dist"
INSTALLER_DIR="$DIST_DIR/installer"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    echo_error "Warning encountered; aborting build."
    exit 1
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

build_dotnet_bridge() {
    if ! command -v dotnet &> /dev/null; then
        echo_error ".NET SDK not found. Install .NET 9 SDK to build the bridge."
        exit 1
    fi

    echo_info "Building .NET bridge as self-contained single file (bundled runtime)..."
    (
        cd "$PROJECT_ROOT/dotnet/MTGOBridge" && \
            dotnet publish -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -warnaserror
    )
}

# Check if running on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo_error "This script is designed for Linux. For Windows, use build_installer.ps1 instead."
    exit 1
fi

ensure_defusedxml() {
    local py_bin
    py_bin="$(command -v python3 || true)"
    if [[ -z "$py_bin" ]]; then
        echo_warn "python3 not found; defusedxml is required."
    fi

    if "$py_bin" - <<'PY'; then
import importlib.util, sys
sys.exit(0 if importlib.util.find_spec("defusedxml") else 1)
PY
        echo_info "defusedxml already installed."
        return
    fi

    echo_info "Installing defusedxml..."
    if ! "$py_bin" -m pip install --upgrade defusedxml; then
        echo_error "Failed to install defusedxml."
        exit 1
    fi
}

# Step 0: clean previous dist output
echo_info "Cleaning dist directory..."
rm -rf "$DIST_DIR"
ensure_defusedxml

# Step 1: Check for Wine
echo_info "Checking for Wine..."
if ! command -v wine &> /dev/null; then
    echo_error "Wine is not installed. Please install Wine first:"
    echo "  Ubuntu/Debian: sudo apt-get install wine wine64"
    echo "  Arch: sudo pacman -S wine"
    echo "  Fedora: sudo dnf install wine"
    exit 1
fi

# Step 2: Check for Inno Setup in Wine
INNO_SETUP_PATH="$HOME/.wine/drive_c/Program Files (x86)/Inno Setup 6/ISCC.exe"
if [ ! -f "$INNO_SETUP_PATH" ]; then
    echo_warn "Inno Setup not found in Wine. Attempting to download and install..."

    # Download Inno Setup installer
    INNO_INSTALLER="/tmp/innosetup-6.3.3.exe"
    if [ ! -f "$INNO_INSTALLER" ]; then
        echo_info "Downloading Inno Setup 6.3.3..."
        wget -O "$INNO_INSTALLER" "https://files.jrsoftware.org/is/6/innosetup-6.3.3.exe" || {
            echo_error "Failed to download Inno Setup. Please download and install manually from https://jrsoftware.org/isdl.php"
            exit 1
        }
    fi

    # Install Inno Setup silently
    echo_info "Installing Inno Setup in Wine (this may take a minute)..."
    wine "$INNO_INSTALLER" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- || {
        echo_error "Failed to install Inno Setup. Please install manually."
        exit 1
    }

    # Wait a moment for installation to complete
    sleep 5

    if [ ! -f "$INNO_SETUP_PATH" ]; then
        echo_error "Inno Setup installation failed or is in a different location."
        exit 1
    fi
fi

echo_info "Inno Setup found at: $INNO_SETUP_PATH"

# Step 3: Check for PyInstaller
echo_info "Checking for PyInstaller..."
if ! command -v pyinstaller &> /dev/null; then
    echo_error "PyInstaller is not installed. Install it with: pip install pyinstaller"
    exit 1
fi

# Step 4: Build PyInstaller executable
echo_info "Building PyInstaller executable..."
cd "$PROJECT_ROOT"

# Check if main.py exists
if [ ! -f "main.py" ]; then
    echo_error "main.py not found. Please ensure the entry point exists."
    exit 1
fi

# Ensure mana assets are present (needed for packaged icons)
MANA_DIR="$PROJECT_ROOT/assets/mana"
if [ ! -d "$MANA_DIR" ]; then
    echo_info "Mana assets missing; fetching andrewgioia/mana…"
    if ! python3 scripts/fetch_mana_assets.py; then
        echo_warn "Failed to fetch mana assets; mana symbols will not render in the installer build."
    fi
else
    echo_info "Mana assets already present."
fi

# Run PyInstaller with the spec file
if [ -f "packaging/magic_online_metagame_crawler.spec" ]; then
    echo_info "Using existing spec file..."
    pyinstaller packaging/magic_online_metagame_crawler.spec --clean --noconfirm
else
    echo_error "PyInstaller spec file not found at packaging/magic_online_metagame_crawler.spec"
    exit 1
fi

# Verify the executable was created
if [ ! -f "$DIST_DIR/magic_online_metagame_crawler/magic_online_metagame_crawler.exe" ]; then
    echo_error "PyInstaller build failed - executable not found"
    exit 1
fi

echo_info "PyInstaller build complete!"

# Step 5: Ensure .NET bridge is present (build if missing)
BRIDGE_PATH="$PROJECT_ROOT/dotnet/MTGOBridge/bin/Release/net9.0-windows7.0/win-x64/publish/MTGOBridge.exe"
if [ ! -f "$BRIDGE_PATH" ]; then
    echo_info ".NET bridge not found at expected location. Building..."
    build_dotnet_bridge

    if [ ! -f "$BRIDGE_PATH" ]; then
        echo_error ".NET bridge build completed but executable not found at: $BRIDGE_PATH"
        exit 1
    fi
fi
echo_info ".NET bridge available at: $BRIDGE_PATH"

# Step 6: Create installer output directory
echo_info "Creating installer output directory..."
mkdir -p "$INSTALLER_DIR"

# Step 7: Run Inno Setup Compiler
echo_info "Running Inno Setup Compiler..."
cd "$SCRIPT_DIR"

# Convert Linux path to Windows path for Wine
ISS_FILE_WINDOWS="Z:$(echo "$SCRIPT_DIR/installer.iss" | sed 's/\//\\/g')"

wine "$INNO_SETUP_PATH" "$ISS_FILE_WINDOWS" || {
    echo_error "Inno Setup compilation failed!"
    exit 1
}

# Step 8: Verify the installer was created
INSTALLER_FILE="$INSTALLER_DIR/MTGOMetagameBuilder_Setup_v0.2.exe"
if [ ! -f "$INSTALLER_FILE" ]; then
    echo_error "Installer was not created at expected location: $INSTALLER_FILE"
    exit 1
fi

# Get installer size
INSTALLER_SIZE=$(du -h "$INSTALLER_FILE" | cut -f1)
INSTALLER_TIMESTAMP=$(date -r "$INSTALLER_FILE" +"%Y-%m-%d %H:%M:%S %Z")

echo_info "=========================================="
echo_info "Installer build SUCCESSFUL!"
echo_info "=========================================="
echo_info "Installer location: $INSTALLER_FILE"
echo_info "Installer size: $INSTALLER_SIZE"
echo_info "Installer timestamp: $INSTALLER_TIMESTAMP"
echo_info ""
echo_info "You can now copy this installer to a Windows machine and run it."
echo_info "To test the installer, run: ./test_installer.sh"
