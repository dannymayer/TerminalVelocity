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
│  Entra ID · Identity Protection · PIM       │
│  Defender XDR · Advanced Hunting · Intune   │
│  Purview · Exchange · SharePoint · Teams    │
│  Defender for Cloud Apps · Secure Score     │
│  Service Health · Attack Simulation         │
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
│   ├── entra_id.py          # Entra ID sign-in, audit, SP sign-in, provisioning logs
│   ├── identity_protection.py  # Entra Identity Protection: risk detections, risky users/SPs
│   ├── pim.py               # Privileged Identity Management role activation and assignments
│   ├── defender_xdr.py      # Defender XDR incidents, alerts, device timeline, vuln mgmt
│   ├── advanced_hunting.py  # Defender 365 KQL Advanced Hunting queries
│   ├── intune.py            # Intune audit and operational logs
│   ├── unified_audit_log.py # Microsoft Purview unified audit log (incl. DLP, Power BI, Forms)
│   ├── exchange_online.py   # Exchange Online message trace and admin logs
│   ├── sharepoint_onedrive.py
│   ├── teams.py
│   ├── defender_cloud_apps.py
│   ├── secure_score.py      # Microsoft Secure Score snapshots and control profiles
│   ├── service_health.py    # M365 service incidents, advisories, health overviews
│   └── attack_simulation.py # Attack Simulation Training per-user simulation results
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
│   ├── cross_provider.py    # cross-provider event enrichment and risk-sign-in linking
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

TerminalVelocity supports 14 provider adapters grouped by function.

### Core identity and access providers

| Provider | Module | Registry name | Log types |
|---|---|---|---|
| Entra ID | `entra_id.py` | `entra_id` | User sign-in logs, directory audit logs, service principal sign-in logs, provisioning logs |
| Identity Protection | `identity_protection.py` | `identity_protection` | Risk detections (impossible travel, leaked creds, anonymous IP), risky users, risky service principals |
| Privileged Identity Management | `pim.py` | `pim` | PIM role activation/deactivation requests, active role assignments |

### Threat detection and hunting

| Provider | Module | Registry name | Log types |
|---|---|---|---|
| Defender XDR | `defender_xdr.py` | `defender_xdr` | Incidents, alerts, device timeline events, vulnerability management |
| Advanced Hunting | `advanced_hunting.py` | `advanced_hunting` | KQL hunting results: IdentityLogonEvents, DeviceEvents, EmailEvents, CloudAppEvents |
| Defender for Cloud Apps | `defender_cloud_apps.py` | `defender_cloud_apps` | Activity log, MCAS alerts |

### Endpoint and device management

| Provider | Module | Registry name | Log types |
|---|---|---|---|
| Intune | `intune.py` | `intune` | Audit events, operational events |

### Collaboration and communication

| Provider | Module | Registry name | Log types |
|---|---|---|---|
| Microsoft Purview (UAL) | `unified_audit_log.py` | `unified_audit_log` | Unified Audit Log: AzureActiveDirectory, Exchange, General, SharePoint, DLP, Power BI, Microsoft Forms |
| Exchange Online | `exchange_online.py` | `exchange_online` | Message trace, admin audit logs, analyzed emails |
| SharePoint / OneDrive | `sharepoint_onedrive.py` | `sharepoint_onedrive` | File, sharing, and admin audit events |
| Microsoft Teams | `teams.py` | `teams` | Admin, meeting, messaging, and device events |

### Posture, health, and awareness

| Provider | Module | Registry name | Log types |
|---|---|---|---|
| Secure Score | `secure_score.py` | `secure_score` | Daily tenant posture score snapshots and control-level profiles |
| Service Health | `service_health.py` | `service_health` | M365 service incidents, advisories, and health overviews |
| Attack Simulation | `attack_simulation.py` | `attack_simulation` | Simulation results per user: link clicked, credentials entered, reported |

### Provider registry aliases

Multiple aliases are registered for convenience. Common aliases:

| Alias | Resolves to |
|---|---|
| `entra`, `aad`, `azure_ad` | `entra_id` |
| `identity_protection`, `idp` | `identity_protection` |
| `pim`, `privileged_identity_management` | `pim` |
| `defender`, `mde`, `mdo` | `defender_xdr` |
| `defender_vuln`, `vuln_mgmt` | `defender_xdr` (with `include_vulnerabilities=True`) |
| `advanced_hunting`, `hunting`, `threat_hunting` | `advanced_hunting` |
| `intune`, `mdm` | `intune` |
| `ual`, `purview`, `unified_audit_log` | `unified_audit_log` |
| `exchange`, `exo` | `exchange_online` |
| `sharepoint`, `onedrive`, `spo` | `sharepoint_onedrive` |
| `teams`, `msteams` | `teams` |
| `mcas`, `cloud_apps` | `defender_cloud_apps` |
| `secure_score`, `security_score` | `secure_score` |
| `service_health`, `m365_health` | `service_health` |
| `attack_simulation`, `sim_training` | `attack_simulation` |

