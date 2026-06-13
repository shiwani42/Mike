# Bootstrap script for Windows / PowerShell collaborators.
# Run from the repo root:  .\bootstrap.ps1
#
# Prereqs (install these once, manually, BEFORE running this script):
#   - Python 3.10+              winget install Python.Python.3.13
#   - Splunk Enterprise         https://www.splunk.com/en_us/download/splunk-enterprise.html
#   - Ollama                    irm https://ollama.com/install.ps1 | iex
#
# This script does:
#   1. Creates a Python virtualenv at .venv
#   2. Installs the ima CLI + all dependencies (including mcp) in editable mode
#   3. Copies .env.example to .env if .env is missing
#   4. Pulls the default Ollama model if absent
#   5. Prints next steps
#
# After this script runs, you still need to:
#   - Edit .env with your SPLUNK_TOKEN
#   - Install the Splunk app via .\install_splunk_app.ps1 (needs Administrator)

$ErrorActionPreference = "Stop"

Write-Host "[1/5] Creating .venv ..." -ForegroundColor Cyan
if (-not (Test-Path .venv)) {
    py -3 -m venv .venv
}

Write-Host "[2/5] Installing ima (with mcp) in editable mode ..." -ForegroundColor Cyan
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
        Write-Host "  Pulling $model (~5 GB, takes a few minutes) ..." -ForegroundColor Yellow
        ollama pull $model
    }
} catch {
    Write-Host "  Ollama not reachable at http://localhost:11434. Install it from https://ollama.com/download/windows then run:" -ForegroundColor Red
    Write-Host "    ollama pull $model" -ForegroundColor Red
}

Write-Host "[5/5] Done." -ForegroundColor Green
Write-Host ""
Write-Host "=== Next steps ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "A. Configure auth + populate the knowledge graph (in this terminal):" -ForegroundColor Yellow
Write-Host "   1. notepad .env                            # paste SPLUNK_TOKEN (Splunk Web -> Settings -> Tokens -> New Token)"
Write-Host "   2. .\.venv\Scripts\Activate.ps1            # activate the venv"
Write-Host "   3. ima auth check                          # verify Splunk REST connectivity"
Write-Host "   4. ima kv init                             # create the KV Store collections"
Write-Host "   5. ima demo seed --clear                   # seed ~10 realistic annotations"
Write-Host "   6. ima knowledge build                     # cluster via LLM (~3 min on CPU)"
Write-Host "   7. ima knowledge query 'finance'           # ask the agent"
Write-Host ""
Write-Host "B. Install the Splunk app (needs Administrator PowerShell):" -ForegroundColor Yellow
Write-Host "   - Open PowerShell as Administrator, cd to this repo, run:"
Write-Host "       .\install_splunk_app.ps1"
Write-Host "   - Then open http://localhost:8000 -> Apps -> Institutional Memory Agent"
Write-Host ""
Write-Host "C. (Optional) Expose IMA to Claude Desktop or any MCP client:" -ForegroundColor Yellow
Write-Host "   - Add to %APPDATA%\Claude\claude_desktop_config.json:"
Write-Host '       { "mcpServers": { "ima": { "command": "<repo>\\.venv\\Scripts\\python.exe",'
Write-Host '                                  "args": ["-m", "ima.cli", "mcp", "serve"] } } }'
Write-Host "   - Or run a standalone MCP HTTP server:  ima mcp serve --http"
Write-Host ""
Write-Host "See README.md and ARCHITECTURE.md for the full picture." -ForegroundColor Cyan
