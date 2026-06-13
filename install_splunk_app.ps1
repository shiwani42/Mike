# Install the ima Splunk app into a local Splunk Enterprise install.
#
# This needs Administrator privileges (the etc/apps directory under
# C:\Program Files\Splunk is protected). Run from an elevated PowerShell:
#
#   1. Press Windows key, type "PowerShell"
#   2. Right-click "Windows PowerShell" -> "Run as administrator"
#   3. cd <repo root>
#   4. .\install_splunk_app.ps1
#
# Does:
#   - Verifies elevation + that Splunk Enterprise is installed
#   - Copies splunk_app/ima/ into <SPLUNK_HOME>\etc\apps\ima\
#   - Restarts Splunk so the new commands/collections/dashboard register
#   - Prints next steps

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script must run as Administrator." -ForegroundColor Red
    Write-Host "  Press Windows key, type 'PowerShell', right-click 'Windows PowerShell',"
    Write-Host "  pick 'Run as administrator', then re-run this script from the repo root."
    exit 1
}

$splunkHome = if ($env:SPLUNK_HOME) { $env:SPLUNK_HOME } else { "C:\Program Files\Splunk" }
$splunkExe = Join-Path $splunkHome "bin\splunk.exe"
$appsDir = Join-Path $splunkHome "etc\apps"
$appSource = Join-Path $PSScriptRoot "splunk_app\ima"

if (-not (Test-Path $splunkExe)) {
    Write-Host "ERROR: Splunk Enterprise not found at $splunkHome" -ForegroundColor Red
    Write-Host "  Install Splunk Enterprise first: https://www.splunk.com/en_us/download/splunk-enterprise.html"
    Write-Host "  Then re-run this script (or set `$env:SPLUNK_HOME if Splunk is elsewhere)."
    exit 1
}

if (-not (Test-Path $appSource)) {
    Write-Host "ERROR: app source not found at $appSource" -ForegroundColor Red
    Write-Host "  Run this script from the repo root (the directory that contains splunk_app/)."
    exit 1
}

Write-Host "[1/3] Copying ima Splunk app -> $appsDir" -ForegroundColor Cyan
Copy-Item -Recurse -Force $appSource $appsDir

Write-Host "[2/3] Restarting Splunk (this takes ~60 sec) ..." -ForegroundColor Cyan
& $splunkExe restart

Write-Host "[3/3] Done." -ForegroundColor Green
Write-Host ""
Write-Host "Open http://localhost:8000 -> Apps menu -> Institutional Memory Agent" -ForegroundColor Cyan
Write-Host "Or run from any SPL search bar:" -ForegroundColor Cyan
Write-Host "  | imaquery question=`"finance`""
Write-Host "  | imabuild"
