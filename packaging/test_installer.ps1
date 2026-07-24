# Test script to verify the MTGO Tools installer was built correctly
# This performs basic verification of the installer file on Windows

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$InstallerDir = Join-Path $ProjectRoot "dist\installer"
$InstallerFile = Join-Path $InstallerDir "MTGOTools_Setup_v0.2.exe"

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Green
}

function Write-Warn-Custom {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Error-Custom {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-Test {
    param([string]$Message)
    Write-Host "[TEST] $Message" -ForegroundColor Blue
}

function Write-Pass {
    param([string]$Message)
    Write-Host "[PASS] $Message" -ForegroundColor Green
}

function Write-Fail {
    param([string]$Message)
    Write-Host "[FAIL] $Message" -ForegroundColor Red
}

$TestCount = 0
$PassCount = 0
$FailCount = 0

function Run-Test {
    param(
        [string]$TestName,
        [scriptblock]$TestCommand
    )

    $script:TestCount++
    Write-Test "Test ${TestCount}: $TestName"

    try {
        $result = & $TestCommand
        if ($result) {
            Write-Pass $TestName
            $script:PassCount++
            return $true
        } else {
            Write-Fail $TestName
            $script:FailCount++
            return $false
        }
    } catch {
        Write-Fail "$TestName - Exception: $_"
        $script:FailCount++
        return $false
    }
}

Write-Info "=========================================="
Write-Info "MTGO Tools Installer Test Suite"
Write-Info "=========================================="
Write-Host ""

# Test 1: Check if installer file exists
$testResult = Run-Test "Installer file exists" {
    Test-Path $InstallerFile
}

if (-not $testResult) {
    Write-Error-Custom "Installer file not found at: $InstallerFile"
    Write-Error-Custom "Please run .\build_installer.ps1 first to create the installer."
    exit 1
}

# Test 2: Check if file is actually an executable
Run-Test "File is a Windows executable" {
    $file = Get-Item $InstallerFile
    return $file.Extension -eq ".exe"
}

# Test 3: Check minimum file size (should be at least 10MB for a bundled app)
$MinSize = 10MB
Run-Test "Installer has reasonable size (>10MB)" {
    $fileSize = (Get-Item $InstallerFile).Length
    return $fileSize -gt $MinSize
}

# Test 4: Check maximum file size (shouldn't be larger than 500MB for a reasonable app)
$MaxSize = 500MB
Run-Test "Installer size is reasonable (<500MB)" {
    $fileSize = (Get-Item $InstallerFile).Length
    return $fileSize -lt $MaxSize
}

# Test 5: Check if installer is digitally signed (optional, may not be signed in dev)
Run-Test "Check digital signature (optional)" {
    $signature = Get-AuthenticodeSignature $InstallerFile
    if ($signature.Status -eq "Valid") {
        return $true
    } else {
        Write-Warn-Custom "Installer is not digitally signed (this is OK for development)"
        return $true  # Don't fail the test, just warn
    }
}

# Test 6: Verify PE header is valid
Run-Test "PE header is valid" {
    try {
        $bytes = [System.IO.File]::ReadAllBytes($InstallerFile)
        # Check for MZ header (PE executable)
        return ($bytes[0] -eq 0x4D -and $bytes[1] -eq 0x5A)
    } catch {
        return $false
    }
}

# Test 7: Check for Inno Setup signature using strings
Run-Test "Contains Inno Setup signature" {
    $content = [System.IO.File]::ReadAllBytes($InstallerFile)
    $text = [System.Text.Encoding]::ASCII.GetString($content)
    return $text -match "Inno Setup"
}

# Test 8: Verify the file is not corrupted (can be read)
Run-Test "File can be read without errors" {
    try {
        $stream = [System.IO.File]::OpenRead($InstallerFile)
        $stream.Close()
        return $true
    } catch {
        return $false
    }
}

# Test 9: Check file attributes
Run-Test "File has normal attributes" {
    $file = Get-Item $InstallerFile
    return (-not $file.Attributes.HasFlag([System.IO.FileAttributes]::Hidden)) -and
           (-not $file.Attributes.HasFlag([System.IO.FileAttributes]::System))
}

# Test 10: Verify version info can be read
Run-Test "Version info is readable" {
    try {
        $versionInfo = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($InstallerFile)
        return $versionInfo -ne $null
    } catch {
        return $false
    }
}

# Summary
Write-Host ""
Write-Info "=========================================="
Write-Info "Test Results Summary"
Write-Info "=========================================="
Write-Info "Total tests: $TestCount"
Write-Pass "Passed: $PassCount"
if ($FailCount -gt 0) {
    Write-Fail "Failed: $FailCount"
} else {
    Write-Info "Failed: $FailCount"
}
Write-Host ""

# Display installer details
$fileSize = (Get-Item $InstallerFile).Length
$fileSizeFormatted = "{0:N2} MB" -f ($fileSize / 1MB)
$md5 = (Get-FileHash -Path $InstallerFile -Algorithm MD5).Hash
$sha256 = (Get-FileHash -Path $InstallerFile -Algorithm SHA256).Hash

Write-Info "Installer Details:"
Write-Info "  Location: $InstallerFile"
Write-Info "  Size: $fileSizeFormatted"
Write-Info "  MD5: $md5"
Write-Info "  SHA256: $sha256"
Write-Info "  Created: $((Get-Item $InstallerFile).CreationTime)"
Write-Info "  Modified: $((Get-Item $InstallerFile).LastWriteTime)"
Write-Host ""

# Overall result
if ($FailCount -eq 0) {
    Write-Pass "=========================================="
    Write-Pass "ALL TESTS PASSED!"
    Write-Pass "=========================================="
    Write-Info "The installer appears to be valid and ready for distribution."
    Write-Info "You can now run the installer to test the installation process."
    Write-Info "To test installation: Right-click $InstallerFile and select 'Run as administrator'"
    exit 0
} else {
    Write-Fail "=========================================="
    Write-Fail "SOME TESTS FAILED!"
    Write-Fail "=========================================="
    Write-Error-Custom "Please review the failures above and rebuild the installer if necessary."
    exit 1
}
