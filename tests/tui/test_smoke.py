import asyncio

from terminalvelocity.tui.app import TerminalVelocityApp, filter_events, generate_mock_events
from terminalvelocity.tui.widgets.detail_panel import DetailPanel
from terminalvelocity.tui.widgets.event_table import EventTable
from terminalvelocity.tui.widgets.provider_panel import ProviderPanel
from terminalvelocity.tui.widgets.query_bar import QueryBar


def test_mock_filtering_supports_field_queries() -> None:
    events = generate_mock_events(count=12, seed=42)
    filtered = filter_events(events, "provider:defender result:failure", "all")
    assert filtered
    assert all(event.provider == "defender" for event in filtered)
    assert all(event.result == "failure" for event in filtered)


def test_tui_smoke() -> None:
    async def run() -> None:
        app = TerminalVelocityApp(seed=42, count=18)

        async with app.run_test(size=(150, 45)) as pilot:
            await pilot.pause()
            assert app.query_one(QueryBar)
            assert app.query_one(ProviderPanel)
            assert app.query_one(EventTable).row_count > 0
            assert app.query_one(DetailPanel).display is True

            await pilot.press("z")
            await pilot.pause()
            assert app.detail_mode == "deep"

            await pilot.press("d")
            await pilot.pause()
            assert app.detail_visible is False

            await pilot.press("?")
            await pilot.pause()
            assert len(app.screen_stack) > 1

    asyncio.run(run())
