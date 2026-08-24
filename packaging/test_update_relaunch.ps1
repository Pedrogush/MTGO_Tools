<#
.SYNOPSIS
    Verifies that an in-app update's /RELAUNCH actually brings the app back.

.DESCRIPTION
    The in-app updater (services/update_installer.py) downloads this installer,
    runs it as `/SILENT /NORESTART /RELAUNCH`, and exits so its own files can be
    replaced; the installer's [Run] entry is what starts the new build. This
    script drives that last step directly, from the environment the updater
    hands Setup, and asserts the app came back.

    The environment is the whole point. A PyInstaller onefile build runs from a
    directory it unpacked into %TEMP% (_MEIxxxxxx) and advertises it to its child
    processes through _PYI_APPLICATION_HOME_DIR / _PYI_ARCHIVE_FILE /
    _PYI_PARENT_PROCESS_LEVEL. Setup inherits them from the app that launched it,
    and without the cleanup in installer.iss the relaunched app inherits them
    from Setup - then loads Python from the old app's unpack directory, deleted
    when that app exited, and dies before any Python runs:

        Failed to load Python DLL '...\_MEIxxxxxx\python3xx.dll'

    So this script sets those variables to a directory that does not exist,
    exactly as an exited app would leave them, with _PYI_ARCHIVE_FILE naming the
    installed executable (the same path before and after an update - which is
    what makes the bootloader trust them). If the app starts anyway, the
    inherited state was cleared. If it never appears, it was not.

    A new log file under %LOCALAPPDATA%\MTGO Tools\logs is the signal: the app
    writes one per run, before building any UI, so it appears whether or not the
    window does - and it cannot appear at all if the bootloader failed.

.NOTES
    Run on Windows in a normal (non-elevated) shell.

    CAUTION: this installs over the current install and briefly starts the app
    (it is killed again at the end). No user data is touched.

.PARAMETER InstallerPath
    Path to the built installer. Defaults to the standard build output.

.PARAMETER TimeoutSeconds
    How long to wait for the relaunched app to write its log. The default allows
    for a cold start on a slow disk.
#>

param(
    [string]$InstallerPath,
    [int]$TimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

if (-not $InstallerPath) {
    $AppVersion = (Get-Content -Raw (Join-Path $ProjectRoot "VERSION")).Trim()
    $InstallerPath = Join-Path $ProjectRoot "dist\installer\MTGOTools_Setup_v$AppVersion.exe"
}

$AppName   = "MTGO Tools"   # must match MyAppName / INSTALLED_APP_DATA_DIR_NAME
$ExeName   = "mtgo_tools.exe"
$AppExe    = Join-Path $env:LOCALAPPDATA "Programs\$AppName\$ExeName"
$LogDir    = Join-Path $env:LOCALAPPDATA "$AppName\logs"

function Write-Info { param([string]$m) Write-Host "[INFO] $m" -ForegroundColor Green }
function Write-Test { param([string]$m) Write-Host "[TEST] $m" -ForegroundColor Blue }
function Write-Pass { param([string]$m) Write-Host "[PASS] $m" -ForegroundColor Green }
function Write-Fail { param([string]$m) Write-Host "[FAIL] $m" -ForegroundColor Red }

function Stop-App {
    Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($ExeName)) -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

Write-Info "=========================================="
Write-Info "MTGO Tools Update Relaunch Test"
Write-Info "=========================================="
Write-Host ""

if (-not (Test-Path $InstallerPath)) {
    Write-Fail "Installer not found at: $InstallerPath"
    Write-Info "Build it first with .\build_installer.ps1"
    exit 1
}
Write-Info "Installer: $InstallerPath"
Write-Info "Log dir:   $LogDir"
Write-Host ""

Stop-App
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Before = @(Get-ChildItem -Path $LogDir -Filter "*.log" -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty Name)

# The environment an exited onefile app leaves to the processes it started. The
# directory is deliberately one that does not exist: that is the state after the
# app that launched Setup has exited and its bootloader cleaned up.
$Stale = Join-Path $env:TEMP "_MEI_does_not_exist_update_relaunch_test"
$env:_PYI_APPLICATION_HOME_DIR = $Stale
$env:_PYI_ARCHIVE_FILE         = $AppExe
$env:_PYI_PARENT_PROCESS_LEVEL = "1"

Write-Test "Installing with /SILENT /NORESTART /RELAUNCH from an updater environment"
Write-Info "  _PYI_APPLICATION_HOME_DIR = $Stale (does not exist)"
# -PassThru + WaitForExit rather than -Wait. Start-Process -Wait waits on a job
# object containing the whole process tree, and the tree here includes the app
# Setup relaunches - so -Wait would block for as long as the app stayed open,
# which is exactly what this test is waiting for it to do.
$proc = Start-Process -FilePath $InstallerPath `
                      -ArgumentList "/SILENT", "/NORESTART", "/RELAUNCH" `
                      -PassThru
$proc.WaitForExit()
Remove-Item Env:\_PYI_APPLICATION_HOME_DIR, Env:\_PYI_ARCHIVE_FILE, Env:\_PYI_PARENT_PROCESS_LEVEL `
            -ErrorAction SilentlyContinue

if ($proc.ExitCode -ne 0) {
    Write-Fail "Setup exited with code $($proc.ExitCode)"
    exit 1
}
Write-Info "Setup finished; waiting up to $TimeoutSeconds s for the app to come back..."

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$newLog = $null
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    $newLog = Get-ChildItem -Path $LogDir -Filter "*.log" -ErrorAction SilentlyContinue |
              Where-Object { $Before -notcontains $_.Name } |
              Select-Object -First 1
    if ($newLog) { break }
}

if (-not $newLog) {
    Write-Fail "The app did not come back: no new log in $LogDir"
    Write-Info "This is the _MEI regression - check the [Code] section of installer.iss"
    Write-Info "and _BOOTLOADER_ENV_VARS in services/update_installer.py."
    exit 1
}

Write-Pass "The app relaunched and started logging: $($newLog.Name)"
Start-Sleep -Seconds 3
Stop-App
Write-Info "Closed the relaunched app."
exit 0
