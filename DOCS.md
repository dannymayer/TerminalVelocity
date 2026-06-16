# TerminalVelocity – Application Documentation

## Table of contents

1. [Architecture overview](#architecture-overview)
2. [Package layout](#package-layout)
3. [TUI layout and navigation](#tui-layout-and-navigation)
4. [Keyboard bindings](#keyboard-bindings)
5. [Search query syntax](#search-query-syntax)
6. [Providers](#providers)
7. [Normalized event schema](#normalized-event-schema)
8. [Configuration](#configuration)
9. [Highlight rules](#highlight-rules)
10. [Persistence and checkpoints](#persistence-and-checkpoints)
11. [Investigation features](#investigation-features)
12. [Observability](#observability)
13. [Development guide](#development-guide)

---

## Architecture overview

TerminalVelocity is structured around four layers:

```
┌─────────────────────────────────────────────┐
│              Textual TUI (tui/)              │
│  query bar · provider panel · event table   │
│  detail panel · export · help overlay       │
└──────────────────┬──────────────────────────┘
                   │ NormalizedEvent list
┌──────────────────▼──────────────────────────┐
│     Search & investigation layer            │
│  SearchEngine · correlator · pivot          │
│  anomaly detection · saved queries          │
└──────────────────┬──────────────────────────┘
                   │ indexes / queries
┌──────────────────▼──────────────────────────┐
│           Provider adapters (providers/)    │
│  Entra ID · Defender XDR · Intune           │
│  Purview · Exchange · SharePoint · Teams    │
│  Defender for Cloud Apps                    │
└──────────────────┬──────────────────────────┘
                   │ raw API responses
┌──────────────────▼──────────────────────────┐
│         Microsoft Graph / M365 APIs         │
└─────────────────────────────────────────────┘
```

Each provider adapter fetches raw events, normalizes them into `NormalizedEvent` objects, and yields them to the search engine. The TUI reads from the search engine and renders results in real time.

---

## Package layout

```
src/terminalvelocity/
├── __init__.py              # public exports and __version__
├── __main__.py              # CLI entry point (terminalvelocity command)
├── schema.py                # NormalizedEvent, ProviderCheckpoint, ProviderStatus
├── models.py                # additional shared models
├── providers/
│   ├── base.py              # abstract ProviderAdapter, HTTP clients, retry logic
│   ├── registry.py          # provider discovery and registration
│   ├── entra_id.py          # Entra ID sign-in and audit logs
│   ├── defender_xdr.py      # Defender XDR incidents, alerts, device timeline
│   ├── intune.py            # Intune audit and operational logs
│   ├── unified_audit_log.py # Microsoft Purview unified audit log
│   ├── exchange_online.py   # Exchange Online message trace and admin logs
│   ├── sharepoint_onedrive.py
│   ├── teams.py
│   └── defender_cloud_apps.py
├── search/
│   ├── engine.py            # SQLite-backed SearchEngine
│   ├── parser.py            # query string parser
│   ├── filters.py           # time-range and field filters
│   ├── index.py             # incremental indexing helpers
│   ├── anomaly.py           # anomaly detection
│   ├── correlator.py        # cross-event correlation
│   └── saved_queries.py     # persistent named queries
├── investigation/
│   ├── pivot.py             # pivot from event to related activity
│   ├── timeline.py          # actor/target timeline builder
│   ├── highlight_rules.py   # YAML-driven highlight and alert rules
│   ├── export.py            # JSON and CSV export
│   └── replay.py            # raw-event replay from cache
├── enrichment/
│   ├── cross_provider.py    # cross-provider event enrichment
│   └── schema_mapper.py     # field normalization helpers
├── observability/
│   ├── health.py            # provider health checks
│   └── metrics.py           # ingestion counters and latency tracking
└── tui/
    ├── app.py               # TerminalVelocityApp (Textual App subclass)
    ├── keybindings.py       # key binding definitions
    ├── themes.py            # CSS / theme constants
    └── widgets/
        ├── query_bar.py     # top query and time-scope bar
        ├── provider_panel.py# left sidebar: provider status
        ├── event_table.py   # centre: scrollable event table
        └── detail_panel.py  # right/bottom: normalized + raw JSON view
```

---

## TUI layout and navigation

```
┌────────────────────────────────────────────────────────────┐
│ [ / ] Query …                             Time: last 24h   │  ← query bar
├─────────────┬──────────────────────────────────────────────┤
│ Providers   │  timestamp    provider  actor   action  result│  ← event table
│             │  ──────────────────────────────────────────── │
│ ● entra     │  12:01:03     entra     alice…  sign-in  ✓   │
│   lag: 2s   │  12:00:58     defender  svc-…   alert    ✗   │
│ ● defender  │  11:59:44     intune    –       sync     ✓   │
│   lag: 5s   │  …                                            │
│ ● intune    ├──────────────────────────────────────────────┤
│ ● purview   │ Detail panel (toggle with d / z)             │  ← detail panel
│             │ { normalized JSON …                          │
└─────────────┴──────────────────────────────────────────────┘
  F1 Query  j/k ↕  h/l ←→  z Deep  d Toggle  e Export  ? Help  q Quit
```

| Region | Description |
|---|---|
| Query bar | Free-text and field-filter input; time scope selector |
| Provider panel | Left sidebar listing each enabled provider, polling lag, error count, and total events |
| Event table | Scrollable list of matching events, sorted by timestamp (newest first by default) |
| Detail panel | Expandable view showing the selected event as normalized JSON and raw JSON |

---

## Keyboard bindings

| Key | Action |
|---|---|
| `/` | Focus query bar |
| `j` / `↓` | Move to next event |
| `k` / `↑` | Move to previous event |
| `g` | Jump to top of list |
| `G` / `End` | Jump to bottom of list |
| `h` | Focus previous panel |
| `l` | Focus next panel |
| `z` / `Tab` | Toggle deep detail mode |
| `d` | Toggle detail panel visibility |
| `e` | Export filtered events to JSON |
| `c` | Export filtered events to CSV |
| `?` | Show help overlay |
| `q` | Quit |

---

## Search query syntax

Queries are typed into the query bar (`/`). Terms are separated by spaces; use quotes for multi-word values.

### Free-text search

Any token that is not a `field:value` pair is treated as a free-text term. All terms must match (implicit AND).

```
sign-in failure
```

### Field filters

```
field:value
```

Available fields: `provider`, `service`, `tenant_id`, `actor`, `action`, `target`, `result`, `severity`, `correlation_id`, `request_id`.

```
provider:defender result:failure
actor:alice@contoso.com severity:high
```

### Time range

```
since:24h            # last 24 hours (units: s, m, h, d, w)
since:2024-01-01     # ISO 8601 date
until:2024-06-01T12:00:00
last:1h              # alias for since:
after:30m            # alias for since:
before:now           # alias for until:
```

### Sorting

```
sort:time            # newest first (default)
sort:-time           # oldest first
sort:severity        # highest severity first
sort:+severity       # lowest severity first
sort:provider        # alphabetical by provider
```

### Combined example

```
sign-in provider:entra result:failure since:1h sort:severity
```

---

## Providers

| Provider | Module | Log types |
|---|---|---|
| Entra ID | `entra_id.py` | Sign-in logs, audit logs |
| Defender XDR | `defender_xdr.py` | Incidents, alerts, device timeline events |
| Intune | `intune.py` | Audit events, operational events |
| Microsoft Purview (UAL) | `unified_audit_log.py` | Unified Audit Log |
| Exchange Online | `exchange_online.py` | Message trace, admin audit logs |
| SharePoint / OneDrive | `sharepoint_onedrive.py` | Audit events |
| Microsoft Teams | `teams.py` | Audit and compliance events |
| Defender for Cloud Apps | `defender_cloud_apps.py` | Activity log, alerts |

All adapters implement the base interface from `providers/base.py`:

| Method | Purpose |
|---|---|
| `connect()` | Authenticate and validate credentials |
| `fetch(since, until)` | Retrieve raw events for a time window |
| `normalize(raw)` | Convert a raw event to `NormalizedEvent` |
| `checkpoint()` | Return the current polling cursor |

Retry and back-off for throttling (HTTP 429) and transient server errors (5xx) is handled by the base HTTP client using `tenacity`.

---

## Normalized event schema

Every provider event is mapped to `NormalizedEvent` (defined in `schema.py`):

| Field | Type | Description |
|---|---|---|
| `timestamp` | `datetime` (UTC) | Event time, always normalized to UTC |
| `provider` | `str` | Source provider identifier (e.g. `entra`, `defender`) |
| `service` | `str` | Sub-service within the provider (e.g. `signin`, `incident`) |
| `tenant_id` | `str \| None` | Entra tenant ID |
| `actor` | `str \| None` | User, application, or service principal that performed the action |
| `action` | `str` | The action or operation name |
| `target` | `str \| None` | Resource or object the action was performed on |
| `result` | `str \| None` | `success`, `failure`, or provider-specific string |
| `severity` | `str \| None` | Normalized severity: `low`, `medium`, `high`, `critical` |
| `correlation_id` | `str \| None` | Cross-request correlation identifier |
| `request_id` | `str \| None` | Individual request identifier |
| `raw` | `dict` | Original unmodified event payload from the provider API |

`result` and `severity` values are lowercased on ingestion. The `raw` field is preserved for full-fidelity investigation.

---

## Configuration

### Credentials

Supply M365 credentials via environment variables:

| Variable | Description |
|---|---|
| `TERMINALVELOCITY_TENANT_ID` | Entra tenant ID |
| `TERMINALVELOCITY_CLIENT_ID` | App registration (client) ID |
| `TERMINALVELOCITY_CLIENT_SECRET` | Client secret for app-only auth |

### CLI flags

| Flag | Default | Description |
|---|---|---|
| `--seed` | `365` | Random seed for demo event generation |
| `--count` | `72` | Number of demo events to generate |
| `--headless-smoke` | off | Run non-interactive smoke test and exit |

---

## Highlight rules

Highlight rules are defined in a YAML file (see `config/highlight_rules.example.yaml`). Copy the example to `config/highlight_rules.yaml` and customize.

```yaml
rules:
  - name: "Privileged role assignment"
    match:
      action: "Add member to role"
      severity: [high, critical]
    highlight: red
    alert: true

  - name: "Repeated sign-in failures"
    match:
      action: "SignIn"
      result: failure
      provider: entra
    highlight: yellow
    alert: false
```

Each rule specifies:
- `name` – human-readable label shown in the TUI
- `match` – one or more field conditions (all must match; severity accepts a list)
- `highlight` – colour applied to matching rows (`red`, `yellow`, `magenta`, …)
- `alert` – whether to count this rule towards the alert badge in the provider panel

---

## Persistence and checkpoints

Checkpoints track the polling cursor for each provider so that restarts do not re-ingest duplicate events.

Checkpoint files are written to `.terminalvelocity/checkpoints/<provider>.json` relative to the working directory. Each file stores:

```json
{
  "provider": "entra",
  "cursor": "eyJ...",
  "last_event_time": "2024-06-01T12:00:00+00:00",
  "metadata": {}
}
```

The search index is backed by a local SQLite database (WAL mode) with a full-text-search virtual table. Events can be archived (hidden from default searches) to keep the hot window fast.

---

## Investigation features

### Correlation

`investigation/pivot.py` lets you pivot from any event to all related activity sharing the same `correlation_id`, `actor`, or `target`.

### Timeline

`investigation/timeline.py` builds a chronological activity timeline for a given actor or target across all providers.

### Anomaly detection

`search/anomaly.py` flags events that exhibit unusual patterns (burst failures, rare actions, privileged operations) based on a sliding-window baseline.

### Export

Press `e` to export filtered events to a timestamped JSON file, or `c` for CSV. Files are written to the current working directory as `terminalvelocity_export_<timestamp>.json/.csv`.

### Saved queries

Named queries can be saved and recalled in the query bar. They are persisted in `.terminalvelocity/saved_queries.json`.

### Session replay

`investigation/replay.py` can replay the raw event cache to re-index events after a schema change or for debugging.

---

## Observability

`observability/health.py` performs lightweight connectivity checks against each configured provider and reports the result in the provider panel sidebar.

`observability/metrics.py` tracks per-provider ingestion counters (total events, error count, last poll time, lag) exposed as `ProviderStatus` objects consumed by the TUI.

---

## Development guide

### Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Run tests

```bash
pytest
```

### Run the TUI (demo mode)

```bash
terminalvelocity --count 100 --seed 1
```

### Non-interactive smoke test

```bash
terminalvelocity --headless-smoke
```

### Adding a new provider

1. Create `src/terminalvelocity/providers/<name>.py`.
2. Subclass `ProviderAdapter` from `providers/base.py` and implement `connect`, `fetch`, `normalize`, and `checkpoint`.
3. Register the adapter in `providers/registry.py`.
4. Add tests under `tests/providers/`.

### Project conventions

- Python 3.12+; type annotations required on all public APIs.
- `pydantic` v2 for data models; `httpx` for async HTTP; `tenacity` for retries.
- TUI components are Textual widgets; CSS lives in `tui/themes.py`.
- Never commit credentials or `config/highlight_rules.yaml` (it is gitignored).
