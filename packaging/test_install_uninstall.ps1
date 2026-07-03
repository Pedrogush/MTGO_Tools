<#
.SYNOPSIS
    End-to-end install/uninstall path test for the MTGO Tools.

.DESCRIPTION
    Where test_installer.ps1 only validates the installer *file* (PE header,
    size, signature), this exercises the actual install -> run -> uninstall
    lifecycle and verifies it leaves the machine clean:

      1. Snapshots the relevant registry key and directories.
      2. Installs silently and asserts the app + its uninstall registry entry
         appear where expected.
      3. Simulates runtime data (the caches/logs/config the app writes at first
         run) under %LOCALAPPDATA%.
      4. Uninstalls silently.
      5. Asserts nothing is left behind: the uninstall registry key is gone, the
         install directory (including the post-install bridge download) is gone,
         and regenerable per-user data (cache/logs/data) is gone - while user
         settings (config) and saved decks are intentionally preserved.

    This is what catches the classic installer bugs: an orphaned registry key,
    or files created after install (the downloaded bridge, runtime caches) that
    the uninstaller doesn't know to remove.

.NOTES
    Run on Windows in a normal (non-elevated) shell - the installer is a
    per-user install and needs no administrator privileges.

    CAUTION: this uninstalls the app and removes its regenerable per-user data
    (%LOCALAPPDATA%\MTGO Tools\{cache,logs,data}). Don't run it
    on a machine where you have a real install you want to keep. Saved decks
    (~\Documents\mtgo_decks) and settings (config) are preserved.

.PARAMETER InstallerPath
    Path to the built installer. Defaults to the standard build output.

.PARAMETER SkipLaunch
    Skip the best-effort launch of the installed app. Runtime data is simulated
    with marker files either way, so the uninstall-cleanup assertions still run.
#>

param(
    [string]$InstallerPath,
    [switch]$SkipLaunch
)

$ErrorActionPreference = "Stop"

# --- Constants ---------------------------------------------------------------
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

if (-not $InstallerPath) {
    $InstallerPath = Join-Path $ProjectRoot "dist\installer\MTGOTools_Setup_v0.2.exe"
}

# AppId from installer.iss (the doubled leading brace there escapes to one brace
# here) with Inno's "_is1" uninstall suffix.
$AppId       = "{8F9A2D3B-1C4E-5F6A-7B8C-9D0E1F2A3B4C}_is1"
$AppName     = "MTGO Tools"   # must match MyAppName / INSTALLED_APP_DATA_DIR_NAME
$UninstallSubkey = "Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppId"

$DataDir     = Join-Path $env:LOCALAPPDATA $AppName
$DecksDir    = Join-Path ([Environment]::GetFolderPath('MyDocuments')) "mtgo_decks"
$Marker      = "__install_uninstall_test_marker__.txt"

