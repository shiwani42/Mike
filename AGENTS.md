# AGENTS.md - Institutional Memory Agent

Brief for AI coding agents (Claude Code, Cursor, GitHub Copilot, etc.) picking up
this project. Read top-to-bottom before making changes. The gotchas section
below encodes the debugging we already went through - skip it and you'll relearn
each one.

For the public-facing project overview, see `README.md`. For the design diagram
and data flow, see `ARCHITECTURE.md`. This file is the operational handoff.

---

## 0. One-paragraph orientation

`ima` ("Institutional Memory Agent") is a Splunk-native system that captures
SOC analyst reasoning on alert closures, persists it to Splunk KV Store, and
exposes the resulting institutional knowledge graph through four surfaces:
a Python CLI, custom search commands inside Splunk, a Splunk modular input
that runs autonomously, and a Model Context Protocol (MCP) server for
external AI agents. The LLM extraction step is built against Splunk's
hosted Foundation-Sec-1.1-8B; locally it runs Llama-3.1-8B-Instruct via
Ollama as a stand-in (swap is a one-line `.env` change).

See section 7 for the full coding/writing conventions to follow on any change.

---

## 1. Run it locally (commands that always work)

```powershell
# from repo root, after bootstrap
.\.venv\Scripts\Activate.ps1

ima auth check                                       # verify Splunk REST is reachable
ima kv init                                          # create KV Store collections
ima demo seed --clear                                # wipe + seed 10 realistic annotations
ima knowledge build                                  # cluster via Ollama, ~3 min on CPU
ima knowledge query "finance Monday"                 # semantic-search the graph
ima knowledge about acct-prod-01                     # per-asset memory card
ima alerts watch --interval 0 --earliest -10m        # single-pass poll for unannotated alerts
ima mcp serve                                        # stdio MCP server (Claude Desktop)
ima mcp serve --http --port 8765                     # HTTP MCP server (remote agents)
```

The Splunk app side (after editing files in `splunk_app/ima/`):

```powershell
# elevated PowerShell:
.\install_splunk_app.ps1                             # copies app, restarts splunkd
```

To verify the live loop end-to-end, run `_verify_loop.py` (gitignored scratch script).
To do a pre-recording health check, run `_verify_preflight.py` (also gitignored).

---

## 2. Repository layout

```
.
├── ima/                                # Python CLI package (the dev surface)
│   ├── __init__.py
│   ├── cli.py                          # Typer entry, registers all subcommands
│   ├── config.py                       # .env loader -> Settings dataclass
│   ├── splunk_client.py                # cached splunklib Service factory
│   ├── kvstore.py                      # collection init + insert/query helpers
│   ├── asset_memory.py                 # per-asset card aggregation
│   ├── mcp_server.py                   # FastMCP server + 5 @mcp.tool() definitions
│   ├── llm/
│   │   ├── __init__.py
│   │   └── foundation_sec.py           # extract() + embed() + cosine_similarity() + SYSTEM_PROMPT
│   └── commands/
│       ├── auth.py                     # ima auth check
│       ├── kv.py                       # ima kv init|ls
│       ├── alerts.py                   # ima alerts list|watch|annotate
│       ├── demo.py                     # ima demo seed
│       ├── knowledge.py                # ima knowledge build|query|about
│       └── mcp.py                      # ima mcp serve [--http]
│
├── splunk_app/ima/                     # Splunk app (the production surface)
│   ├── default/
│   │   ├── app.conf                    # launcher metadata; author = "Shiwani Mishra, Saurabh Gupta"
│   │   ├── commands.conf               # SPL command stanzas (NO underscores in names!)
│   │   ├── collections.conf            # 3 KV Store collections declared
│   │   ├── transforms.conf             # KV Store lookup definitions (required for inputlookup)
│   │   ├── inputs.conf                 # ima_autobuild modular input (enabled by default)
│   │   ├── savedsearches.conf          # ima_simulate_alerts (cron */5, enabled)
│   │   └── data/ui/
│   │       ├── nav/default.xml
│   │       └── views/ima_overview.xml  # Simple XML dashboard, 4 row groups
│   ├── bin/
│   │   ├── _ima_common.py              # shared helpers; MIRRORS ima/asset_memory.py + ima/llm/foundation_sec.py
│   │   ├── ima_query.py                # CSC: | imaquery question="..." (semantic + substring fallback)
│   │   ├── ima_annotate.py             # CSC: | imaannotate alert_id="..." ...
│   │   ├── ima_build.py                # CSC: | imabuild
│   │   ├── ima_aboutasset.py           # CSC: | imaaboutasset asset="..."
│   │   ├── ima_ping.py                 # CSC: | imaping  (smoke test)
│   │   ├── ima_autobuild.py            # Modular Input script (Script subclass)
│   │   └── lib/                        # VENDORED deps, required (see Gotcha #2)
│   │       ├── splunklib/              # full splunklib SDK 3.0 source
│   │       └── splunk_sdk-3.0.0.dist-info/   # metadata, REQUIRED (see Gotcha #3)
│   ├── metadata/default.meta           # exports: commands, transforms, lookups, modular_inputs, savedsearches, views, nav
│   ├── README/inputs.conf.spec         # modular-input spec
│   └── README.md
│
├── bootstrap.ps1                       # Windows collaborator one-command setup
├── bootstrap.sh                        # macOS/Linux equivalent
├── install_splunk_app.ps1              # elevated copy + restart
├── pyproject.toml                      # ima console_scripts entry
├── .env.example                        # config template; .env is gitignored
├── README.md                           # public-facing
├── ARCHITECTURE.md                     # public-facing design doc
├── LICENSE                             # MIT, Shiwani Mishra + Saurabh Gupta
└── AGENTS.md                           # this file
```

