"""CLI entrypoint for launching the TerminalVelocity TUI."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from terminalvelocity.tui.app import TerminalVelocityApp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the TerminalVelocity Microsoft 365 log viewer.")
    parser.add_argument("--seed", type=int, default=365, help="Seed for deterministic demo data.")
    parser.add_argument("--count", type=int, default=72, help="Number of demo events to generate.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    TerminalVelocityApp(seed=args.seed, count=args.count).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