### Provider details

#### Entra ID (`entra_id`)

Fetches from four Graph endpoints and normalizes them into a unified event stream:

1. **User sign-in logs** — `GET /auditLogs/signIns` (requires `AuditLog.Read.All`)
   - Risky sign-ins: severity derived from `riskLevelDuringSignIn` (preferred) then `riskLevelAggregated`
   - `riskEventTypes_v2` preserved in `raw` for downstream correlation
2. **Directory audit logs** — `GET /auditLogs/directoryAudits`
3. **Service principal sign-in logs** — `GET /auditLogs/servicePrincipals`
   - Machine-to-machine OAuth flows; `servicePrincipalName` → `actor`, `resourceDisplayName` → `target`
4. **Provisioning logs** — `GET /auditLogs/provisioning`
   - SCIM/HR-driven account lifecycle events; `initiatedBy.user.userPrincipalName` → `actor`, `targetIdentity.displayName` → `target`

Required app permissions: `AuditLog.Read.All`, `Directory.Read.All`

#### Identity Protection (`identity_protection`)

Fetches from three endpoints and merges results:

- `GET /identityProtection/riskDetections` — individual risk events (impossible travel, leaked credentials, etc.)
- `GET /identityProtection/riskyUsers` — current risky user snapshot with risk level and state
- `GET /identityProtection/riskyServicePrincipals` — risky service principal snapshot

Normalization: `riskEventType`/`riskType` → `action`, `riskLevel` → `severity`, `userPrincipalName`/`displayName` → `actor`, `detectedDateTime`/`riskLastUpdatedDateTime` → `timestamp`, `riskState` → `result`.

Required app permissions: `IdentityRiskEvent.Read.All`, `IdentityRiskyUser.Read.All`

#### Privileged Identity Management (`pim`)

Fetches from two endpoints:

- `GET /identityGovernance/privilegedAccess/aadRoles/roleAssignmentRequests` — time-filtered activation/deactivation requests
- `GET /identityGovernance/privilegedAccess/aadRoles/roleAssignments` — current active assignment snapshot

PIM status values (`Granted`, `ProvisionedLocally`, etc.) are mapped to `success`/`failure` through `_PIM_STATUS_MAP`. Justification text is preserved in `raw._tv_reason`; ticket numbers in `raw._tv_ticket_ref`. Assignments involving the **Global Administrator** role are marked `severity=high`.

Required app permissions: `PrivilegedEligibilitySchedule.Read.AzureADGroup`, `RoleAssignmentSchedule.Read.Directory`

#### Defender XDR (`defender_xdr`)

Fetches incidents, alerts, and optionally per-device timeline events from both the Graph Security API and the Microsoft Defender for Endpoint (MDE) REST API.

**Vulnerability Management** (opt-in via `include_vulnerabilities=True`):

- `GET https://api.securitycenter.microsoft.com/api/vulnerabilities` — fleet-wide CVE snapshot
- `GET https://api.securitycenter.microsoft.com/api/machines/SoftwareVulnerabilitiesByMachine` — per-machine CVE exposure

Normalization: `cveId` → `action`, CVSS v3 score drives severity (≥9.0 critical, ≥7.0 high, ≥4.0 medium, else low), `publicExploit` → `result` (true → failure, false → success).

Required MDE permission: `Vulnerability.Read.All`

#### Advanced Hunting (`advanced_hunting`)

Posts KQL queries to `POST /security/runHuntingQuery`. Default tables queried:

| Table | Key fields normalized |
|---|---|
| `IdentityLogonEvents` | `AccountUpn` → actor, `ActionType` → action, `TargetDeviceName` → target |
| `DeviceEvents` | `InitiatingProcessAccountUpn` → actor, `ActionType` → action, `FileName` → target |
| `EmailEvents` | `RecipientEmailAddress` → actor, `Subject` → action, `DeliveryAction` → result |
| `CloudAppEvents` | `AccountUpn` → actor, `ActionType` → action, `ObjectName` → target |

Custom queries can be supplied as `queries: list[tuple[str, str]]` (table name, KQL string) in the constructor.

Required app permission: `ThreatHunting.Read.All`

#### Microsoft Purview Unified Audit Log (`unified_audit_log`)

Polls the Office 365 Management Activity API for 7 content types by default:

| Content type | Coverage |
|---|---|
| `AzureActiveDirectory` | Entra sign-in and admin operations |
| `Exchange` | Exchange mailbox and admin activity |
| `General` | Cross-workload events |
| `SharePoint` | SharePoint and OneDrive file activity |
| `DLP.All` | Data Loss Prevention rule matches and policy violations |
| `Audit.PowerBI` | Power BI report access, dataset export, workspace changes |
| `MicrosoftForms` | Form creation, response collection, phishing-via-Forms activity |