# --- Output helpers (mirrors test_installer.ps1) -----------------------------
function Write-Info { param([string]$m) Write-Host "[INFO] $m" -ForegroundColor Green }
function Write-Warn-Custom { param([string]$m) Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Write-Test { param([string]$m) Write-Host "[TEST] $m" -ForegroundColor Blue }
function Write-Pass { param([string]$m) Write-Host "[PASS] $m" -ForegroundColor Green }
function Write-Fail { param([string]$m) Write-Host "[FAIL] $m" -ForegroundColor Red }

$script:TestCount = 0
$script:PassCount = 0
$script:FailCount = 0

function Run-Test {
    param([string]$TestName, [scriptblock]$TestCommand)
    $script:TestCount++
    Write-Test "Test $($script:TestCount): $TestName"
    try {
        if (& $TestCommand) {
            Write-Pass $TestName; $script:PassCount++; return $true
        } else {
            Write-Fail $TestName; $script:FailCount++; return $false
        }
    } catch {
        Write-Fail "$TestName - Exception: $_"; $script:FailCount++; return $false
    }
}

# --- Registry helpers --------------------------------------------------------
# The install is per-user (HKCU); check HKLM too so an elevated install is still
# detected and cleaned-up assertions remain meaningful.
function Get-UninstallKey {
    foreach ($hive in @("HKCU:", "HKLM:")) {
        $path = Join-Path $hive $UninstallSubkey
        if (Test-Path $path) { return Get-ItemProperty -Path $path }
    }
    return $null
}
function Test-UninstallKeyPresent { return $null -ne (Get-UninstallKey) }

# --- Pre-flight --------------------------------------------------------------
Write-Info "=========================================="
Write-Info "MTGO Tools Install/Uninstall Test"
Write-Info "=========================================="
Write-Host ""

if (-not (Test-Path $InstallerPath)) {
    Write-Fail "Installer not found at: $InstallerPath"
    Write-Info "Build it first with .\build_installer.ps1"
    exit 1
}
Write-Info "Installer:   $InstallerPath"
Write-Info "Data dir:    $DataDir"
Write-Info "Decks dir:   $DecksDir"
Write-Host ""

if (Test-UninstallKeyPresent) {
    Write-Fail "The app appears to already be installed (uninstall key present)."
    Write-Info "Uninstall it first so the test starts from a clean state."
    exit 1
}

# Track whether the per-user data dir already existed so cleanup only removes
# what this test created.
$DataDirPreExisted = Test-Path $DataDir

# --- Install -----------------------------------------------------------------
Write-Info "Installing silently..."
$installLog = Join-Path $env:TEMP "mtgo_install_$PID.log"
$proc = Start-Process -FilePath $InstallerPath `
    -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOICONS", "/LOG=$installLog" `
    -Wait -PassThru
Write-Info "Installer exited with code $($proc.ExitCode) (log: $installLog)"
Write-Host ""

Run-Test "Installer exited successfully" { $proc.ExitCode -eq 0 }
Run-Test "Uninstall registry key created" { Test-UninstallKeyPresent }

$installKey  = Get-UninstallKey
$InstallDir  = if ($installKey) { $installKey.InstallLocation } else { $null }

Run-Test "InstallLocation recorded in registry" { -not [string]::IsNullOrWhiteSpace($InstallDir) }
Run-Test "Application executable installed" {
    $InstallDir -and (Test-Path (Join-Path $InstallDir "mtgo_tools.exe"))
}
Run-Test "Uninstaller registered" {
    $installKey -and ($installKey.UninstallString -or $installKey.QuietUninstallString)
}
Run-Test "App did NOT write data into the install dir" {
    # Regression guard for the old behavior (data next to the exe). Config/cache/
    # logs/data must live under %LOCALAPPDATA%, not in Program Files/{app}.
    if (-not $InstallDir) { return $false }
    -not (Test-Path (Join-Path $InstallDir "config")) -and
    -not (Test-Path (Join-Path $InstallDir "cache"))
}

# --- Simulate runtime data ---------------------------------------------------
# The app creates these on first run (utils/constants/paths.py). We seed marker
# files so the uninstall-cleanup policy can be asserted deterministically even
# without a full app run.
Write-Host ""
Write-Info "Seeding simulated runtime data under $DataDir ..."
foreach ($sub in @("cache", "logs", "data", "config")) {
    $dir = Join-Path $DataDir $sub
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    Set-Content -Path (Join-Path $dir $Marker) -Value "test" -Encoding ASCII
}
New-Item -ItemType Directory -Path $DecksDir -Force | Out-Null
$decksMarker = Join-Path $DecksDir $Marker
Set-Content -Path $decksMarker -Value "test" -Encoding ASCII

if (-not $SkipLaunch) {
    $exe = Join-Path $InstallDir "mtgo_tools.exe"
    if (Test-Path $exe) {
        Write-Info "Launching the installed app (best effort, 8s)..."
        try {
            $app = Start-Process -FilePath $exe -PassThru
            Start-Sleep -Seconds 8
            # A PyInstaller onefile app runs as a bootloader that spawns a child
            # process, so Stop-Process on $app alone leaves the real app (and its
            # lock on mtgo_tools.exe) alive - which would block the uninstaller
            # from deleting the exe. Kill the whole tree by PID, then sweep by
            # name, then wait for every mtgo_tools process to exit so the exe is
            # unlocked before we uninstall.
            & taskkill.exe /F /T /PID $app.Id 2>&1 | Out-Null
            Get-Process -Name mtgo_tools -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
            $killDeadline = (Get-Date).AddSeconds(15)
            while ((Get-Process -Name mtgo_tools -ErrorAction SilentlyContinue) -and ((Get-Date) -lt $killDeadline)) {
                Start-Sleep -Milliseconds 500
            }
            if (Get-Process -Name mtgo_tools -ErrorAction SilentlyContinue) {
                Write-Warn-Custom "App process still running after kill; the uninstall-cleanup check may be affected."
            }
        } catch {
            Write-Warn-Custom "Could not launch the app ($_); continuing with simulated data only."
        }
    }
}

# --- Uninstall ---------------------------------------------------------------
Write-Host ""
Write-Info "Uninstalling silently..."
$uninstallString = if ($installKey.QuietUninstallString) { $installKey.QuietUninstallString } else { $installKey.UninstallString }
# UninstallString is a quoted path to unins000.exe; strip quotes to get the exe.
$uninsExe = ($uninstallString -replace '(?<=\.exe").*', '') -replace '"', ''
if (-not (Test-Path $uninsExe)) { $uninsExe = Join-Path $InstallDir "unins000.exe" }

Start-Process -FilePath $uninsExe -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" | Out-Null

# Inno's uninstaller relaunches itself from a temp copy, so the spawned process
# returning doesn't mean it finished. Poll until the registry key clears.
Write-Info "Waiting for uninstall to complete..."
$deadline = (Get-Date).AddSeconds(60)
while ((Test-UninstallKeyPresent) -and ((Get-Date) -lt $deadline)) { Start-Sleep -Milliseconds 500 }
Start-Sleep -Seconds 2  # let final file/dir deletions settle
Write-Host ""

# --- Post-uninstall assertions ----------------------------------------------
Run-Test "Uninstall registry key removed" { -not (Test-UninstallKeyPresent) }
Run-Test "Install directory fully removed" {
    -not $InstallDir -or -not (Test-Path $InstallDir)
}
Run-Test "Downloaded bridge removed with install dir" {
    -not $InstallDir -or -not (Test-Path (Join-Path $InstallDir "mtgo_integration"))
}
Run-Test "Regenerable cache removed on uninstall" { -not (Test-Path (Join-Path $DataDir "cache")) }
Run-Test "Regenerable logs removed on uninstall"  { -not (Test-Path (Join-Path $DataDir "logs")) }
Run-Test "Regenerable data removed on uninstall"  { -not (Test-Path (Join-Path $DataDir "data")) }
Run-Test "User settings (config) preserved" { Test-Path (Join-Path (Join-Path $DataDir "config") $Marker) }
Run-Test "Saved decks preserved" { Test-Path $decksMarker }

# --- Cleanup of test artifacts ----------------------------------------------
Write-Host ""
Write-Info "Cleaning up test artifacts..."
Remove-Item -Path $decksMarker -Force -ErrorAction SilentlyContinue
if ($DataDirPreExisted) {
    # Only remove the config marker we added; leave any pre-existing data intact.
    Remove-Item -Path (Join-Path (Join-Path $DataDir "config") $Marker) -Force -ErrorAction SilentlyContinue
} else {
    # We created the whole data dir for this test; remove it entirely.
    Remove-Item -Path $DataDir -Recurse -Force -ErrorAction SilentlyContinue
}

# --- Summary -----------------------------------------------------------------
Write-Host ""
Write-Info "=========================================="
Write-Info "Results: $($script:PassCount)/$($script:TestCount) passed"
if ($script:FailCount -gt 0) {
    Write-Fail "Failed: $($script:FailCount)"
    Write-Fail "=========================================="
    exit 1
} else {
    Write-Pass "ALL TESTS PASSED - install/uninstall path is clean."
    Write-Pass "=========================================="
    exit 0
}
