param(
    [string]$Version = "0.1.0",
    [ValidateSet("Native", "Inno")]
    [string]$Backend = "Native",
    [string]$ISCC = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

function Resolve-ISCC {
    if ($ISCC) {
        return $ISCC
    }

    $Candidates = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )

    foreach ($Candidate in $Candidates) {
        if (Test-Path -LiteralPath $Candidate) {
            return $Candidate
        }
    }

    $FromPath = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($FromPath) {
        return $FromPath.Source
    }

    throw "Inno Setup 6 compiler was not found. Install it with: winget install --id JRSoftware.InnoSetup -e"
}

$ReleaseDir = Join-Path $Root "release"
New-Item -ItemType Directory -Force $ReleaseDir | Out-Null

if (-not (Test-Path "dist\CodexPhone\CodexPhone.exe")) {
    throw "dist\CodexPhone\CodexPhone.exe was not found. Run scripts\build-release.ps1 first."
}

if ($Backend -eq "Inno") {
    $Compiler = Resolve-ISCC

    & $Compiler `
        "/DMyAppVersion=$Version" `
        "/DSourceDir=$Root\dist\CodexPhone" `
        "/DOutputDir=$ReleaseDir" `
        "installer\CodexPhone.iss"

    Write-Host ""
    Write-Host "Installer created:"
    Write-Host (Join-Path $ReleaseDir "CodexPhoneSetup-$Version-windows-x64.exe")
    exit 0
}

$PayloadDir = Join-Path $Root "build\installer"
New-Item -ItemType Directory -Force $PayloadDir | Out-Null

$PayloadZip = Join-Path $PayloadDir "CodexPhone-payload.zip"
Remove-Item -Force -ErrorAction SilentlyContinue $PayloadZip
Compress-Archive -Path (Join-Path $Root "dist\CodexPhone\*") -DestinationPath $PayloadZip

$InstallerVersionFile = Join-Path $PayloadDir "installer-version.txt"
Set-Content -Encoding ASCII -NoNewline -Path $InstallerVersionFile -Value $Version

$Python = Join-Path $Root ".venv-release\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw ".venv-release was not found. Run scripts\build-release.ps1 first."
}

$env:CODEX_PHONE_INSTALLER_VERSION = $Version
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "CodexPhoneSetup-$Version-windows-x64" `
    --icon "assets\app-icon.ico" `
    --add-data "$PayloadZip;payload" `
    --add-data "$InstallerVersionFile;." `
    "app\windows_installer.py"
Remove-Item Env:\CODEX_PHONE_INSTALLER_VERSION -ErrorAction SilentlyContinue

$BuiltInstaller = Join-Path $Root "dist\CodexPhoneSetup-$Version-windows-x64.exe"
$FinalInstaller = Join-Path $ReleaseDir "CodexPhoneSetup-$Version-windows-x64.exe"
Move-Item -Force $BuiltInstaller $FinalInstaller
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $Root "CodexPhoneSetup-$Version-windows-x64.spec")

Write-Host ""
Write-Host "Installer created:"
Write-Host $FinalInstaller
