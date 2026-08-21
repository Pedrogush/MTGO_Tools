# Build script for creating the MTGO Tools installer
# This script runs on Windows and creates the installer using Inno Setup
#
# Prerequisites:
# - Inno Setup 6 installed (https://jrsoftware.org/isdl.php)
# - PyInstaller installed (pip install pyinstaller)
# - .NET 9 SDK (REQUIRED): the MTGO bridge is built self-contained and shipped
#   inside the installer, so the build fails if it cannot be produced. A per-user
#   SDK under %LOCALAPPDATA%\Microsoft\dotnet is detected automatically (install
#   with no admin via https://dot.net/v1/dotnet-install.ps1 -Channel 9.0).

param(
    [switch]$SkipPyInstaller = $false,
    # Reuse an already-published bridge instead of rebuilding it. The bridge is
    # still REQUIRED: if the published artifact is missing, the build fails
    # rather than shipping an installer without MTGO integration.
    [switch]$SkipDotNetBuild = $false,
    # Skip downloading the bundled bulk-data seed. Without the seed, a fresh
    # install downloads the card database on first run (works, just slower to
    # warm up). Provided as an escape hatch for offline builds; normal releases
    # should ship the seed so first-run is instant.
    [switch]$SkipBulkSeed = $false
)

$ErrorActionPreference = "Stop"
$script:HadWarning = $false

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$DistDir = Join-Path $ProjectRoot "dist"
$InstallerDir = Join-Path $DistDir "installer"

