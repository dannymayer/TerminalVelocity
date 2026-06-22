# Contributing to TerminalVelocity

Thank you for your interest in contributing! This guide walks you through the development setup, branching conventions, and the pull request process.

---

## Table of contents

1. [Development setup](#development-setup)
2. [Running tests](#running-tests)
3. [Linting and formatting](#linting-and-formatting)
4. [Type checking](#type-checking)
5. [Pre-commit hooks](#pre-commit-hooks)
6. [Branching conventions](#branching-conventions)
7. [Pull request process](#pull-request-process)
8. [Reporting bugs](#reporting-bugs)

---

## Development setup

```bash
# Clone the repository
git clone https://github.com/dannymayer/TerminalVelocity.git
cd TerminalVelocity

# Create and activate a virtual environment (Python 3.12+ required)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install the package in editable mode with all dev dependencies
pip install --upgrade pip
pip install -e ".[dev]"
```

---

## Running tests

```bash
# Run the full test suite
pytest

# Run with coverage report
pytest --cov=terminalvelocity --cov-report=term-missing

# Run a quick non-interactive smoke test of the TUI
terminalvelocity --headless-smoke
```

---

## Linting and formatting

We use [ruff](https://docs.astral.sh/ruff/) as a combined linter and formatter.

```bash
# Check for lint issues
ruff check .

# Auto-fix safe issues
ruff check --fix .

# Format code
ruff format .

# Check formatting without modifying files
ruff format --check .
```

---

## Type checking

We use [mypy](https://mypy.readthedocs.io/) for static type analysis.

```bash
mypy src/terminalvelocity
```

---

## Pre-commit hooks

Install the pre-commit hooks once to have ruff and mypy run automatically before each commit:

```bash
pre-commit install
```

Run all hooks manually on every file:

```bash
pre-commit run --all-files
```

---

## Branching conventions

| Branch | Purpose |
|--------|---------|
| `main` | Stable, always-deployable code. Protected — merge via PR only. |
| `feat/<short-description>` | New features or enhancements. |
| `fix/<short-description>` | Bug fixes. |
| `chore/<short-description>` | Maintenance tasks (deps, CI, docs). |

Branch names should be lowercase and use hyphens, e.g. `feat/new-provider-teams`.

---

## Pull request process

1. **Fork** the repository and create your branch from `main`.
2. **Make your changes** — keep each PR focused on a single concern.
3. **Add or update tests** — new features should have test coverage; bug fixes should include a regression test.
4. **Run the full quality gate locally** before opening the PR:
   ```bash
   ruff check . && ruff format --check . && mypy src/terminalvelocity && pytest
   ```
5. **Open a pull request** against `main`. Fill in the PR template.
6. **Address review feedback** — the CI pipeline (ruff, mypy, pytest) must be green before merge.

---

## Reporting bugs

Open an [issue](https://github.com/dannymayer/TerminalVelocity/issues) with:

- A clear title and description.
- Steps to reproduce.
- Expected vs. actual behaviour.
- Your OS, Python version (`python --version`), and TerminalVelocity version (`pip show terminalvelocity`).
- Any relevant log output from `.terminalvelocity/app.log`.

For security issues, please follow the [security policy](SECURITY.md) instead of opening a public issue.
