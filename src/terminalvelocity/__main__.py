"""CLI entrypoint for launching the TerminalVelocity TUI."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from pathlib import Path

from terminalvelocity.config import AppConfig
from terminalvelocity.tui.app import TerminalVelocityApp, run_headless_smoke


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch the TerminalVelocity Microsoft 365 log viewer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  terminalvelocity                         # Demo mode with mock events
  terminalvelocity --live                  # Connect to real M365 providers
  terminalvelocity --input events.jsonl    # Load events from a local file
  terminalvelocity --input events.json --provider azure --service activity
  terminalvelocity --compare 48            # Show events newer than 48h baseline
  terminalvelocity --config myconfig.yaml  # Use a custom configuration file
  terminalvelocity --headless-smoke        # Non-interactive smoke test
""",
    )
    # Demo / generation options
    parser.add_argument("--seed", type=int, default=365, help="Seed for deterministic demo events.")
    parser.add_argument("--count", type=int, default=72, help="Number of demo events to generate.")

    # Live polling
    parser.add_argument(
        "--live",
        action="store_true",
        help="Connect to real Microsoft 365 providers using environment credentials.",
    )

    # File ingestion
    parser.add_argument(
        "--input",
        metavar="FILE",
        help="Ingest events from a local JSONL, JSON, or CSV file.",
    )
    parser.add_argument(
        "--provider",
        metavar="NAME",
        default=None,
        help="Override provider name for all events loaded via --input.",
    )
    parser.add_argument(
        "--service",
        metavar="NAME",
        default=None,
        help="Override service name for all events loaded via --input.",
    )

    # Differential / comparison
    parser.add_argument(
        "--compare",
        type=int,
        metavar="HOURS",
        default=None,
        help="Comparison baseline: highlight events newer than HOURS hours (sets initial time scope).",
    )

    # Configuration
    parser.add_argument(
        "--config",
        metavar="FILE",
        default=None,
        help="Path to terminalvelocity.yaml configuration file.",
    )

    # Test / CI
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

    # Load application configuration
    config = AppConfig.load_or_default(args.config)

    # File ingestion
    input_events = None
    if args.input:
        from terminalvelocity.ingestion import ingest_file, FileIngestionError

        # Resolve field mappings from config for the given provider
        field_mappings: dict[str, str] | None = None
        if args.provider and config.field_mappings:
            for fm in config.field_mappings:
                if fm.provider == args.provider:
                    field_mappings = fm.as_dict()
                    break

        try:
            input_events = ingest_file(
                args.input,
                field_mappings=field_mappings,
                provider_override=args.provider,
                service_override=args.service,
            )
            print(f"Loaded {len(input_events)} event(s) from {args.input}")
        except FileIngestionError as exc:
            print(f"Error: {exc}")
            return 1

    TerminalVelocityApp(
        seed=args.seed,
        count=args.count,
        config=config,
        live=args.live,
        input_events=input_events,
        compare_hours=args.compare,
    ).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
