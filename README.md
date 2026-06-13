# Institutional Memory Agent (`ima`)

A Splunk-native agent that watches SOC analyst behavior — which alerts they close, escalate, suppress, and *why* — and turns that accumulated reasoning into a structured, queryable institutional knowledge graph stored in Splunk's KV Store.

**Track**: Security  •  **Hackathon**: Splunk Agentic Ops

The core bet: existing SIEM tooling captures *events*; nobody captures *analyst reasoning*. When a senior analyst leaves, their mental model leaves with them. `ima` keeps it.

## What it actually does

```
analyst closes alert     →   ima asks "why?" (10-second prompt)
                              ↓
                          annotation lands in KV Store (ima_annotations)
                              ↓
        | imabuild  →   clusters by (event_type, disposition)
                          and calls Foundation-Sec-1.1-8B
                              ↓
                          structured knowledge entry in ima_knowledge
                              ↓
new analyst asks         →   | imaquery question="finance Monday"
"what do we know         →   returns: "Finance batch job triggers failed-auth
about X?"                       bursts every Monday 6am."  conf=1.0  ×3 evidence
```

## Quick start (collaborators — read this first)

**Prereqs**: Python 3.10+, [Splunk Enterprise](https://www.splunk.com/en_us/download/splunk-enterprise.html) running locally on `:8089`, [Ollama](https://ollama.com) for the local LLM.

```powershell
git clone <repo>
cd Splunk_agentic_ops
.\bootstrap.ps1                       # Windows. macOS/Linux: ./bootstrap.sh
notepad .env                          # paste your SPLUNK_TOKEN (see below)
.\.venv\Scripts\Activate.ps1
ima auth check
ima kv init
ima demo seed --clear
ima knowledge build                   # ~3 min on CPU
ima knowledge query "finance"
```

To get a Splunk auth token: Splunk Web → **Settings → Tokens → New Token**. User: `admin`, audience: anything, expires: 90+ days.

The bootstrap script creates `.venv`, installs the CLI in editable mode, copies `.env.example` to `.env`, and pulls the Ollama model if it isn't already.

## Install the Splunk app

The CLI is for development. The submission artifact is the **Splunk app** at `splunk_app/ima/`. Install it from an **Administrator** PowerShell:

```powershell
Copy-Item -Recurse -Force ".\splunk_app\ima" "C:\Program Files\Splunk\etc\apps\"
& "C:\Program Files\Splunk\bin\splunk.exe" restart
```

After restart, open Splunk Web → Apps → **Institutional Memory Agent** for the dashboard, and try the custom search commands directly:

```spl
| imaquery question="finance"

| imaannotate alert_id="NOTABLE-2024-09-21" disposition="false_positive" `
              reason="Finance batch job again, Monday 6am" `
              asset="acct-prod-01" event_type="failed_auth_burst"

| imabuild
```

## Repo layout

```
.
├── ima/                          # Python CLI (dev tool)
│   ├── cli.py                    #   Typer entrypoint
│   ├── config.py                 #   .env loader
│   ├── splunk_client.py          #   splunk-sdk Service
│   ├── kvstore.py                #   KV Store helpers
│   ├── llm/foundation_sec.py     #   Ollama / Splunk-hosted client
│   └── commands/                 #   auth, kv, alerts, knowledge, demo
├── splunk_app/ima/               # Splunk app (submission artifact)
│   ├── bin/                      #   3 custom search commands
│   ├── default/                  #   collections, commands, transforms, dashboard XML
│   └── README.md
├── bootstrap.ps1 / bootstrap.sh  # one-command collaborator setup
├── pyproject.toml                # installs the `ima` console script
├── .env.example                  # config template; .env is gitignored
├── ARCHITECTURE.md               # data model, design choices, why-not-SOAR
├── LICENSE                       # MIT
└── README.md                     # this file
```

## How it uses Splunk's AI stack

| Splunk surface | How `ima` uses it |
|---|---|
| **KV Store** | Three collections — `ima_annotations`, `ima_knowledge`, `ima_assets` — declared in `splunk_app/ima/default/collections.conf` and used as the persistence layer for the knowledge graph. |
| **Custom Search Commands** (Python SDK 3.0) | `\| imaannotate`, `\| imabuild`, `\| imaquery` — first-class SPL commands so any saved search, dashboard, or analyst can trigger IMA. |
| **Foundation-Sec-1.1-8B** | The extraction prompt + JSON schema target the Splunk-hosted Foundation-Sec model. Local dev runs against an Ollama-hosted Llama-3.1-8B stand-in (no GPU on the dev box); swap to the Splunk-hosted endpoint via a one-line `.env` change. |
| **Simple XML dashboards** | `ima_overview.xml` gives the SOC a single pane: contributor stats, disposition mix, knowledge table, and an interactive "ask the agent" input. |
| **MCP Server** *(stretch)* | The knowledge graph can be exposed as MCP tools (`ima_query_knowledge`, `ima_record_annotation`) so SAIA Agent Mode, Claude Desktop, and other external agents can query institutional memory natively. |

See **[ARCHITECTURE.md](ARCHITECTURE.md)** for the full design.

## Why this isn't a SOAR playbook

SOAR automates *actions* — block this IP, isolate this endpoint. IMA captures and queries *reasoning* — *why did the senior analyst close this kind of alert as a false positive last quarter?* Complementary surfaces, not substitutes.

## License

MIT — see [LICENSE](LICENSE).