---

## 3. Data model

Three KV Store collections, declared in `splunk_app/ima/default/collections.conf`
AND auto-created by `ima kv init` from the CLI side.

**`ima_annotations`** - raw analyst notes captured on alert closure.
```
alert_id, event_type, analyst, disposition, reason, source_ip, asset, created_at
```

**`ima_knowledge`** - structured institutional knowledge produced by clustering
annotations by `(event_type, disposition)` and passing each cluster through
the LLM extractor.
```
topic ("event_type :: disposition"), summary, evidence_count, confidence, tags, updated_at
```

**`ima_assets`** - declared but **currently unused** as a separate write target.
Per-asset cards are computed on the fly by `build_asset_card()` from
annotations + knowledge entries. If you add asset-level persistence later,
write here.

Confidence calibration (from the prompt):
- 3+ analysts agree -> 0.90-1.00
- 2 analysts agree -> 0.65-0.90
- 1 observation -> 0.10-0.35 (not yet a pattern)

---

## 4. Surfaces and where their logic lives

All four surfaces read the same KV Store, so they stay in lockstep.

| Surface | Entry point | Reads/writes KV via |
|---|---|---|
| CLI | `ima/cli.py` -> `ima/commands/*.py` | `ima/kvstore.py` (uses cached `splunklib.client.Service`) |
| Splunk CSC | `splunk_app/ima/bin/ima_*.py` | `splunk_app/ima/bin/_ima_common.py` -> `self.service` (provided by splunklib SDK 3.0) |
| Modular Input | `splunk_app/ima/bin/ima_autobuild.py` | same `_ima_common.py` helpers, `self.service` |
| MCP server | `ima/mcp_server.py` | same `ima/kvstore.py` + `ima/asset_memory.py` |

**Shared logic is DUPLICATED, not imported**: the Splunk-side `_ima_common.py`
re-implements `build_asset_card()`, `embed()`, `cosine_similarity()`, the
LLM extractor, and the `SYSTEM_PROMPT`. The CSC files cannot import from
the `ima/` Python package because they run inside Splunk's bundled Python
(3.9) with their own sys.path, vendoring splunklib only.

**When you change extraction logic, prompts, or helper algorithms, update BOTH
copies:** `ima/llm/foundation_sec.py` AND `splunk_app/ima/bin/_ima_common.py`.

---

## 5. External dependencies and versions

