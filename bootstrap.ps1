# Bootstrap script for Windows / PowerShell collaborators.
# Run from the repo root:  .\bootstrap.ps1
#
# Prereqs (install these once, manually):
#   - Python 3.10+   (winget install Python.Python.3.13)
#   - Splunk Enterprise running locally on https://localhost:8089
#   - Ollama         (irm https://ollama.com/install.ps1 | iex)
#
# This script does:
#   1. Creates a Python virtualenv at .venv
#   2. Installs the ima CLI + dependencies in editable mode
#   3. Copies .env.example to .env if .env is missing
#   4. Pulls the default Ollama model if absent
#   5. Prints next steps

$ErrorActionPreference = "Stop"

Write-Host "[1/5] Creating .venv ..." -ForegroundColor Cyan
if (-not (Test-Path .venv)) {
    py -3 -m venv .venv
}

Write-Host "[2/5] Installing ima in editable mode ..." -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .\.venv\Scripts\python.exe -m pip install -e . --quiet

Write-Host "[3/5] Configuring .env ..." -ForegroundColor Cyan
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "  Created .env from .env.example. Edit it and set SPLUNK_TOKEN." -ForegroundColor Yellow
} else {
    Write-Host "  .env already exists; leaving it alone." -ForegroundColor DarkGray
}

Write-Host "[4/5] Checking Ollama model ..." -ForegroundColor Cyan
$model = "llama3.1:8b-instruct-q4_K_M"
try {
    $tags = (Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 3).Content | ConvertFrom-Json
    if ($tags.models.name -contains $model) {
        Write-Host "  Model $model already pulled." -ForegroundColor DarkGray
    } else {
        Write-Host "  Pulling $model (this is ~5GB, takes a few minutes) ..." -ForegroundColor Yellow
        ollama pull $model
    }
} catch {
    Write-Host "  Ollama not reachable at http://localhost:11434. Install it from https://ollama.com/download/windows then run:" -ForegroundColor Red
    Write-Host "    ollama pull $model" -ForegroundColor Red
}

Write-Host "[5/5] Done." -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. notepad .env                           # paste SPLUNK_TOKEN (Splunk Web -> Settings -> Tokens -> New Token)"
Write-Host "  2. .\.venv\Scripts\Activate.ps1           # activate the venv"
Write-Host "  3. ima auth check                          # verify Splunk REST connectivity"
Write-Host "  4. ima kv init                             # create the KV Store collections"
Write-Host "  5. ima demo seed --clear                   # seed ~10 realistic annotations"
Write-Host "  6. ima knowledge build                     # cluster annotations through the LLM"
Write-Host "  7. ima knowledge query 'finance'           # ask the agent"
Write-Host ""
Write-Host "To install the Splunk app, see splunk_app/ima/README.md." -ForegroundColor Cyan
