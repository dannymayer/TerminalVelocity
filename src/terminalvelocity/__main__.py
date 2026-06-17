"""CLI entrypoint for launching the TerminalVelocity TUI."""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Sequence

from terminalvelocity.tui.app import TerminalVelocityApp, run_headless_smoke


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the TerminalVelocity Microsoft 365 log viewer.")
    parser.add_argument("--seed", type=int, default=365, help="Seed for deterministic demo events.")
    parser.add_argument("--count", type=int, default=72, help="Number of demo events to generate.")
    parser.add_argument(
        "--headless-smoke",
        action="store_true",
        help="Run a non-interactive Textual smoke test and exit.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    tenant_id = os.environ.get("TERMINALVELOCITY_TENANT_ID")
    client_id = os.environ.get("TERMINALVELOCITY_CLIENT_ID")
    client_secret = os.environ.get("TERMINALVELOCITY_CLIENT_SECRET")
    if args.headless_smoke:
        asyncio.run(run_headless_smoke(seed=args.seed, count=args.count))
        return 0
    TerminalVelocityApp(
        seed=args.seed,
        count=args.count,
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    ).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
