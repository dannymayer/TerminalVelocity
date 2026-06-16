# TerminalVelocity

A terminal UI for aggregating, searching, and investigating Microsoft 365 security and operations logs.

TerminalVelocity pulls events from M365 providers (Entra ID, Defender XDR, Intune, Purview, and more), normalizes them into a shared schema, indexes them locally, and presents them in a keyboard-driven TUI built with [Textual](https://textual.textualize.io/).

For full application documentation see [DOCS.md](DOCS.md).

## Requirements

- Python 3.12+
- A Microsoft Entra app registration with the appropriate Graph / M365 API permissions

## Install

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -e .
```

## Quick start

Launch the TUI with demo events (no credentials required):

```bash
terminalvelocity
```

Run a non-interactive smoke test and exit:

```bash
terminalvelocity --headless-smoke
```

Control the number and seed of generated demo events:

```bash
terminalvelocity --count 200 --seed 42
```

## Configuration

Copy the example highlight rules and edit to suit your environment:

```bash
cp config/highlight_rules.example.yaml config/highlight_rules.yaml
```

Store credentials in environment variables (never commit secrets):

| Variable | Purpose |
|---|---|
| `TERMINALVELOCITY_TENANT_ID` | Entra tenant ID |
| `TERMINALVELOCITY_CLIENT_ID` | App registration client ID |
| `TERMINALVELOCITY_CLIENT_SECRET` | App registration client secret |

See [DOCS.md – Configuration](DOCS.md#configuration) for the full reference.

## Contributing

```bash
pip install -e ".[dev]"
pytest
```
