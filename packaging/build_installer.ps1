# Build script for creating the MTGO Metagame Deck Builder installer
# This script runs on Windows and creates the installer using Inno Setup
#
# Prerequisites:
# - Inno Setup 6 installed (https://jrsoftware.org/isdl.php)
# - PyInstaller installed (pip install pyinstaller)
# - .NET 9 SDK (optional, if you want to rebuild the bridge)

param(
    [switch]$SkipPyInstaller = $false,
    [switch]$SkipDotNetBuild = $false
)

$ErrorActionPreference = "Stop"
$script:HadWarning = $false

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$DistDir = Join-Path $ProjectRoot "dist"
$InstallerDir = Join-Path $DistDir "installer"

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
    $script:HadWarning = $true
}

function Write-Error-Custom {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Fail-On-Warnings {
    if ($script:HadWarning) {
        Write-Error-Custom "Build aborted because a warning was raised."
        exit 1
    }
}

function Ensure-DefusedXml {
    param([string]$PythonPath)

    if (-not $PythonPath) {
        Write-Warn "Python not found; cannot install defusedxml."
        return
    }

    Write-Info "Ensuring defusedxml is installed..."
    & $PythonPath -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('defusedxml') else 1)"
    if ($LASTEXITCODE -eq 0) {
        Write-Info "defusedxml already installed."
        return
    }

    Write-Info "Installing defusedxml..."
    & $PythonPath -m pip install --upgrade defusedxml
    if ($LASTEXITCODE -ne 0) {
        Write-Error-Custom "Failed to install defusedxml (exit code $LASTEXITCODE)."
        exit 1
    }
}

function Ensure-GitSync {
    $GitDir = Join-Path $ProjectRoot ".git"
    if (-not (Test-Path $GitDir)) {
        Write-Warn "Git repository not found in project root; skipping git pull."
        return
    }

    Write-Info "Syncing with remote branch..."
    $currentLocation = Get-Location
    Push-Location $ProjectRoot
    try {
        git pull --ff-only
    } catch {
        Write-Warn "Git pull failed: $_"
    } finally {
        Pop-Location
    }
}

# Ensure we are on the latest branch before building
Ensure-GitSync

# Step 0: clean previous dist output
Write-Info "Cleaning dist directory..."
if (Test-Path $DistDir) {
    try {
        Remove-Item -LiteralPath $DistDir -Recurse -Force -ErrorAction Stop
        Write-Info "Removed existing dist directory."
    } catch {
        Write-Warn "Failed to delete dist directory: $_"
    }
} else {
    Write-Info "No existing dist directory found."
}

