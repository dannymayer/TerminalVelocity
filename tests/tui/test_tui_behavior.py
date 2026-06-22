"""Unit tests for TUI search submission, keybindings, and provider panel behavior."""

from __future__ import annotations

import asyncio
import unittest

from terminalvelocity.tui.app import TerminalVelocityApp, generate_mock_events
from terminalvelocity.tui.widgets.event_table import EventTable
from terminalvelocity.tui.widgets.provider_panel import ProviderPanel
from terminalvelocity.tui.widgets.query_bar import QueryBar


class SearchSubmissionTests(unittest.TestCase):
    """Tests for the query bar and search filtering behaviors."""

    def test_field_filter_narrows_results(self) -> None:
        async def run() -> None:
            app = TerminalVelocityApp(seed=42, count=50, database_path=":memory:")
            async with app.run_test(size=(160, 48)) as pilot:
                await pilot.pause()
                total = len(app.filtered_events)
                assert total > 0, "Expected demo events to be loaded"

                # Apply a provider filter
                app.query_one(QueryBar).set_query("provider:entra")
                app.refresh_view()
                await pilot.pause()

                filtered = len(app.filtered_events)
                assert filtered <= total
                assert all(e.provider == "entra" for e in app.filtered_events)

        asyncio.run(run())

    def test_result_filter_failure(self) -> None:
        async def run() -> None:
            app = TerminalVelocityApp(seed=42, count=50, database_path=":memory:")
            async with app.run_test(size=(160, 48)) as pilot:
                await pilot.pause()
                app.query_one(QueryBar).set_query("result:failure")
                app.refresh_view()
                await pilot.pause()
                assert all(e.result == "failure" for e in app.filtered_events)

        asyncio.run(run())

    def test_clear_filter_restores_all_events(self) -> None:
        async def run() -> None:
            count = 24
            app = TerminalVelocityApp(seed=42, count=count, database_path=":memory:")
            async with app.run_test(size=(160, 48)) as pilot:
                await pilot.pause()

                # Narrow then clear
                app.query_one(QueryBar).set_query("provider:entra")
                app.refresh_view()
                await pilot.pause()
                narrowed = len(app.filtered_events)

                app.query_one(QueryBar).set_query("")
                app.refresh_view()
                await pilot.pause()
                restored = len(app.filtered_events)

                assert restored >= narrowed
                assert restored == count

        asyncio.run(run())


class KeybindingTests(unittest.TestCase):
    """Tests that keyboard shortcuts trigger the expected state changes."""

    def test_z_toggles_deep_detail(self) -> None:
        async def run() -> None:
            app = TerminalVelocityApp(seed=1, count=12, database_path=":memory:")
            async with app.run_test(size=(160, 48)) as pilot:
                await pilot.pause()
                assert app.deep_detail is False

                await pilot.press("z")
                await pilot.pause()
                assert app.deep_detail is True

                await pilot.press("z")
                await pilot.pause()
                assert app.deep_detail is False

        asyncio.run(run())

    def test_d_toggles_detail_panel_visibility(self) -> None:
        async def run() -> None:
            app = TerminalVelocityApp(seed=1, count=12, database_path=":memory:")
            async with app.run_test(size=(160, 48)) as pilot:
                await pilot.pause()
                assert app.detail_visible is True

                await pilot.press("d")
                await pilot.pause()
                assert app.detail_visible is False

                await pilot.press("d")
                await pilot.pause()
                assert app.detail_visible is True

        asyncio.run(run())

    def test_question_mark_opens_help_screen(self) -> None:
        async def run() -> None:
            app = TerminalVelocityApp(seed=1, count=12, database_path=":memory:")
            async with app.run_test(size=(160, 48)) as pilot:
                await pilot.pause()
                initial_depth = len(app.screen_stack)

                await pilot.press("?")
                await pilot.pause()
                assert len(app.screen_stack) > initial_depth

                await pilot.press("escape")
                await pilot.pause()
                assert len(app.screen_stack) == initial_depth

        asyncio.run(run())

    def test_j_and_k_move_cursor(self) -> None:
        async def run() -> None:
            app = TerminalVelocityApp(seed=1, count=20, database_path=":memory:")
            async with app.run_test(size=(160, 48)) as pilot:
                await pilot.pause()
                from textual.widgets import DataTable

                table_widget = app.query_one(EventTable)
                dt = table_widget.query_one(DataTable)
                initial_row = dt.cursor_row

                await pilot.press("j")
                await pilot.pause()
                after_down = dt.cursor_row

                await pilot.press("k")
                await pilot.pause()
                after_up = dt.cursor_row

                assert after_down == initial_row + 1
                assert after_up == initial_row

        asyncio.run(run())

    def test_slash_focuses_query_bar(self) -> None:
        async def run() -> None:
            app = TerminalVelocityApp(seed=1, count=12, database_path=":memory:")
            async with app.run_test(size=(160, 48)) as pilot:
                await pilot.pause()
                # Focus the table first (default)
                app.query_one(EventTable).focus()
                await pilot.pause()

                await pilot.press("/")
                await pilot.pause()
                # After pressing /, the query input should be focused
                query_input = app.query_one("#query-input")
                assert query_input.has_focus

        asyncio.run(run())


class ProviderPanelTests(unittest.TestCase):
    """Tests for the provider panel display."""

    def test_provider_panel_mounted(self) -> None:
        async def run() -> None:
            app = TerminalVelocityApp(seed=42, count=24, database_path=":memory:")
            async with app.run_test(size=(160, 48)) as pilot:
                await pilot.pause()
                panel = app.query_one(ProviderPanel)
                assert panel is not None

        asyncio.run(run())

    def test_all_providers_represented_in_demo_mode(self) -> None:
        events = generate_mock_events(seed=42, count=100)
        providers_seen = {e.provider for e in events}
        # Demo mode should generate at least 10 distinct providers
        assert len(providers_seen) >= 10
