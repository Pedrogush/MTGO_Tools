<#
.SYNOPSIS
    Reset the machine to a clean slate for installer/app testing.

.DESCRIPTION
    Removes everything a previous install or run of MTGO Tools leaves on the
    machine so the next install/launch starts fresh:

      * Kills any running mtgo_tools processes (including multiprocessing
        spawn children that would hold the exe locked).
      * Uninstalls the app if present (runs its uninstaller, then force-removes
        any residual install directory and the uninstall registry key).
      * Deletes the per-user data directory (%LOCALAPPDATA%\MTGO Tools:
        config, cache, logs, downloaded card data).

    Saved decks (~\Documents\mtgo_decks) are preserved by default since they are
    real user data; pass -IncludeDecks to wipe those too.

.PARAMETER KeepInstall
    Leave the installed application in place; only clear the per-user data.

.PARAMETER IncludeDecks
    Also delete saved decks in ~\Documents\mtgo_decks.

.EXAMPLE
    .\reset_test_state.ps1                # uninstall + wipe app data, keep decks
    .\reset_test_state.ps1 -KeepInstall   # keep the install, just wipe app data
    .\reset_test_state.ps1 -IncludeDecks  # full wipe including saved decks
#>

param(
    [switch]$KeepInstall,
    [switch]$IncludeDecks
)

$ErrorActionPreference = "Stop"

# Must match installer.iss AppId/MyAppName and INSTALLED_APP_DATA_DIR_NAME.
$AppId    = "{8F9A2D3B-1C4E-5F6A-7B8C-9D0E1F2A3B4C}_is1"
$AppName  = "MTGO Tools"
$UninstallSubkey = "Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppId"

$DataDir  = Join-Path $env:LOCALAPPDATA $AppName
$DecksDir = Join-Path ([Environment]::GetFolderPath('MyDocuments')) "mtgo_decks"

function Write-Info { param([string]$m) Write-Host "[INFO] $m" -ForegroundColor Green }
function Write-Step { param([string]$m) Write-Host "[ .. ] $m" -ForegroundColor Cyan }
function Write-Done { param([string]$m) Write-Host "[ OK ] $m" -ForegroundColor Green }
function Write-Skip { param([string]$m) Write-Host "[skip] $m" -ForegroundColor DarkGray }

function Get-UninstallKeyPath {
    foreach ($hive in @("HKCU:", "HKLM:")) {
        $path = Join-Path $hive $UninstallSubkey
        if (Test-Path $path) { return $path }
    }
    return $null
}

Write-Info "=========================================="
Write-Info "MTGO Tools - reset test state"
Write-Info "=========================================="

# 1. Kill running processes -------------------------------------------------
$procs = Get-Process -Name mtgo_tools -ErrorAction SilentlyContinue
if ($procs) {
    Write-Step "Stopping $($procs.Count) running mtgo_tools process(es)..."
    $procs | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Write-Done "Processes stopped."
} else {
    Write-Skip "No mtgo_tools process running."
}

# 2. Uninstall the app ------------------------------------------------------
$keyPath = Get-UninstallKeyPath
if ($KeepInstall) {
    Write-Skip "Keeping the installed app (-KeepInstall)."
} elseif ($keyPath) {
    $key = Get-ItemProperty -Path $keyPath
    $installDir = $key.InstallLocation
    $uninsExe = Join-Path $installDir "unins000.exe"
    if (Test-Path $uninsExe) {
        Write-Step "Uninstalling via $uninsExe ..."
        Start-Process -FilePath $uninsExe -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" | Out-Null
        $deadline = (Get-Date).AddSeconds(60)
        while ((Get-UninstallKeyPath) -and ((Get-Date) -lt $deadline)) { Start-Sleep -Milliseconds 500 }
        Start-Sleep -Seconds 2
    } else {
        Write-Skip "Uninstaller not found; will force-remove."
    }
    # Force-remove any residue the uninstaller could not delete.
    if ($installDir -and (Test-Path $installDir)) {
        Remove-Item -LiteralPath $installDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    $stillThere = Get-UninstallKeyPath
    if ($stillThere) { Remove-Item -LiteralPath $stillThere -Recurse -Force -ErrorAction SilentlyContinue }
    Write-Done "App uninstalled."
} else {
    Write-Skip "App is not installed."
}

# 3. Wipe per-user data -----------------------------------------------------
if (Test-Path $DataDir) {
    Write-Step "Removing per-user data: $DataDir"
    Remove-Item -LiteralPath $DataDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Done "Per-user data removed."
} else {
    Write-Skip "No per-user data at $DataDir."
}

# 4. Saved decks (opt-in) ---------------------------------------------------
if ($IncludeDecks) {
    if (Test-Path $DecksDir) {
        Write-Step "Removing saved decks: $DecksDir"
        Remove-Item -LiteralPath $DecksDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Done "Saved decks removed."
    } else {
        Write-Skip "No saved decks at $DecksDir."
    }
} else {
    Write-Skip "Preserving saved decks (pass -IncludeDecks to wipe)."
}

# Summary -------------------------------------------------------------------
Write-Host ""
Write-Info "Clean-slate summary:"
Write-Info ("  Uninstall key : " + ($(if (Get-UninstallKeyPath) { "PRESENT" } else { "gone" })))
Write-Info ("  App data dir  : " + ($(if (Test-Path $DataDir) { "PRESENT" } else { "gone" })))
Write-Info ("  Saved decks   : " + ($(if (Test-Path $DecksDir) { "present" } else { "gone" })))
Write-Info "Done."
