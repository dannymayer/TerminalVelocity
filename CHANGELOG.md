# Changelog

All notable changes to TerminalVelocity are documented here.  
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- MIT `LICENSE` file.
- `CONTRIBUTING.md` contributor guide.
- `SECURITY.md` responsible-disclosure policy.
- `.github/workflows/ci.yml` — CI pipeline (Python 3.12 & 3.13, ruff, mypy, pytest + coverage).
- `.github/workflows/release.yml` — automated PyPI & GitHub Release publishing on version tags.
- `[project.urls]`, `license`, `keywords`, and `classifiers` in `pyproject.toml`.
- `ruff`, `mypy`, `pytest-cov`, and `pre-commit` added to the `dev` extras.
- `[tool.ruff]`, `[tool.mypy]`, `[tool.coverage.run]` configuration sections.
- `.pre-commit-config.yaml` with ruff and mypy hooks.
- File-size guard in `ingestion.py` (rejects files > 256 MB).
- `_normalize_id()` helper in `schema_mapper.py` to correctly handle `correlation_id` / `request_id` values.
- Context-manager protocol (`__enter__` / `__exit__`) on `SearchEngine`, `QueryHistoryStore`, and `SavedQueryStore`.
- `on_unmount` hook in `TerminalVelocityApp` to reliably close all SQLite connections on exit.
- Tests for `enrichment/schema_mapper.py` and `enrichment/cross_provider.py`.
- Integration tests for provider HTTP retry logic using `httpx` mock transport.
- TUI unit tests (search submission, provider panel toggle, keybindings).

### Changed
- `TenantConfig.client_secret` is now `pydantic.SecretStr` — the value is masked in repr/logs.
- Bare `except Exception` in the auto-detect path of `ingestion.py` replaced with specific exception types and a DEBUG-level log.
- `correlation_id` and `request_id` in `SchemaMapper.map_event()` now use a dedicated `_normalize_id()` helper instead of `normalize_target()`.
- `SearchEngine.index_events()` wraps the entire batch in a single `BEGIN`/`COMMIT` transaction.
- `SearchEngine`, `QueryHistoryStore`, and `SavedQueryStore` implement `close()` and context-manager protocol.
- Highlight-rule load failure in `TerminalVelocityApp` is now logged at `WARNING` level.
- `asyncio.ensure_future()` replaced with `asyncio.create_task()` in `TerminalVelocityApp`.
- `BaseProvider` (sync) and `ProviderAdapter` (async) classes now have clarifying docstrings explaining the distinction.

---

## [0.1.0] — 2024-01-01

### Added
- Initial public release.
- Textual TUI with query bar, provider panel, event table, and detail panels.
- Support for 14 Microsoft 365 providers: Entra ID, Identity Protection, PIM, Defender XDR, Advanced Hunting, Defender for Cloud Apps, Intune, Unified Audit Log, Exchange Online, SharePoint/OneDrive, Teams, Secure Score, Service Health, Attack Simulation.
- Normalised event schema (`NormalizedEvent`).
- Search engine backed by SQLite FTS5.
- File-based ingestion (JSONL, JSON, CSV) with optional field-mapping.
- Demo mode (no credentials required) with configurable seed and event count.
- Highlight rules engine (YAML-based).
- Cross-provider enrichment and correlation.
- Saved queries and query history.
- JSON, CSV, and Markdown export.
- Anomaly detection.
- Timeline and pivot investigation screens.
- Event tagging.
- YAML-based application configuration with environment-variable overlay.

[Unreleased]: https://github.com/dannymayer/TerminalVelocity/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/dannymayer/TerminalVelocity/releases/tag/v0.1.0