# Version is the single source of truth in the repo-root VERSION file, owned by
# the release automation (scripts/next_version.py + .github/workflows/release.yml).
# installer.iss reads the same file, so the output filename below matches it.
$VersionFile = Join-Path $ProjectRoot "VERSION"
if (-not (Test-Path $VersionFile)) {
    Write-Host "[ERROR] VERSION file not found at $VersionFile" -ForegroundColor Red
    exit 1
}
$AppVersion = (Get-Content -Raw $VersionFile).Trim()
$InstallerFileName = "MTGOTools_Setup_v$AppVersion.exe"

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

    # Never in CI. A CI job must build exactly the commit it checked out, and
    # since versioning moved after the merge (docs/VERSIONING.md) `main` grows a
    # `chore(release): VERSION x.y.z` commit seconds after any merge lands. A
    # pull here swallows it mid-build: the run that merged PR #1000 read VERSION
    # as 1.1.6, pulled 1.1.7 into the tree, and then ISCC -- which reads the file
    # again at compile time -- emitted MTGOTools_Setup_v1.1.7.exe while the
    # script went looking for the 1.1.6 name it had already computed.
    if ($env:CI) {
        Write-Info "CI detected; building the checked-out commit without pulling."
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

# Re-read VERSION after the sync. installer.iss reads the same file itself, at
# ISCC compile time -- minutes later, and after this pull. Reading it once up top
# left two readers of a file that had moved in between, and the only symptom was
# the build "succeeding" and then failing on a filename that did not exist.
# Defence in depth: the CI guard above already prevents the pull that caused it,
# but a local build pulling a colleague's version bump would desync the same way.
$AppVersion = (Get-Content -Raw $VersionFile).Trim()
$InstallerFileName = "MTGOTools_Setup_v$AppVersion.exe"

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
    # Prefer the project virtualenv (which has the build deps like defusedxml and
    # PyInstaller). The venv is named ".venv" here; "env" is kept as a fallback for
    # other setups. A bare "python" on PATH is the last resort - on this machine
    # that resolves to a uv-managed interpreter whose "pip install" is blocked.
    $VendorPython = $null
    foreach ($cand in @(
        (Join-Path $ProjectRoot ".venv\Scripts\python.exe"),
        (Join-Path $ProjectRoot "env\Scripts\python.exe")
    )) {
        if (Test-Path $cand) { $VendorPython = $cand; break }
    }
    $FallbackPython = Get-Command python -ErrorAction SilentlyContinue
    $PythonPath = $null
    if ($VendorPython -and (Test-Path $VendorPython)) {
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
            if ($VendorPython -and (Test-Path $VendorPython)) {
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

    # Prefer the project virtualenv (".venv" here, "env" as a fallback) before a
    # PyInstaller on PATH, so the build uses the same interpreter that has the
    # project's build dependencies installed.
    foreach ($explicit in @(
        (Join-Path $ProjectRoot ".venv\Scripts\pyinstaller.exe"),
        (Join-Path $ProjectRoot "env\Scripts\pyinstaller.exe")
    )) {
        Write-Info "Looking for PyInstaller at explicit path: $explicit"
        if (Test-Path $explicit) {
            Write-Info "PyInstaller found explicitly."
            return $explicit
        }
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
    $SpecFile = Join-Path $ProjectRoot "packaging\mtgo_tools.spec"
    if (Test-Path $SpecFile) {
        Write-Info "Using existing spec file..."
        & $PyInstallerPath $SpecFile --clean --noconfirm
        if ($LASTEXITCODE -ne 0) {
            Write-Error-Custom "PyInstaller build failed!"
            Pop-Location
            exit 1
        }
    } else {
        Write-Error-Custom "PyInstaller spec file not found at packaging\mtgo_tools.spec"
        Pop-Location
        exit 1
    }

    # Verify the executable was created
    $ExePath = Join-Path $DistDir "mtgo_tools.exe"
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

# Step 3b: Build the bundled bulk-data seed.
#
# Downloads Scryfall's default_cards bulk file (gzip transfer, ~130 MB) and
# writes it to dist/seed/bulk_data.json.gz. The onefile "dist/*" [Files] rule in
# installer.iss ships everything under dist (except installer/), so the seed
# lands at {app}\seed\bulk_data.json.gz, which the app decompresses into its
# image cache on first run (services/image_service/seed.py). This makes a fresh
# install start warm instead of racing a cold download.
if (-not $SkipBulkSeed) {
    Write-Info "Building bundled bulk-data seed (this downloads ~130 MB)..."
    $SeedScript = Join-Path $ProjectRoot "scripts\build_bulk_seed.py"
    $SeedOut = Join-Path $DistDir "seed\bulk_data.json.gz"
    if (-not $PythonPath) {
        Write-Warn "Python not found; cannot build the bulk-data seed."
    } elseif (-not (Test-Path $SeedScript)) {
        Write-Warn "Bulk seed script not found at $SeedScript"
    } else {
        & $PythonPath $SeedScript --out $SeedOut
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "Bulk seed build failed (exit code $LASTEXITCODE)."
        } elseif (-not (Test-Path $SeedOut)) {
            Write-Warn "Bulk seed build reported success but $SeedOut is missing."
        } else {
            $SeedSizeMb = "{0:N1} MB" -f ((Get-Item $SeedOut).Length / 1MB)
            Write-Info "Bulk-data seed ready: $SeedOut ($SeedSizeMb)"
        }
    }
    Fail-On-Warnings
} else {
    Write-Info "Skipping bulk-data seed build (-SkipBulkSeed); first run will download it."
}

# Step 4: Build the .NET bridge (REQUIRED)
#
# The bridge is a self-contained .NET publish (bundles its own runtime) and is
# shipped inside the installer by installer.iss. It is therefore mandatory: if
# the published artifact cannot be produced or found, we fail rather than ship an
# installer without MTGO integration.
function Find-DotNetPath {
    # Prefer an explicit dotnet on PATH, then the per-user install location used
    # by dotnet-install.ps1 (%LOCALAPPDATA%\Microsoft\dotnet), then the standard
    # machine-wide location. Mirrors how PyInstaller/Python are resolved above.
    $fromEnv = Get-Command dotnet -ErrorAction SilentlyContinue
    if ($fromEnv) {
        Write-Info "dotnet found via PATH: $($fromEnv.Path)"
        return $fromEnv.Source
    }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Microsoft\dotnet\dotnet.exe"),
        (Join-Path $env:ProgramFiles "dotnet\dotnet.exe")
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            Write-Info "dotnet found at: $candidate"
            return $candidate
        }
    }
    return $null
}

$BridgeProject = Join-Path $ProjectRoot "dotnet\MTGOBridge"
$BridgePublishDir = Join-Path $BridgeProject "bin\Release\net9.0-windows7.0\win-x64\publish"
$BridgePath = Join-Path $BridgePublishDir "MTGOBridge.exe"

if ($SkipDotNetBuild) {
    Write-Info "Skipping .NET bridge build (-SkipDotNetBuild); reusing existing publish output."
} else {
    $DotNetPath = Find-DotNetPath
    if (-not $DotNetPath) {
        Write-Error-Custom ".NET 9 SDK not found. The bridge is shipped inside the installer and cannot be skipped."
        Write-Error-Custom "Install it with no admin rights via:"
        Write-Error-Custom "  Invoke-WebRequest https://dot.net/v1/dotnet-install.ps1 -OutFile dotnet-install.ps1; .\dotnet-install.ps1 -Channel 9.0"
        exit 1
    }
    Push-Location $BridgeProject
    Write-Info "Building .NET bridge as self-contained single file (bundles .NET runtime)..."
    & $DotNetPath publish -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -warnaserror
    $BridgeExit = $LASTEXITCODE
    Pop-Location
    if ($BridgeExit -ne 0) {
        Write-Error-Custom ".NET bridge build failed (exit code $BridgeExit)."
        exit 1
    }
    Write-Info ".NET bridge build complete!"
}

# Hard requirement: the published bridge MUST exist before we compile the
# installer, regardless of whether we just built it or reused an existing build.
if (-not (Test-Path $BridgePath)) {
    Write-Error-Custom "MTGO bridge not found at $BridgePath"
    Write-Error-Custom "The installer ships the bridge from this path; refusing to build without it."
    Write-Error-Custom "Run without -SkipDotNetBuild (and with the .NET 9 SDK installed) to build it."
    exit 1
}
Write-Info "MTGO bridge ready: $BridgePath"
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
$InstallerFile = Join-Path $InstallerDir $InstallerFileName
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