- **Python**: 3.10+ for the venv. Splunk CSCs run under **Splunk's bundled
  Python 3.9** (UI uses 3.13 - they're separate interpreters).
- **Splunk Enterprise 10.4** with Developer License (10 GB/day). KV Store, custom
  search commands, modular inputs, dashboards, saved searches all required.
  Splunkbase apps installed: `Splunk_Security_Essentials` (mostly unused; ES is gated).
- **Ollama** on localhost:11434 with two models:
  - `llama3.1:8b-instruct-q4_K_M` (extraction)
  - `nomic-embed-text` (embeddings for semantic search)
- **Python packages** (pyproject.toml): typer, rich, python-dotenv, splunk-sdk>=2.0,
  httpx, mcp>=1.0.

---

## 6. GOTCHAS (read every one before touching Splunk code)

Each of these cost a debug cycle. If you're changing the Splunk app, you will
hit them. They are NOT documented in the public README on purpose.

### G1. SPL custom search command names MUST NOT contain underscores

Splunk's SPL parser tokenizes `_` as the leading character of internal fields
(`_time`, `_raw`, `_indextime`). A stanza named `[ima_query]` causes the
parser to read `| ima_query` as `| ima` (unknown command) + `_query` (field
ref), returning `HTTP 400 Unknown search command 'ima'`. **Stanza names
must be lowercase concatenated** (`imaquery`, `imaannotate`, `imabuild`,
`imaaboutasset`, `imaping`, `imaautobuild`).

Filenames are unrestricted: `commands.conf` can point `filename = ima_query.py`
even though the stanza is `[imaquery]`. Don't try to make them match.

### G2. Splunk 10.x does NOT bundle splunklib for CSCs

CSC scripts that `import splunklib.searchcommands` fail with the maximally
unhelpful `error code 1` and produce **no Python traceback** anywhere
indexable. Splunk's bundled Python 3.9 has the `splunk` package (web app
internals) but not `splunklib`. **You must vendor splunklib into
`splunk_app/ima/bin/lib/splunklib/`** by copying from the venv:

```bash
cp -r .venv/Lib/site-packages/splunklib splunk_app/ima/bin/lib/
find splunk_app/ima/bin/lib -type d -name __pycache__ -exec rm -rf {} +
```

Each CSC script needs:
```python
import os, sys
_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, "lib"))   # splunklib
sys.path.insert(0, _here)                         # _ima_common
```

### G3. The splunk_sdk-*.dist-info folder is ALSO required

splunklib calls `importlib.metadata.version("splunk-sdk")` during the MCP
protocol handshake. Without the dist-info folder on sys.path, CSCs fail with
`PackageNotFoundError: splunk-sdk`. So vendoring is two folders:
```
splunk_app/ima/bin/lib/splunklib/
splunk_app/ima/bin/lib/splunk_sdk-3.0.0.dist-info/
```

### G4. commands.conf MUST use `chunked = true` for SDK 3.x

Old v1 protocol fields (`generating`, `enableheader`, `outputheader`,
`supports_getinfo`, `requires_srinfo`) are unsupported by splunklib 3.0.
Each CSC stanza needs only:
```ini
[imaquery]
filename = ima_query.py
chunked = true
python.version = python3
local = true
```

Without `chunked = true` the error is `Command imaquery appears to be
statically configured for search command protocol version 1 and static
configuration is unsupported by splunklib.searchcommands.`

### G5. KV Store namespace matters - `.env` SPLUNK_APP must be `ima`

KV Store collections in Splunk are namespaced by `(app, owner)`. The CLI
connects with `app=ima` (from `.env`); the Splunk app's CSCs run under
`app=ima`. **If `.env` has `SPLUNK_APP=search`, the CLI writes data into
the search namespace and the Splunk dashboard reads from a different empty
collection.** The `.env.example` correctly defaults to `ima`. Watch for this
when a collaborator's dashboard appears empty - check the namespace first.

### G6. The Splunk app re-install needs Administrator

