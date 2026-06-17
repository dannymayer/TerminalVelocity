import asyncio
from unittest.mock import AsyncMock, patch

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


def test_demo_mode_used_when_credentials_absent() -> None:
    """App uses mock data when env vars are not set."""
    async def run() -> None:
        app = TerminalVelocityApp(seed=1, count=10)
        async with app.run_test(size=(150, 45)) as pilot:
            await pilot.pause()
            assert len(app.events) == 10
            assert "Demo mode" in app.sub_title

    asyncio.run(run())


def test_live_mode_used_when_credentials_present() -> None:
    """App calls _load_live_events when all three credentials are supplied."""
    async def run() -> None:
        live_events = generate_mock_events(count=5, seed=99)
        from terminalvelocity.schema import ProviderStatus
        live_statuses = [
            ProviderStatus(
                provider="entra_id",
                service="Microsoft Entra ID",
                state="ok",
                lag_seconds=0,
                error_count=0,
                enabled=True,
                total_events=5,
            )
        ]
        app = TerminalVelocityApp(
            seed=1,
            count=10,
            tenant_id="test-tenant",
            client_id="test-client",
            client_secret="test-secret",
        )
        with patch.object(app, "_load_live_events", new=AsyncMock(return_value=(live_events, live_statuses))):
            async with app.run_test(size=(150, 45)) as pilot:
                await pilot.pause()
                assert app.events is live_events
                assert app.provider_statuses is live_statuses
                app._load_live_events.assert_awaited_once()

    asyncio.run(run())


def test_partial_credentials_fall_back_to_demo() -> None:
    """App uses mock data when only some credentials are provided."""
    async def run() -> None:
        app = TerminalVelocityApp(
            seed=1,
            count=10,
            tenant_id="test-tenant",
            client_id=None,
            client_secret="test-secret",
        )
        async with app.run_test(size=(150, 45)) as pilot:
            await pilot.pause()
            assert len(app.events) == 10
            assert "Demo mode" in app.sub_title

    asyncio.run(run())
