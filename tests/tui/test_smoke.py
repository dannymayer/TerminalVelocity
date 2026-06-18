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


def test_compare_hours_sets_initial_query() -> None:
    async def run() -> None:
        app = TerminalVelocityApp(seed=42, count=18, compare_hours=12)

        async with app.run_test(size=(150, 45)) as pilot:
            await pilot.pause()
            assert app.query_one(QueryBar).query == "since:12h"

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
    """App calls _poll_providers when live=True and credentials are set."""
    import os
    from unittest.mock import AsyncMock, patch

    async def run() -> None:
        live_events = generate_mock_events(count=5, seed=99)
        from terminalvelocity.schema import ProviderStatus
        app = TerminalVelocityApp(seed=1, count=10, live=True)
        env_vars = {
            "TERMINALVELOCITY_TENANT_ID": "test-tenant",
            "TERMINALVELOCITY_CLIENT_ID": "test-client",
            "TERMINALVELOCITY_CLIENT_SECRET": "test-secret",
        }
        with patch.dict(os.environ, env_vars), patch.object(
            app, "_poll_providers", new=AsyncMock()
        ) as mock_poll:
            async with app.run_test(size=(150, 45)) as pilot:
                await pilot.pause()
                assert "Live" in app.sub_title
                mock_poll.assert_awaited()

    asyncio.run(run())


def test_partial_credentials_fall_back_to_demo() -> None:
    """App uses mock data when live flag is not set."""
    async def run() -> None:
        app = TerminalVelocityApp(seed=1, count=10)
        async with app.run_test(size=(150, 45)) as pilot:
            await pilot.pause()
            assert len(app.events) == 10
            assert "Demo mode" in app.sub_title

    asyncio.run(run())


def test_main_auto_enables_live_when_env_creds_present() -> None:
    """main() auto-enables live mode when all three env credentials are set."""
    import os
    from unittest.mock import AsyncMock, MagicMock, patch

    env_vars = {
        "TERMINALVELOCITY_TENANT_ID": "test-tenant",
        "TERMINALVELOCITY_CLIENT_ID": "test-client",
        "TERMINALVELOCITY_CLIENT_SECRET": "test-secret",
    }

    mock_app = MagicMock()
    mock_app.run = MagicMock()

    def capture_app(**kwargs: object) -> MagicMock:
        assert kwargs.get("live") is True, "live should be True when env creds are present"
        return mock_app

    with patch.dict(os.environ, env_vars, clear=False), patch(
        "terminalvelocity.__main__.TerminalVelocityApp", side_effect=capture_app
    ):
        from terminalvelocity.__main__ import main
        main([])