`C:\Program Files\Splunk\etc\apps\` is ACL-protected. Use
`install_splunk_app.ps1` from an elevated PowerShell. The script's
elevation guard exits cleanly if not run as admin. Splunk service restart
takes ~60 seconds. The sandbox shell this AGENTS.md is read from cannot
elevate - you have to ask the user to run the install.

### G7. Use `self.service` in CSCs, not hand-rolled REST clients

splunklib SDK 3.0 automatically populates `self.service` on `GeneratingCommand`
subclasses, scoped to the right namespace and session key. Don't try to
build your own with `splunklib.client.connect(...)` from the search
metadata - it works but adds complexity and namespace-drift bugs.

### G8. Microsoft Store-packaged Claude Desktop ignores stdio MCP

The Store-packaged Claude Desktop (under `C:\Program Files\WindowsApps\Claude_*\`)
does NOT honor the `mcpServers` block in `claude_desktop_config.json`. It uses a
DXT (Desktop Extensions) connector system tied to the user's Anthropic
account/org, gated by an allowlist (`dxt:allowlistEnabled`). For MCP testing,
use Claude Code (the CLI) via `.mcp.json` at the project root, or the
standalone Claude Desktop installer from claude.ai/download (not the Store).

The Store sandbox config lives under the package's LocalCache directory at
`%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude_desktop_config.json`,
but writing there has no effect on MCP loading.

### G9. Modular Input output file is fragile

Splunk dispatches modular inputs as subprocess invocations and writes their
stdout into the configured index. If the script crashes during import, **no
traceback** reaches the index - check `index=_internal sourcetype=splunkd
component=ExecProcessor` or `var/log/splunk/python.log` for the real error.
Same vendoring + sys.path rules as CSCs apply.

### G10. Ollama CPU inference is slow

The `knowledge build` step makes one LLM call per cluster (~5 calls for the
seeded data). On Intel Iris Xe (no discrete GPU), each call takes 20-60s.
The full build is 2-5 min. For demos, don't run `imabuild` live; show the
result panel from a recent autobuild tick instead.

---

## 7. Coding and writing conventions (encoded user preferences)

These are non-negotiable. Each was a correction from the user; don't relitigate.

### Writing
- **No em dashes** (`—` / U+2014) anywhere - docs, prose, code comments. Use
  hyphens, commas, or periods.
- **No hackathon/submission framing in public docs** - README, ARCHITECTURE,
  app.conf descriptions. The repo reads as a standalone project.
- **No institutional affiliation** in public-facing metadata. Names only.
- **Two equal contributors**: Shiwani Mishra and Saurabh Gupta. Credit both
  in LICENSE, app.conf author, pyproject.toml `[project.authors]`, README.
- **No Co-Authored-By Claude / AI attribution** in commit messages or PR
  bodies. Phrase commits in the user's voice.
- **No emojis** unless the user explicitly asks for them. Rich panel titles
  with `:bookmark_tabs:` etc. crash on Windows cp1252 console.

### Workflow
- Use `Edit`/`Write` tools directly. Prefer editing over re-writing whole files.
- Use `Grep`/`Glob` over `find`/`grep` shell calls.
- For commits: stage with `git add .` (respects gitignore), commit with a
  generic message that doesn't mention preference cleanups (e.g. "Light
  prose cleanup across docs" rather than "Remove em dashes").
- Don't ask multi-option polls when you have a clear recommendation. Just
  announce: "Recommendation X because Y - proceeding."
- When in doubt about a side change, do it but mention briefly.

### Code
- Python 3.10+ syntax allowed in `ima/` (uses `from __future__ import annotations`).
- Python 3.9-compatible only in `splunk_app/ima/bin/` (no `dict[str, Any]`
  return annotations at runtime; use `Dict` from typing if you need it; or
  rely on `from __future__ import annotations` which our files already do).
- Stdlib only in `bin/` unless you also vendor the dep. We use
  `urllib.request` in `_ima_common.py` instead of `httpx` to avoid
  vendoring another package.
- Splunk CSC chunked protocol = `chunked = true` in commands.conf.

---

## 8. How to make common changes

### Add a new MCP tool
1. Add a `@mcp.tool()` decorated function in `ima/mcp_server.py`.
2. Restart any running `ima mcp serve` and any MCP client.
3. No Splunk app change needed.

### Add a new CLI command
1. New file in `ima/commands/<name>.py` with a Typer sub-app.
2. Register it in `ima/cli.py`: import + `app.add_typer(...)`.
3. `pip install -e .` if you changed `pyproject.toml`.

### Add a new custom search command
1. New file in `splunk_app/ima/bin/<name>.py`.
2. Add a stanza in `splunk_app/ima/default/commands.conf` (NO UNDERSCORES,
   `chunked = true`, `python.version = python3`, `local = true`).
3. Use the standard CSC boilerplate:
   ```python
   import os, sys
   _here = os.path.dirname(os.path.abspath(__file__))
   sys.path.insert(0, os.path.join(_here, "lib"))
   sys.path.insert(0, _here)
   from splunklib.searchcommands import Configuration, GeneratingCommand, Option, dispatch
   from _ima_common import KV_KNOWLEDGE, kv_query  # or whatever
   ```
4. Update `splunk_app/ima/metadata/default.meta` if you need a different
   export scope (we already export commands system-wide).
5. Run `.\install_splunk_app.ps1` in elevated PowerShell.

### Change the extraction prompt
Update **both** files (they're separate copies):
- `ima/llm/foundation_sec.py` -> `_SYSTEM_PROMPT`
- `splunk_app/ima/bin/_ima_common.py` -> `SYSTEM_PROMPT`

Then re-seed and rebuild: `ima demo seed --clear && ima knowledge build`.
The autobuild modular input will use the new prompt on its next tick (after
re-install + restart).

### Change the SPL surface that `ima alerts watch` polls
Edit `DEFAULT_WATCH_SPL` in `ima/commands/alerts.py`. The current surface
is `sourcetype="ima:alert" OR (index=_audit action=alert_fired) OR (index=notable)`.

### Swap from Ollama Llama-3.1 to real Foundation-Sec
Set `LLM_PROVIDER=splunk_hosted` in `.env`, fill in `FOUNDATION_SEC_ENDPOINT`
and `FOUNDATION_SEC_API_KEY`. The abstraction in `ima/llm/foundation_sec.py`
`extract()` routes accordingly. The Splunk-side `_ima_common.py` calls
Ollama only - it needs the same swap if you migrate.

### Add another KV Store collection
1. `splunk_app/ima/default/collections.conf` - add `[<name>] field.X = string`.
2. `splunk_app/ima/default/transforms.conf` - add the lookup definition.
3. `ima/kvstore.py` - add to `init_collections()`.
4. Update `.env.example` if collection name is configurable.
5. Re-install Splunk app + restart.

---

## 9. Testing / verification

There is no formal test suite yet. Verification scripts (gitignored):

- `_verify_loop.py` - full live-loop check (saved search, CSCs, autobuild, alerts).
- `_verify_preflight.py` - quick health check before demoing/recording.
- `_test_csc.py` - throwaway script slot; recreated as needed for ad-hoc tests.

If you add a new feature, write a smoke test alongside it as a `_test_*.py`
or `_verify_*.py` script. They'll be gitignored automatically.

To verify a Splunk app change without redeploying every time:
- KV Store changes (collections.conf): a `splunk restart` IS needed.
- Custom search command code changes: usually picked up by next invocation;
  if not, `splunk restart` or restart just the search head.
- Dashboard XML changes: Ctrl-Shift-R in the browser is enough.
- savedsearches.conf / inputs.conf: restart needed.

---

## 10. Project memory (Claude Code only)

If you're running as a Claude Code agent on the machine this project was
originally developed on, there's a persistent per-project memory store under
`~/.claude/projects/<workspace-slug>/memory/`. It contains both reference
notes (the same gotchas captured in section 6) and `feedback_*.md` files
encoding the user's preferences (also reflected in section 7).

Other agents (Cursor, Copilot, fresh Claude Code on another machine, etc.)
don't have access to that memory and should rely on this AGENTS.md instead.
This file is intentionally a superset of the memory contents.

---

## 11. Git, repo, and remote

- Branch: `main`. Push targets `origin/main`.
- GPG signing is available on the user's git config but NOT enabled by default
  (`commit.gpgsign` not set). Commits go out unsigned. Don't touch the global
  git config without the user asking.
- Author identity comes from `git config user.name` / `user.email`. Don't
  override per-commit.
- For pushes: stage with `git add .`, commit with `git commit -m "..."`
  (no Co-Authored-By trailer), `git push origin main`.

---

## 12. What is intentionally NOT here

These were considered and deliberately deferred. Don't pick them up
spontaneously - the user has time to decide.

- **Splunk AI Toolkit (AITK) integration** - `| fit foundation_sec ...` style.
  Too much setup, marginal demo value.
- **SOAR playbook integration** - external dependency, not reproducible.
- **Cisco Talos threat intel feeds** - requires Cisco backend access.
- **Splunk MCP TA (Technical Add-on)** - for self-observability of agent
  activity. Meta-cool but niche.
- **ITSI EventIQ feedback loop** - depends on ITSI install.
- **Multi-analyst conflict detection** - flagging where analysts gave
  different dispositions to the same alert type. Was on the stretch list,
  not built.
- **Real Foundation-Sec-1.1-8B via Hugging Face transformers** - would
  inoculate against the "you used a Llama stand-in" critique. Not built.

If the user asks for any of these, scope them carefully - each is more
work than it looks.

---

## 13. References

- `README.md` - public-facing, what the project is + quick start.
- `ARCHITECTURE.md` - design diagram, surface map, data flow.
- `splunk_app/ima/README.md` - Splunk app installation specifics.
- `DEMO.md` - 3-minute demo script (gitignored, internal).
- `ima/mcp_server.py` - canonical list of MCP tools and their docstrings.

End of AGENTS.md.
