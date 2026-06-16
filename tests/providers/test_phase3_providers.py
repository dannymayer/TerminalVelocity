from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from terminalvelocity.enrichment.cross_provider import CrossProviderEnricher
from terminalvelocity.enrichment.schema_mapper import normalize_result, normalize_severity
from terminalvelocity.observability.health import ProviderHealthChecker
from terminalvelocity.observability.metrics import IngestionMetrics
from terminalvelocity.providers.defender_cloud_apps import DefenderCloudAppsProvider
from terminalvelocity.providers.exchange_online import ExchangeOnlineProvider
from terminalvelocity.providers.sharepoint_onedrive import SharePointOneDriveProvider
from terminalvelocity.providers.teams import TeamsProvider


class FakeGraphClient:
    def __init__(self, *, get_responses=None, post_responses=None, collection_responses=None) -> None:
        self.get_responses = {key: list(value) if isinstance(value, list) else [value] for key, value in (get_responses or {}).items()}
        self.post_responses = {key: list(value) if isinstance(value, list) else [value] for key, value in (post_responses or {}).items()}
        self.collection_responses = collection_responses or {}
        self.deleted_paths: list[str] = []
        self.get_calls: list[tuple[str, dict | None]] = []
        self.post_calls: list[tuple[str, dict]] = []

    def get(self, path: str, *, params=None):
        self.get_calls.append((path, params))
        queue = self.get_responses[path]
        return queue.pop(0)

    def post(self, path: str, body: dict):
        self.post_calls.append((path, body))
        queue = self.post_responses[path]
        return queue.pop(0)

    def delete(self, path: str):
        self.deleted_paths.append(path)
        return None

    def iter_collection(self, path: str, *, params=None):
        self.get_calls.append((path, params))
        for item in self.collection_responses.get(path, []):
            yield item


class FakeMCASClient:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[tuple[str, dict]] = []

    def post(self, path: str, body: dict):
        self.calls.append((path, body))
        return self.response