The `content_types` constructor argument accepts a custom tuple to restrict or expand which types are fetched. Tenants without DLP, Power BI, or Forms subscriptions will simply receive empty responses for those content types — no error is raised.

Required permission: `manage.office.com/.default` via the Office 365 Management API.

#### Secure Score (`secure_score`)

Fetches:

- `GET /security/secureScores` — time-filtered score snapshots; each snapshot becomes a `NormalizedEvent` with `action=SecureScoreSnapshot`
- `GET /security/secureScoreControlProfiles` — control definitions (not time-filtered)

Score delta vs. AllTenants average drives severity: ≤-10 → critical, ≤-5 → high, <0 → medium, ≥0 → info.

Required app permission: `SecurityEvents.Read.All`

#### Service Health (`service_health`)

Fetches:

- `GET /admin/serviceAnnouncement/issues` — active M365 service incidents and advisories
- `GET /admin/serviceAnnouncement/healthOverviews` — per-service health status snapshot

Enables correlation of event spikes with actual Microsoft service outages.

Required app permission: `ServiceHealth.Read.All`

#### Attack Simulation (`attack_simulation`)

Fetches simulation metadata then expands per-user results:

1. `GET /security/attackSimulation/simulations` — list of simulations
2. `GET /security/attackSimulation/simulations/{id}/simulationUsers` — per-user events

Severity mapping: `CredentialsEntered`/`MacroEnabled` → critical, `LinkClicked`/`AttachmentOpened` → high, `ReportedEmail` → success (info), others → medium.

Required app permission: `AttackSimulation.Read.All`

### Provider base interface

All adapters implement the base interface from `providers/base.py`:

| Method | Purpose |
|---|---|
| `connect()` | Authenticate and validate credentials |
| `fetch(since, until)` | Retrieve raw events for a time window |
| `normalize(raw)` | Convert a raw event to `NormalizedEvent` |
| `checkpoint()` | Return the current polling cursor |

Retry and back-off for throttling (HTTP 429) and transient server errors (5xx) is handled by the base HTTP client using `tenacity`.

### Required app registration permissions

The following Microsoft Entra app registration permissions are needed to use all providers. Permissions already covered by the original 8 providers are noted.

| Provider | Required Permissions |
|---|---|
| Entra ID | `AuditLog.Read.All`, `Directory.Read.All` *(original)* |
| Identity Protection | `IdentityRiskEvent.Read.All`, `IdentityRiskyUser.Read.All` *(new)* |
| PIM | `PrivilegedEligibilitySchedule.Read.AzureADGroup`, `RoleAssignmentSchedule.Read.Directory` *(new)* |
| Defender XDR | `SecurityEvents.Read.All`, `ThreatIndicators.Read.All` *(original)*; MDE: `Vulnerability.Read.All` *(new)* |
| Advanced Hunting | `ThreatHunting.Read.All` *(new)* |
| Intune | `DeviceManagementApps.Read.All`, `DeviceManagementManagedDevices.Read.All` *(original)* |
| UAL / Purview | `manage.office.com/.default` *(original)* — covers DLP, Power BI, Forms |
| Exchange Online | `Mail.Read`, `AuditLog.Read.All` *(original)* |
| SharePoint / OneDrive | `Sites.Read.All` *(original)* |
| Microsoft Teams | `TeamSettings.Read.All` *(original)* |
| Defender for Cloud Apps | `CloudApp-Discovery.Read.All` *(original)* |
| Secure Score | `SecurityEvents.Read.All` *(new)* |
| Service Health | `ServiceHealth.Read.All` *(new)* |
| Attack Simulation | `AttackSimulation.Read.All` *(new)* |

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

`NormalizedEvent` uses `model_config = ConfigDict(extra="allow")` (Pydantic v2), so enrichment metadata can be attached as extra fields without schema changes. Currently populated extra fields:

| Extra field | Set by | Description |
|---|---|---|
| `related_event_ids` | `CrossProviderEnricher` | IDs of correlated events from other providers |
| `related_provider_count` | `CrossProviderEnricher` | Number of providers represented in related events |
| `_tv_risk_linked` | `CrossProviderEnricher` | `True` when an Entra sign-in event is linked to an Identity Protection risk detection |
| `_tv_risk_event_ids` | `CrossProviderEnricher` | List of `identity_protection` cache keys for linked risk detections |

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

### Cross-provider enrichment

`enrichment/cross_provider.py` augments events with context from other providers after all providers have been polled:

- **Standard correlation** — events sharing the same `correlation_id` or `request_id` across different providers are linked. Matched events get `related_event_ids` and `related_provider_count` extra fields.
- **Identity Protection → Entra sign-in linking** — when the `identity_protection` provider has been polled alongside `entra_id`, sign-in events are matched against risk detections by `correlationId`/`requestId`. A matched sign-in event gets `_tv_risk_linked=True` and `_tv_risk_event_ids=[...]` pointing at the risk detection cache keys.

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
