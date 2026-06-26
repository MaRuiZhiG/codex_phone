param(
    [string]$Version = "0.1.0",
    [string]$PythonExe = "",
    [switch]$Installer,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if ($Clean) {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue ".venv-release", "build", "dist"
}

function Resolve-Python {
    if ($PythonExe) {
        return $PythonExe
    }

    $Candidates = @(
        @{ Command = "py"; Args = @("-3.13") },
        @{ Command = "py"; Args = @("-3.12") },
        @{ Command = "py"; Args = @("-3.11") },
        @{ Command = "python"; Args = @() }
    )

    foreach ($Candidate in $Candidates) {
        $Command = $Candidate.Command
        $Args = $Candidate.Args
        try {
            & $Command @Args --version *> $null
            if ($LASTEXITCODE -eq 0) {
                return "$Command $($Args -join ' ')".Trim()
            }
        } catch {
        }
    }

    throw "Python 3.11+ was not found. Install Python from https://www.python.org/downloads/windows/ or pass -PythonExe C:\Path\python.exe"
}

function Invoke-Python {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    $Resolved = Resolve-Python
    $Parts = $Resolved.Split(" ", [System.StringSplitOptions]::RemoveEmptyEntries)
    $Command = $Parts[0]
    $PrefixArgs = @()
    if ($Parts.Count -gt 1) {
        $PrefixArgs = $Parts[1..($Parts.Count - 1)]
    }
    & $Command @PrefixArgs @Arguments
}

if (-not (Test-Path ".venv-release")) {
    Invoke-Python -m venv ".venv-release"
}

$Python = Join-Path $Root ".venv-release\Scripts\python.exe"

& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt
& $Python -m pip install "pyinstaller>=6,<7"

& $Python -m PyInstaller --noconfirm --clean "CodexPhone.spec"

$DistAppDir = Join-Path $Root "dist\CodexPhone"

@"
Codex Phone
===========

Start:
  Double-click CodexPhone.exe

The local admin page opens automatically:
  http://127.0.0.1:8787/admin

Phone access:
  Copy the tokenized mobile link from the admin page and open it on your phone.

Requirements:
  1. Windows
  2. Codex Desktop is installed and has been launched at least once
  3. Your PC and phone are on the same LAN, or ZeroTier / public access is configured

Stop:
  Double-click Stop-CodexPhone.bat

Logs and token:
  %USERPROFILE%\.codex-phone
"@ | Set-Content -Encoding UTF8 (Join-Path $DistAppDir "README.txt")

@"
@echo off
taskkill /IM CodexPhone.exe /F
pause
"@ | Set-Content -Encoding ASCII (Join-Path $DistAppDir "Stop-CodexPhone.bat")

$ReleaseDir = Join-Path $Root "release"
New-Item -ItemType Directory -Force $ReleaseDir | Out-Null

$ZipPath = Join-Path $ReleaseDir "CodexPhone-$Version-windows-x64.zip"
Remove-Item -Force -ErrorAction SilentlyContinue $ZipPath

Compress-Archive -Path (Join-Path $DistAppDir "*") -DestinationPath $ZipPath

Write-Host ""
Write-Host "Release package created:"
Write-Host $ZipPath
Write-Host ""
Write-Host "Test it with:"
Write-Host "  dist\CodexPhone\CodexPhone.exe"

if ($Installer) {
    & (Join-Path $PSScriptRoot "build-installer.ps1") -Version $Version
}