# Step 0: ensure vendor data directories exist
Write-Info "Updating vendor data..."
Push-Location $ProjectRoot
try {
    $VendorUpdateScript = Join-Path $ProjectRoot "scripts\update_vendor_data.py"
    $VendorPython = Join-Path $ProjectRoot "env\Scripts\python.exe"
    $FallbackPython = Get-Command python -ErrorAction SilentlyContinue
    $PythonPath = $null
    if (Test-Path $VendorPython) {
        $PythonPath = $VendorPython
    } elseif ($FallbackPython) {
        $PythonPath = $FallbackPython.Source
    }
    Ensure-DefusedXml -PythonPath $PythonPath
    Fail-On-Warnings

    if (-not (Test-Path $VendorUpdateScript)) {
        Write-Warn "Vendor update script not found; skipping vendor refresh."
    } else {
        if ($PythonPath) {
            & $PythonPath $VendorUpdateScript
        } else {
            Write-Warn "Python not found; cannot update vendor data."
        }

        if ($LASTEXITCODE -ne 0) {
            Write-Warn "Vendor update script exited with code $LASTEXITCODE"
        }

        $MtgoSdkScript = Join-Path $ProjectRoot "scripts\update_mtgosdk_vendor.py"
        if (Test-Path $MtgoSdkScript) {
            Write-Info "Updating MTGOSDK vendor data..."
            if ($PythonPath) {
                & $PythonPath $MtgoSdkScript
            } else {
                Write-Warn "Python not found; skipping MTGOSDK vendor update."
            }
            if ($LASTEXITCODE -ne 0) {
                Write-Warn "MTGOSDK vendor script exited with code $LASTEXITCODE"
            }
        } else {
            Write-Warn "MTGOSDK update script not found."
        }
    }
    foreach ($vendorDir in @("vendor\mtgo_format_data", "vendor\mtgo_archetype_parser", "vendor\mtgosdk")) {
        $fullPath = Join-Path $ProjectRoot $vendorDir
        if (-not (Test-Path $fullPath)) {
            Write-Info "Creating missing vendor directory: $vendorDir"
            New-Item -ItemType Directory -Force -Path $fullPath | Out-Null
        }
    }

    $ManaDir = Join-Path $ProjectRoot "assets\mana"
    if (-not (Test-Path $ManaDir)) {
        Write-Info "Mana assets missing; fetching from the Pedrogush/mana fork…"
        $FetchScript = Join-Path $ProjectRoot "scripts\fetch_mana_assets.py"
        if (Test-Path $FetchScript) {
            if (Test-Path $VendorPython) {
                & $VendorPython $FetchScript
            } elseif ($FallbackPython) {
                & $FallbackPython.Source $FetchScript
            } else {
                Write-Warn "Python not found; cannot fetch mana assets."
            }
            if ($LASTEXITCODE -ne 0) {
                Write-Warn "Mana assets fetch exited with code $LASTEXITCODE"
            }
        } else {
            Write-Warn "Mana asset fetch script not found at $FetchScript"
        }
    } else {
        Write-Info "Mana assets already present."
    }
} finally {
    Pop-Location
}
Fail-On-Warnings

# Step 1: Check for Inno Setup
function Get-EnvValue {
    param([string]$Name)

    try {
        $envItem = Get-Item "env:$Name" -ErrorAction Stop
        return $envItem.Value
    } catch {
        return $null
    }
}

Write-Info "Checking for Inno Setup..."
$InnoSetupPath = $env:INNO_SETUP_PATH
if (-not $InnoSetupPath) {
    $ProgramFilesX86 = Get-EnvValue "ProgramFiles(x86)"
    if ($ProgramFilesX86) {
        $candidate = Join-Path $ProgramFilesX86 "Inno Setup 6\ISCC.exe"
        if (Test-Path $candidate) {
            $InnoSetupPath = $candidate
        }
    }
}

if (-not $InnoSetupPath) {
    $ProgramFiles = Get-EnvValue "ProgramFiles"
    if ($ProgramFiles) {
        $candidate = Join-Path $ProgramFiles "Inno Setup 6\ISCC.exe"
        if (Test-Path $candidate) {
            $InnoSetupPath = $candidate
        }
    }
}

if (-not $InnoSetupPath) {
    Write-Error-Custom "Inno Setup not found. Please install Inno Setup 6 from https://jrsoftware.org/isdl.php"
    exit 1
}

Write-Info "Inno Setup found at: $InnoSetupPath"

function Find-PyInstallerPath {
    param([string]$ProjectRoot)

    $explicit = Join-Path $ProjectRoot "env\Scripts\pyinstaller.exe"
    Write-Info "Looking for PyInstaller at explicit path: $explicit"
    if (Test-Path $explicit) {
        Write-Info "PyInstaller found explicitly."
        return $explicit
    }

    $fromEnv = Get-Command pyinstaller -ErrorAction SilentlyContinue
    if ($fromEnv) {
        Write-Info "PyInstaller found via PATH: $($fromEnv.Path)"
        return $fromEnv.Path
    }

    Write-Warn "PyInstaller not found explicitly or via PATH."
    return $null
}

