# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅ Yes    |

---

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

If you discover a security issue in TerminalVelocity, please report it privately using one of the following methods:

1. **GitHub Private Security Advisory** (preferred) — open a [private advisory](https://github.com/dannymayer/TerminalVelocity/security/advisories/new) in this repository.
2. **Email** — send details to the repository owner via the contact information in the GitHub profile.

### What to include

To help us triage the issue quickly, please provide:

- A description of the vulnerability and its potential impact.
- Steps to reproduce (proof-of-concept code or commands, if applicable).
- Affected versions and environments (OS, Python version).
- Any suggested mitigations you have already identified.

### Response timeline

| Milestone | Target |
|-----------|--------|
| Acknowledgement | Within **3 business days** |
| Initial triage & severity assessment | Within **7 business days** |
| Patch or mitigation available | Within **30 days** for high/critical issues |
| Public disclosure | After a fix is available and users have had time to update |

We follow a **coordinated disclosure** model. Once a fix is released, we will publish a GitHub Security Advisory crediting the reporter (unless anonymity is requested).

---

## Scope

Issues in scope include, but are not limited to:

- Credential leakage (e.g. secrets appearing in logs, crash output, or exported files).
- Path traversal or arbitrary file read/write via `--input`, `--config`, or `--log-file` flags.
- Code execution via maliciously crafted input files (JSONL/JSON/CSV ingestion).
- Insecure default permissions on generated files (exports, log files, SQLite databases).
- Authentication bypass or token exposure in the provider adapter layer.

Out of scope:

- Vulnerabilities in third-party dependencies — please report those upstream.
- Issues that require physical access to the machine running TerminalVelocity.
- Social engineering or phishing attacks.

---

## Security best practices for users

- Store tenant credentials in environment variables (`TERMINALVELOCITY_TENANT_ID`, `TERMINALVELOCITY_CLIENT_ID`, `TERMINALVELOCITY_CLIENT_SECRET`) — never commit them to source control.
- Review exported files (JSON/CSV/Markdown) before sharing — they contain raw M365 event data.
- Keep your Python environment and TerminalVelocity up to date by regularly running `pip install --upgrade terminalvelocity`.
- Use a dedicated Entra app registration with the minimum required API permissions and a short-lived client secret.
