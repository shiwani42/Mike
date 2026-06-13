#!/usr/bin/env bash
# Bootstrap script for macOS / Linux collaborators.
# Run from the repo root:  ./bootstrap.sh
#
# Prereqs (install these once, manually):
#   - Python 3.10+
#   - Splunk Enterprise running locally on https://localhost:8089
#   - Ollama:  curl -fsSL https://ollama.com/install.sh | sh

set -euo pipefail

echo "[1/5] Creating .venv ..."
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi

echo "[2/5] Installing ima in editable mode ..."
./.venv/bin/python -m pip install --upgrade pip --quiet
./.venv/bin/python -m pip install -e . --quiet

echo "[3/5] Configuring .env ..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  Created .env from .env.example. Edit it and set SPLUNK_TOKEN."
else
    echo "  .env already exists; leaving it alone."
fi

echo "[4/5] Checking Ollama model ..."
MODEL="llama3.1:8b-instruct-q4_K_M"
if curl -s -m 3 http://localhost:11434/api/tags | grep -q "$MODEL"; then
    echo "  Model $MODEL already pulled."
elif command -v ollama >/dev/null 2>&1; then
    echo "  Pulling $MODEL (this is ~5GB, takes a few minutes) ..."
    ollama pull "$MODEL"
else
    echo "  Ollama not found. Install it from https://ollama.com then run:"
    echo "    ollama pull $MODEL"
fi

echo "[5/5] Done."
echo
echo "Next steps:"
echo "  1. \$EDITOR .env                            # paste SPLUNK_TOKEN (Splunk Web -> Settings -> Tokens -> New Token)"
echo "  2. source .venv/bin/activate               # activate the venv"
echo "  3. ima auth check                           # verify Splunk REST connectivity"
echo "  4. ima kv init                              # create the KV Store collections"
echo "  5. ima demo seed --clear                    # seed ~10 realistic annotations"
echo "  6. ima knowledge build                      # cluster annotations through the LLM"
echo "  7. ima knowledge query 'finance'            # ask the agent"
echo
echo "To install the Splunk app, see splunk_app/ima/README.md."