# Step 2: Check for PyInstaller
if (-not $SkipPyInstaller) {
    Write-Info "Checking for PyInstaller..."
    $PyInstallerPath = Find-PyInstallerPath -ProjectRoot $ProjectRoot
    if (-not $PyInstallerPath) {
        Write-Error-Custom "PyInstaller is not installed. Install it with: pip install pyinstaller"
        exit 1
    }

    # Step 3: Build PyInstaller executable
    Write-Info "Building PyInstaller executable..."
    Push-Location $ProjectRoot

    # Check if main.py exists
    if (-not (Test-Path "main.py")) {
        Write-Error-Custom "main.py not found. Please ensure the entry point exists."
        Pop-Location
        exit 1
    }

    # Run PyInstaller with the spec file
    $SpecFile = Join-Path $ProjectRoot "packaging\magic_online_metagame_crawler.spec"
    if (Test-Path $SpecFile) {
        Write-Info "Using existing spec file..."
        & $PyInstallerPath $SpecFile --clean --noconfirm
        if ($LASTEXITCODE -ne 0) {
            Write-Error-Custom "PyInstaller build failed!"
            Pop-Location
            exit 1
        }
    } else {
        Write-Error-Custom "PyInstaller spec file not found at packaging\magic_online_metagame_crawler.spec"
        Pop-Location
        exit 1
    }

    # Verify the executable was created
    $ExePath = Join-Path $DistDir "magic_online_metagame_crawler.exe"
    if (-not (Test-Path $ExePath)) {
        Write-Error-Custom "PyInstaller build failed - executable not found at $ExePath"
        Pop-Location
        exit 1
    }

    Write-Info "PyInstaller build complete!"
    Pop-Location
} else {
    Write-Info "Skipping PyInstaller build (using existing executable)"
}

# Step 4: Check for .NET bridge (optional)
if (-not $SkipDotNetBuild) {
    $BridgePath = Join-Path $ProjectRoot "dotnet\MTGOBridge\bin\Release\net9.0-windows7.0\win-x64\publish\MTGOBridge.exe"
    if (-not (Test-Path $BridgePath)) {
        Write-Info ".NET bridge not found at expected location; building..."

        # Check for dotnet SDK
        $DotNetCheck = Get-Command dotnet -ErrorAction SilentlyContinue
        if ($DotNetCheck) {
            Push-Location (Join-Path $ProjectRoot "dotnet\MTGOBridge")
            Write-Info "Building .NET bridge as self-contained single file (bundles .NET runtime)..."
            & dotnet publish -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -warnaserror
            Pop-Location

            if (-not (Test-Path $BridgePath)) {
                Write-Error-Custom ".NET bridge build completed but executable not found at $BridgePath"
                exit 1
            }

            Write-Info ".NET bridge build complete!"
        } else {
            Write-Error-Custom ".NET SDK not found. Install .NET 9 SDK or rerun with -SkipDotNetBuild."
            exit 1
        }
    } else {
        Write-Info ".NET bridge found at: $BridgePath"
    }
}
Fail-On-Warnings

# Step 5: Create installer output directory
Write-Info "Creating installer output directory..."
New-Item -ItemType Directory -Force -Path $InstallerDir | Out-Null

# Step 6: Run Inno Setup Compiler
Write-Info "Running Inno Setup Compiler..."
$IssFile = Join-Path $ScriptDir "installer.iss"

& $InnoSetupPath $IssFile
if ($LASTEXITCODE -ne 0) {
    Write-Error-Custom "Inno Setup compilation failed!"
    exit 1
}

# Step 7: Verify the installer was created
$InstallerFile = Join-Path $InstallerDir "MTGOMetagameBuilder_Setup_v0.2.exe"
if (-not (Test-Path $InstallerFile)) {
    Write-Error-Custom "Installer was not created at expected location: $InstallerFile"
    exit 1
}

# Get installer size
$InstallerSize = (Get-Item $InstallerFile).Length / 1MB
$InstallerSizeFormatted = "{0:N2} MB" -f $InstallerSize
$InstallerTimestamp = (Get-Item $InstallerFile).LastWriteTime
Fail-On-Warnings

Write-Info "=========================================="
Write-Info "Installer build SUCCESSFUL!"
Write-Info "=========================================="
Write-Info "Installer location: $InstallerFile"
Write-Info "Installer size: $InstallerSizeFormatted"
Write-Info ("Installer timestamp: {0:yyyy-MM-dd HH:mm:ss zzz}" -f $InstallerTimestamp)
Write-Info ""
Write-Info "You can now run this installer to install the application."
Write-Info "To test the installer, run: .\test_installer.ps1"
