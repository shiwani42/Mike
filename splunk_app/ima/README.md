# Institutional Memory Agent — Splunk app

Captures SOC analyst reasoning at scale and turns it into a queryable institutional knowledge graph.

## Install

1. Copy this `ima/` directory into `C:\Program Files\Splunk\etc\apps\` (you need to do this from an **Administrator** PowerShell window — the sandbox can't reach Program Files).

   ```powershell
   Copy-Item -Recurse -Force `
     "C:\Users\shmishra\Documents\Splunk_agentic_ops\Splunk_agentic_ops\splunk_app\ima" `
     "C:\Program Files\Splunk\etc\apps\"
   ```

2. Restart Splunk:
   ```powershell
   & "C:\Program Files\Splunk\bin\splunk.exe" restart
   ```

3. Open Splunk Web → the **Institutional Memory Agent** app should appear in the Apps menu.

## What's in the box

- `default/collections.conf` — declares the three KV Store collections (`ima_annotations`, `ima_knowledge`, `ima_assets`). Splunk creates them automatically on startup if they don't exist.
- `default/commands.conf` — registers three custom search commands (Splunk SPL parser rejects underscores in command names, so no `_` here):
  - `| imaannotate alert_id="..." disposition="..." reason="..." [asset=...] [analyst=...]` — record an analyst note
  - `| imabuild` — cluster annotations + call local LLM (Ollama) for structured extraction
  - `| imaquery question="..."` — retrieve matching institutional knowledge
- `bin/_ima_common.py` — shared helpers (KV Store wrappers, LLM client). Talks to local Ollama at `http://localhost:11434` by default; override via env vars `IMA_OLLAMA_ENDPOINT` / `IMA_OLLAMA_MODEL`.
- `default/data/ui/views/ima_overview.xml` — Simple XML dashboard with the knowledge graph, contributor stats, and an interactive "ask the agent" panel.

## Autonomous knowledge-graph rebuild

The app ships a Modular Input (`bin/ima_autobuild.py`) that runs the cluster + LLM extraction loop on a configurable interval (default 5 min). When enabled, the institutional knowledge graph stays in sync with annotations without any manual `| imabuild` invocation — that's the "agentic ops" loop running inside Splunk.

Enable it from Splunk Web → **Settings → Data inputs → IMA Autobuild → New** (or edit the default stanza and flip `disabled = false`). Status events land in `index=_internal sourcetype=ima:autobuild`:

```spl
index=_internal sourcetype=ima:autobuild | head 10
```

## Demo flow inside Splunk Web

```spl
| imaannotate alert_id="NOTABLE-2024-09-21" disposition="false_positive" reason="Finance batch job again, Monday 6am" asset="acct-prod-01" event_type="failed_auth_burst"

| imabuild

| imaquery question="finance"
```

## Hackathon submission

Built for the Splunk Agentic Ops Hackathon, Security track. See the project root `README.md` for the full architecture and the CLI dev harness.