class Phase3ProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)

    def test_exchange_provider_fetch_normalize_and_checkpoint(self) -> None:
        graph = FakeGraphClient(
            get_responses={
                "/v1.0/organization": {"value": [{"id": "tenant-1"}]},
                "/beta/security/collaboration/analyzedEmails": {"value": []},
                "/v1.0/security/auditLog/queries/query-exchange": [
                    {"status": "running"},
                    {"status": "succeeded"},
                ],
            },
            post_responses={
                "/v1.0/security/auditLog/queries": {"id": "query-exchange", "status": "notStarted"},
            },
            collection_responses={
                "/v1.0/security/auditLog/queries/query-exchange/records": [
                    {
                        "id": "audit-1",
                        "createdDateTime": "2025-01-01T11:55:00Z",
                        "operation": "Set-Mailbox",
                        "userPrincipalName": "admin@contoso.com",
                        "objectId": "shared-mailbox@contoso.com",
                        "resultStatus": "Success",
                        "correlationId": "corr-ex-1",
                        "auditData": {
                            "Operation": "Set-Mailbox",
                            "ObjectId": "shared-mailbox@contoso.com",
                        },
                    }
                ],
                "/beta/security/collaboration/analyzedEmails": [
                    {
                        "id": "trace-1",
                        "deliveredDateTime": "2025-01-01T11:56:00Z",
                        "recipient": {"emailAddress": "user@contoso.com"},
                        "sender": {"emailAddress": "phish@evil.test"},
                        "subject": "Payroll update",
                        "status": "delivered",
                        "verdict": "high",
                        "networkMessageId": "net-1",
                    }
                ],
            },
        )
        provider = ExchangeOnlineProvider(tenant_id="tenant-1", access_token="token", graph_client=graph)
        self.assertTrue(provider.connect())
        fetched = provider.fetch(since=self.now - timedelta(hours=1), until=self.now)
        self.assertEqual(len(fetched), 2)
        normalized = [provider.normalize(item) for item in fetched]
        self.assertEqual(normalized[0].action, "Set-Mailbox")
        self.assertEqual(normalized[0].result, "success")
        self.assertEqual(normalized[1].action, "MessageTrace")
        self.assertEqual(normalized[1].actor, "user@contoso.com")
        self.assertIn("/v1.0/security/auditLog/queries/query-exchange", graph.deleted_paths)
        checkpoint = provider.checkpoint()
        self.assertEqual(checkpoint.cursor, "query-exchange")
        self.assertEqual(checkpoint.metadata["message_trace_count"], 1)

    def test_sharepoint_onedrive_and_teams_normalization(self) -> None:
        graph = FakeGraphClient(
            post_responses={
                "/v1.0/security/auditLog/queries": [
                    {"id": "query-sp", "status": "notStarted"},
                    {"id": "query-teams", "status": "notStarted"},
                ],
            },
            get_responses={
                "/v1.0/security/auditLog/queries/query-sp": {"status": "succeeded"},
                "/v1.0/security/auditLog/queries/query-teams": {"status": "succeeded"},
            },
            collection_responses={
                "/v1.0/security/auditLog/queries/query-sp/records": [
                    {
                        "id": "sp-1",
                        "createdDateTime": "2025-01-01T11:50:00Z",
                        "operation": "FileDownloaded",
                        "userId": "user@contoso.com",
                        "objectId": "Shared Documents/report.xlsx",
                        "auditData": {"SourceFileName": "report.xlsx", "ObjectId": "Shared Documents/report.xlsx"},
                    }
                ],
                "/v1.0/security/auditLog/queries/query-teams/records": [
                    {
                        "id": "teams-1",
                        "createdDateTime": "2025-01-01T11:51:00Z",
                        "operation": "MessageSent",
                        "userId": "user@contoso.com",
                        "auditData": {"TeamName": "IR", "ChannelName": "General"},
                    }
                ],
            },
        )
        sp_provider = SharePointOneDriveProvider(tenant_id="tenant-1", access_token="token", graph_client=graph)
        teams_provider = TeamsProvider(tenant_id="tenant-1", access_token="token", graph_client=graph)
        sp_event = sp_provider.normalize(sp_provider.fetch(since=self.now - timedelta(hours=1), until=self.now)[0])
        teams_event = teams_provider.normalize(teams_provider.fetch(since=self.now - timedelta(hours=1), until=self.now)[0])
        self.assertEqual(sp_event.target, "Shared Documents/report.xlsx")
        self.assertEqual(teams_event.target, "IR/General")
        self.assertEqual(graph.post_calls[0][1]["serviceFilters"], ["SharePoint", "OneDrive"])
        self.assertEqual(graph.post_calls[1][1]["serviceFilters"], ["Teams"])

    def test_defender_cloud_apps_uses_graph_and_mcas(self) -> None:
        graph = FakeGraphClient(
            collection_responses={
                "/v1.0/security/alerts_v2": [
                    {
                        "id": "alert-1",
                        "createdDateTime": "2025-01-01T11:40:00Z",
                        "severity": "high",
                        "status": "resolved",
                        "title": "Impossible travel",
                        "serviceSource": "microsoftDefenderForCloudApps",
                        "userStates": [{"userPrincipalName": "user@contoso.com"}],
                    }
                ]
            },
            get_responses={},
        )
        mcas = FakeMCASClient(
            {
                "data": [
                    {
                        "id": "activity-1",
                        "timestamp": "2025-01-01T11:41:00Z",
                        "userName": "user@contoso.com",
                        "actionType": "FileDownloaded",
                        "objectName": "report.xlsx",
                        "status": "success",
                    }
                ]
            }
        )
        provider = DefenderCloudAppsProvider(
            tenant_id="tenant-1",
            access_token="token",
            graph_client=graph,
            mcas_client=mcas,
        )
        fetched = provider.fetch(since=self.now - timedelta(hours=1), until=self.now)
        self.assertEqual(len(fetched), 2)
        alert_event = provider.normalize(fetched[0])
        activity_event = provider.normalize(fetched[1])
        self.assertEqual(alert_event.action, "Impossible travel")
        self.assertEqual(activity_event.action, "FileDownloaded")
        self.assertEqual(activity_event.target, "report.xlsx")
        self.assertEqual(mcas.calls[0][0], "/api/v1/activities/")

    def test_enrichment_and_observability_helpers(self) -> None:
        graph = FakeGraphClient(
            get_responses={
                "/v1.0/organization": {"value": [{"id": "tenant-1"}]},
                "/beta/security/collaboration/analyzedEmails": {"value": []},
            },
            post_responses={"/v1.0/security/auditLog/queries": {"id": "query-1", "status": "notStarted"}},
            collection_responses={},
        )
        provider = ExchangeOnlineProvider(tenant_id="tenant-1", access_token="token", graph_client=graph)
        metrics = IngestionMetrics()
        metrics.record_fetch(provider.provider_name, 5)
        metrics.record_normalized(
            provider.provider_name,
            4,
            latest_event_timestamp=datetime.now(UTC) - timedelta(minutes=2),
        )
        metrics.record_error(provider.provider_name, "throttled")
        metrics.record_retry(provider.provider_name, 2)
        health = ProviderHealthChecker(metrics, max_lag=timedelta(minutes=10)).check_provider(provider)
        self.assertTrue(health.ok)
        self.assertAlmostEqual(metrics.snapshot()[provider.provider_name]["error_rate"], 0.2)

        event_a = provider.normalize(
            {
                "id": "audit-1",
                "createdDateTime": "2025-01-01T11:55:00Z",
                "operation": "Set-Mailbox",
                "userPrincipalName": "user@contoso.com",
                "objectId": "shared-mailbox@contoso.com",
                "resultStatus": "Success",
                "auditData": {},
            }
        )
        event_b = event_a.model_copy(update={"provider": "teams", "service": "microsoft-teams", "timestamp": self.now - timedelta(minutes=1)})
        enriched = CrossProviderEnricher(time_window=timedelta(minutes=5)).enrich([event_a, event_b])
        self.assertEqual(enriched[0].related_provider_count, 1)
        self.assertEqual(normalize_result("Blocked"), "failure")
        self.assertEqual(normalize_severity("Informational"), "info")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
