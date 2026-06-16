"""CLI entrypoint for TerminalVelocity."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from terminalvelocity.tui.app import TerminalVelocityApp, run_headless_smoke


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the TerminalVelocity Phase 1 core TUI.")
    parser.add_argument("--seed", type=int, default=365, help="Seed for deterministic mock events.")
    parser.add_argument("--count", type=int, default=72, help="Number of mock events to generate.")
    parser.add_argument(
        "--headless-smoke",
        action="store_true",
        help="Run a non-interactive Textual smoke test and exit.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.headless_smoke:
        asyncio.run(run_headless_smoke(seed=args.seed, count=args.count))
        return 0
    TerminalVelocityApp(seed=args.seed, count=args.count).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
