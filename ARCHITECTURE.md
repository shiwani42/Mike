# Architecture - Institutional Memory Agent

## The problem in one paragraph

When a senior SOC analyst with six years of tenure leaves a team, they take with them an irreplaceable mental model: which alerts are owned by which scheduled jobs, which executives travel internationally, which subnets host sanctioned pentests, which correlation rules were never updated after the network was re-segmented in 2019. None of this lives in a system. It lives in human heads. Existing SIEM tooling captures *events*. Nobody captures *analyst reasoning*. IMA does.

## The shape

```
                              ┌──────────────────────────────────────┐
                              │   Analyst (Splunk Web, SOAR, CLI,    │
                              │   new-hire onboarding)               │
                              └─────┬─────────────────────┬──────────┘
        alert closes / fires        │                     │  "what do we know about X?"
        → 10-sec annotation         ▼                     ▼
                              ┌─────────────────┐   ┌─────────────────────┐
                              │ ima alerts watch│   │ | imaquery         │
                              │ (CLI prompt)    │   │  (custom search cmd)│
                              │ | imaannotate  │   │ ima knowledge query │
                              │  (search cmd)   │   │  (CLI)              │
                              └────────┬────────┘   └──────────▲──────────┘
                                       │                       │
                                       ▼                       │
                  ┌──────────────────────────────────────────┐
                  │   Splunk KV Store (instance-wide)        │
                  │                                          │
                  │   ima_annotations   ima_knowledge        │
                  │   ima_assets                             │
                  └────────────────────────▲─────────────────┘
                                           │
                            ┌──────────────┴───────────────┐
                            │  | imabuild  /  knowledge   │
                            │   build (CLI)                │
                            │                              │
                            │   cluster by (event_type,    │
                            │   disposition) → call local  │
                            │   LLM → write structured     │
                            │   knowledge entries          │
                            └──────────────┬───────────────┘
                                           │
                                           ▼
                            ┌──────────────────────────────┐
                            │   Foundation-Sec-1.1-8B      │
                            │   (Ollama stand-in for dev;  │
                            │   swap to Splunk-hosted via  │
                            │   .env one-line change)      │
                            └──────────────────────────────┘
```

## What lives where

| Component | Location | Role |
|---|---|---|
| Python CLI | `ima/` package at repo root, installed in `.venv` | Dev iteration - analyst-side `annotate`/`watch`/`query`, batch `build` |
| Splunk app | `splunk_app/ima/` (copied to `etc/apps/ima/`) | Production deployment - custom search commands `\| imaannotate`, `\| imabuild`, `\| imaquery`, `\| imaaboutasset`, plus `\| imaping` smoke-test, Simple XML dashboard, `ima_simulate_alerts` saved search that fires synthetic alerts every 5 min, vendored splunklib at `bin/lib/` |
| MCP server | `ima/mcp_server.py` (run via `ima mcp serve`) | Exposes the knowledge graph as MCP tools for Claude Desktop, SAIA Agent Mode, and any MCP-compatible AI client |
| Modular Input | `splunk_app/ima/bin/ima_autobuild.py` (enable in Splunk Web) | Autonomous agentic loop: re-runs the cluster + LLM extraction every interval seconds so the knowledge graph stays current without manual intervention |
| KV Store collections | Splunk instance, `ima` app namespace | Persistence - three collections declared in `collections.conf` |
| LLM extractor | `ima/llm/foundation_sec.py` (CLI side) and `splunk_app/ima/bin/_ima_common.py` (app side) | Calls local Ollama by default; abstraction layer means swapping to Splunk-hosted Foundation-Sec is a config change |

## Data model

**ima_annotations** - raw analyst notes against alert closures
```
alert_id, event_type, analyst, disposition, reason, source_ip, asset, created_at
```

**ima_knowledge** - clustered, structured institutional knowledge produced by the LLM
```
topic ("event_type :: disposition"), summary, evidence_count, confidence, tags, updated_at
```

**ima_assets** - per-asset behavioral exceptions (CISO travels internationally, batch jobs run Monday 6am, etc.) - populated as the graph matures
```
asset, owner, notes, behavioral_exceptions, updated_at
```

## Why the LLM call is a batch step, not a per-event call

The LLM doesn't need to fire on every alert closure - that would be expensive and add latency to the analyst's loop. Instead:

1. Analysts annotate freely (CLI prompt or `\| imaannotate`) - cheap, instant, persisted to KV Store.
2. `\| imabuild` (or `ima knowledge build` from the CLI) runs on demand or on a schedule (`cron`/saved search). It groups annotations by `(event_type, disposition)`, sends each cluster through Foundation-Sec for structured extraction, and writes one knowledge entry per cluster.
3. Confidence emerges from cluster size: 3+ pieces of evidence → confidence ~1.0 (stable institutional pattern); 1 piece → confidence ~0 (one-off observation, not yet institutional knowledge).

This is the central architectural choice: capture is cheap, synthesis is batched.

## Splunk AI surfaces in use

| Surface | How IMA uses it |
|---|---|
| **Splunk KV Store** | Three collections (`ima_annotations`, `ima_knowledge`, `ima_assets`) persist the knowledge graph at the Splunk instance level. |
| **Custom Search Commands** (Python SDK) | `\| imaannotate`, `\| imabuild`, `\| imaquery` make IMA scriptable from any Splunk search bar, dashboard, or saved search. |
| **Simple XML dashboards** | `ima_overview.xml` gives analysts a single pane: contributor stats, disposition mix, knowledge table, and an interactive "ask the agent" panel. |
| **Splunk Hosted Models (Foundation-Sec-1.1-8B)** | The extraction step is built against the Foundation-Sec prompt and JSON schema. Currently calls a local Ollama for dev (no GPU on the dev box); the abstraction switches to the Splunk Cloud Platform-hosted endpoint via a `.env` flag. |
| **MCP Server** | Standalone Python MCP server (`ima/mcp_server.py`) exposes four tools - `query_knowledge`, `record_annotation`, `list_recent_annotations`, `build_knowledge` - over stdio (Claude Desktop) or streamable-HTTP (remote agents). Lets SAIA Agent Mode, Claude Desktop, and autonomous SOAR playbooks query and update institutional memory through a standardized protocol, no Splunkbase install required. |

## Why not a SOAR playbook?

SOAR automates *actions* - block this IP, isolate this endpoint, ticket this case. IMA captures and queries *reasoning* - *why did the senior analyst close this kind of alert as a false positive last quarter?* These are complementary surfaces, not substitutes.
