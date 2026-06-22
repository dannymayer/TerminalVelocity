"""CLI entrypoint for launching the TerminalVelocity TUI."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from collections.abc import Sequence
from pathlib import Path

from terminalvelocity.config import AppConfig
from terminalvelocity.tui.app import TerminalVelocityApp, run_headless_smoke

_DEFAULT_LOG_FILE = Path(".terminalvelocity") / "app.log"


def _configure_logging(log_file: str | Path, log_level: str) -> None:
    """Set up a rotating file handler that captures all application logs."""
    from logging.handlers import RotatingFileHandler

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, log_level.upper(), logging.WARNING)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(fmt)
    handler.setLevel(level)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)


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

    # Logging
    parser.add_argument(
        "--log-file",
        metavar="FILE",
        default=None,
        help=f"Path to the application log file (default: {_DEFAULT_LOG_FILE}).",
    )
    parser.add_argument(
        "--log-level",
        metavar="LEVEL",
        default=None,
        help="Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: WARNING).",
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

    # Configure file-based logging (CLI args take precedence over config)
    log_file = args.log_file or config.log_file or _DEFAULT_LOG_FILE
    log_level = args.log_level or config.log_level
    _configure_logging(log_file, log_level)

    # Auto-enable live mode when credentials are available in the environment
    if not args.live and not args.input:
        _env_creds = all(
            [
                os.environ.get("TERMINALVELOCITY_TENANT_ID"),
                os.environ.get("TERMINALVELOCITY_CLIENT_ID"),
                os.environ.get("TERMINALVELOCITY_CLIENT_SECRET"),
            ]
        )
        if _env_creds:
            args.live = True

    # File ingestion
    input_events = None
    if args.input:
        from terminalvelocity.ingestion import FileIngestionError, ingest_file

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
        log_file=Path(log_file),
    ).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
