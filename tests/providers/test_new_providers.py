"""Tests for the new and extended provider implementations."""

from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime, timedelta

import httpx

from terminalvelocity.enrichment.cross_provider import CrossProviderEnricher
from terminalvelocity.providers import CheckpointStore
from terminalvelocity.providers.advanced_hunting import AdvancedHuntingProvider
from terminalvelocity.providers.attack_simulation import AttackSimulationProvider
from terminalvelocity.providers.defender_xdr import DefenderXdrProvider
from terminalvelocity.providers.entra_id import EntraIdProvider
from terminalvelocity.providers.identity_protection import IdentityProtectionProvider
from terminalvelocity.providers.pim import PIMProvider
from terminalvelocity.providers.registry import registry as provider_registry
from terminalvelocity.providers.secure_score import SecureScoreProvider
from terminalvelocity.providers.service_health import ServiceHealthProvider
from terminalvelocity.providers.unified_audit_log import UnifiedAuditLogProvider
from terminalvelocity.schema import NormalizedEvent

# ---------------------------------------------------------------------------
# Shared async helpers
# ---------------------------------------------------------------------------


def run(coro):
    return asyncio.run(coro)


def _make_checkpoint_dir(tmp_path, name):
    p = tmp_path / name
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Fake async HTTP transport helpers
# ---------------------------------------------------------------------------


class _AsyncMockTransport(httpx.AsyncBaseTransport):
    """Simple URL-routing mock transport for httpx.AsyncClient."""

    def __init__(self, routes: dict) -> None:
        # routes: {path_suffix: response_dict_or_list}
        self._routes = routes

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/oauth2/v2.0/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        for suffix, body in self._routes.items():
            if path.endswith(suffix):
                return httpx.Response(200, json=body if isinstance(body, dict) else {"value": body})
        raise AssertionError(f"Unhandled path: {path}")


def _make_provider(cls, routes, tmp_dir, **kwargs):
    transport = _AsyncMockTransport(routes)
    return cls(
        tenant_id="t1",
        client_id="c1",
        client_secret="s1",
        checkpoint_store=CheckpointStore(tmp_dir),
        http_client=httpx.AsyncClient(transport=transport),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# EntraIdProvider — new endpoints
# ---------------------------------------------------------------------------


class TestEntraIdExtended(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp()
        self.start = datetime(2025, 1, 1, tzinfo=UTC)
        self.end = datetime(2025, 1, 1, 1, tzinfo=UTC)

    def _provider(self, routes):
        from pathlib import Path

        return _make_provider(EntraIdProvider, routes, Path(self.tmp))

    def test_sp_signin_normalization(self):
        routes = {
            "/auditLogs/signIns": {"value": []},
            "/auditLogs/directoryAudits": {"value": []},
            "/auditLogs/servicePrincipals": {
                "value": [
                    {
                        "id": "sp-1",
                        "createdDateTime": "2025-01-01T00:05:00Z",
                        "servicePrincipalId": "sp-id-1",
                        "servicePrincipalName": "MyApp",
                        "resourceDisplayName": "Microsoft Graph",
                        "correlationId": "corr-sp-1",
                        "status": {"errorCode": 0},
                        "clientCredentialType": "secret",
                    }
                ]
            },
            "/auditLogs/provisioning": {"value": []},
        }
        provider = self._provider(routes)
        events = run(provider.fetch(start_time=self.start, end_time=self.end))
        assert len(events) == 1
        ev = events[0]
        assert ev.action == "sp-sign-in"
        assert ev.actor == "MyApp"
        assert ev.result == "success"
        assert ev.service == "Microsoft Entra ID Service Principal Sign-In"

    def test_provisioning_log_normalization(self):
        routes = {
            "/auditLogs/signIns": {"value": []},
            "/auditLogs/directoryAudits": {"value": []},
            "/auditLogs/servicePrincipals": {"value": []},
            "/auditLogs/provisioning": {
                "value": [
                    {
                        "id": "prov-1",
                        "activityDateTime": "2025-01-01T00:10:00Z",
                        "jobId": "job-1",
                        "cycleId": "cycle-1",
                        "provisioningAction": "Create",
                        "initiatedBy": {"user": {"userPrincipalName": "admin@contoso.com"}},
                        "targetIdentity": {"displayName": "NewUser"},
                        "sourceSystem": {"displayName": "Workday"},
                        "targetSystem": {"displayName": "Azure AD"},
                        "statusInfo": {"status": "success"},
                    }
                ]
            },
        }
        provider = self._provider(routes)
        events = run(provider.fetch(start_time=self.start, end_time=self.end))
        assert len(events) == 1
        ev = events[0]
        assert ev.action == "Create"
        assert ev.actor == "admin@contoso.com"
        assert ev.target == "NewUser"
        assert ev.result == "success"
        assert "Workday" in ev.service

    def test_risky_signin_uses_risk_level_during_signin(self):
        routes = {
            "/auditLogs/signIns": {
                "value": [
                    {
                        "id": "signin-risky",
                        "createdDateTime": "2025-01-01T00:01:00Z",
                        "userPrincipalName": "victim@contoso.com",
                        "resourceDisplayName": "SharePoint",
                        "correlationId": "corr-risk",
                        "status": {"errorCode": 0},
                        "riskLevelAggregated": "none",
                        "riskLevelDuringSignIn": "high",
                        "riskState": "atRisk",
                    }
                ]
            },
            "/auditLogs/directoryAudits": {"value": []},
            "/auditLogs/servicePrincipals": {"value": []},
            "/auditLogs/provisioning": {"value": []},
        }
        provider = self._provider(routes)
        events = run(provider.fetch(start_time=self.start, end_time=self.end))
        assert len(events) == 1
        # riskLevelDuringSignIn should take precedence over riskLevelAggregated
        assert events[0].severity == "high"


# ---------------------------------------------------------------------------
# IdentityProtectionProvider
# ---------------------------------------------------------------------------


class TestIdentityProtectionProvider(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp()
        self.start = datetime(2025, 1, 1, tzinfo=UTC)
        self.end = datetime(2025, 1, 1, 1, tzinfo=UTC)

    def _provider(self, routes):
        from pathlib import Path

        return _make_provider(IdentityProtectionProvider, routes, Path(self.tmp))

    def test_risk_detection_normalization(self):
        routes = {
            "/identityProtection/riskDetections": {
                "value": [
                    {
                        "id": "det-1",
                        "detectedDateTime": "2025-01-01T00:02:00Z",
                        "riskEventType": "anonymizedIPAddress",
                        "riskLevel": "high",
                        "riskState": "atRisk",
                        "userPrincipalName": "victim@contoso.com",
                        "correlationId": "corr-risk-1",
                        "ipAddress": "1.2.3.4",
                        "tenantId": "t1",
                    }
                ]
            },
            "/identityProtection/riskyUsers": {"value": []},
            "/identityProtection/riskyServicePrincipals": {"value": []},
        }
        provider = self._provider(routes)
        events = run(provider.fetch(start_time=self.start, end_time=self.end))
        assert len(events) == 1
        ev = events[0]
        assert ev.action == "anonymizedIPAddress"
        assert ev.severity == "high"
        assert ev.actor == "victim@contoso.com"
        assert ev.provider == "identity_protection"

    def test_risky_user_normalization(self):
        routes = {
            "/identityProtection/riskDetections": {"value": []},
            "/identityProtection/riskyUsers": {
                "value": [
                    {
                        "id": "usr-1",
                        "riskLastUpdatedDateTime": "2025-01-01T00:03:00Z",
                        "userPrincipalName": "victim@contoso.com",
                        "userDisplayName": "Victim User",
                        "riskLevel": "critical",
                        "riskState": "confirmedCompromised",
                    }
                ]
            },
            "/identityProtection/riskyServicePrincipals": {"value": []},
        }
        provider = self._provider(routes)
        events = run(provider.fetch(start_time=self.start, end_time=self.end))
        assert len(events) == 1
        ev = events[0]
        assert ev.action == "risky-user-state-change"
        assert ev.severity == "critical"
        assert ev.actor == "victim@contoso.com"

    def test_risky_service_principal_normalization(self):
        routes = {
            "/identityProtection/riskDetections": {"value": []},
            "/identityProtection/riskyUsers": {"value": []},
            "/identityProtection/riskyServicePrincipals": {
                "value": [
                    {
                        "id": "sp-1",
                        "riskLastUpdatedDateTime": "2025-01-01T00:04:00Z",
                        "displayName": "CompromisedApp",
                        "appId": "app-id-1",
                        "riskLevel": "high",
                        "riskState": "atRisk",
                    }
                ]
            },
        }
        provider = self._provider(routes)
        events = run(provider.fetch(start_time=self.start, end_time=self.end))
        assert len(events) == 1
        ev = events[0]
        assert ev.action == "risky-service-principal-state-change"
        assert ev.actor == "CompromisedApp"
        assert ev.severity == "high"


# ---------------------------------------------------------------------------
# UnifiedAuditLogProvider — extended content types
# ---------------------------------------------------------------------------


class TestUnifiedAuditLogExtended(unittest.TestCase):
    def test_default_content_types_include_dlp_powerbi_forms(self):
        ual = UnifiedAuditLogProvider.__new__(UnifiedAuditLogProvider)
        # Instantiate minimally to inspect default content_types
        import pathlib
        import tempfile

        from terminalvelocity.providers.base import CheckpointStore, RawLogCache

        ual.tenant_id = "t1"
        ual.client_id = "c1"
        ual.client_secret = "s1"
        ual.checkpoint_store = CheckpointStore(pathlib.Path(tempfile.mkdtemp()))
        ual.raw_log_cache = RawLogCache(pathlib.Path(tempfile.mkdtemp()))
        ual.enable_raw_cache = False
        ual._access_tokens = {}
        ual._owns_client = True
        ual.http_client = None
        ual.authority = "https://login.microsoftonline.com"
        ual.timeout = 30.0
        ual.max_retries = 5
        ual.poll_window = timedelta(minutes=15)
        ual.content_types = (
            UnifiedAuditLogProvider.__init__.__wrapped__
            if hasattr(UnifiedAuditLogProvider.__init__, "__wrapped__")
            else None
        )
        # Just test defaults via the class directly
        {
            "tenant_id": "t1",
            "client_id": "c1",
            "client_secret": "s1",
            "checkpoint_store": CheckpointStore(pathlib.Path(tempfile.mkdtemp())),
        }
        # We can't call __init__ without an httpx client — use the transport approach
        import httpx as _httpx

        async def _get_token_mock(scope):
            return "tok"

        transport = _AsyncMockTransport(
            {
                "subscriptions/list": [],
            }
        )
        client = _httpx.AsyncClient(transport=transport)
        from terminalvelocity.providers.base import CheckpointStore as CS

        real = UnifiedAuditLogProvider(
            tenant_id="t1",
            client_id="c1",
            client_secret="s1",
            checkpoint_store=CS(pathlib.Path(tempfile.mkdtemp())),
            http_client=client,
        )
        assert "DLP.All" in real.content_types
        assert "Audit.PowerBI" in real.content_types
        assert "MicrosoftForms" in real.content_types

    def test_dlp_event_normalization(self):
        import pathlib
        import tempfile

        import httpx as _httpx

        from terminalvelocity.providers.base import CheckpointStore as CS

        transport = _AsyncMockTransport({"subscriptions/list": []})
        provider = UnifiedAuditLogProvider(
            tenant_id="t1",
            client_id="c1",
            client_secret="s1",
            checkpoint_store=CS(pathlib.Path(tempfile.mkdtemp())),
            http_client=_httpx.AsyncClient(transport=transport),
        )
        event = provider.normalize(
            {
                "CreationTime": "2025-01-01T00:20:00Z",
                "Workload": "SecurityComplianceCenter",
                "UserId": "admin@contoso.com",
                "PolicyDetails": [{"PolicyName": "SSN Detection Policy"}],
                "SensitiveInfoTypeData": [{"SensitiveType": "U.S. SSN"}],
                "ObjectId": "/sites/finance/docs/payroll.xlsx",
                "OrganizationId": "org-1",
                "Id": "dlp-1",
            }
        )
        assert event.service == "Microsoft Purview DLP"
        assert event.action == "SSN Detection Policy"
        assert event.severity == "high"
        assert event.actor == "admin@contoso.com"

    def test_powerbi_event_normalization(self):
        import pathlib
        import tempfile

        import httpx as _httpx

        from terminalvelocity.providers.base import CheckpointStore as CS

        transport = _AsyncMockTransport({"subscriptions/list": []})
        provider = UnifiedAuditLogProvider(
            tenant_id="t1",
            client_id="c1",
            client_secret="s1",
            checkpoint_store=CS(pathlib.Path(tempfile.mkdtemp())),
            http_client=_httpx.AsyncClient(transport=transport),
        )
        event = provider.normalize(
            {
                "CreationTime": "2025-01-01T00:21:00Z",
                "Workload": "PowerBI",
                "UserId": "analyst@contoso.com",
                "Operation": "ExportReport",
                "DatasetName": "Sales Report 2025",
                "OrganizationId": "org-1",
                "Id": "pbi-1",
            }
        )
        assert event.service == "Microsoft Power BI"
        assert event.action == "ExportReport"
        assert event.target == "Sales Report 2025"

    def test_forms_event_normalization(self):
        import pathlib
        import tempfile

        import httpx as _httpx

        from terminalvelocity.providers.base import CheckpointStore as CS

        transport = _AsyncMockTransport({"subscriptions/list": []})
        provider = UnifiedAuditLogProvider(
            tenant_id="t1",
            client_id="c1",
            client_secret="s1",
            checkpoint_store=CS(pathlib.Path(tempfile.mkdtemp())),
            http_client=_httpx.AsyncClient(transport=transport),
        )
        event = provider.normalize(
            {
                "CreationTime": "2025-01-01T00:22:00Z",
                "Workload": "MicrosoftForms",
                "UserId": "user@contoso.com",
                "Operation": "ViewResponse",
                "FormName": "IT Access Request",
                "OrganizationId": "org-1",
                "Id": "forms-1",
            }
        )
        assert event.service == "Microsoft Forms"
        assert event.action == "ViewResponse"
        assert event.target == "IT Access Request"


# ---------------------------------------------------------------------------
# DefenderXdrProvider — vulnerability management
# ---------------------------------------------------------------------------


class TestDefenderXdrVulnerabilities(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp()
        self.start = datetime(2025, 1, 1, tzinfo=UTC)
        self.end = datetime(2025, 1, 1, 1, tzinfo=UTC)

    def _provider(self, routes, include_vulnerabilities=True):
        from pathlib import Path

        return _make_provider(
            DefenderXdrProvider,
            routes,
            Path(self.tmp),
            include_vulnerabilities=include_vulnerabilities,
        )

    def test_vulnerability_normalization(self):
        routes = {
            "/security/incidents": {"value": []},
            "/security/alerts_v2": {"value": []},
            "/machines": {"value": []},
            "/vulnerabilities": [
                {
                    "id": "CVE-2024-1234",
                    "severity": "critical",
                    "exposedMachines": 42,
                    "publicExploit": True,
                    "publishedOn": "2024-06-01T00:00:00Z",
                    "cvssV3": 9.8,
                }
            ],
            "/machines/SoftwareVulnerabilitiesByMachine": [],
        }
        provider = self._provider(routes)
        events = run(provider.fetch(start_time=self.start, end_time=self.end))
        vuln_events = [e for e in events if e.service == "Microsoft Defender Vulnerability Management"]
        assert len(vuln_events) == 1
        ev = vuln_events[0]
        assert ev.action == "CVE-2024-1234"
        assert ev.result == "failure"  # public exploit present
        assert ev.severity == "critical"
        assert "42 machines" in ev.target

    def test_vulnerability_disabled_by_default(self):
        routes = {
            "/security/incidents": {"value": []},
            "/security/alerts_v2": {"value": []},
            "/machines": {"value": []},
        }
        provider = self._provider(routes, include_vulnerabilities=False)
        events = run(provider.fetch(start_time=self.start, end_time=self.end))
        vuln_events = [e for e in events if e.service == "Microsoft Defender Vulnerability Management"]
        assert len(vuln_events) == 0


# ---------------------------------------------------------------------------
# SecureScoreProvider
# ---------------------------------------------------------------------------


class TestSecureScoreProvider(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp()
        self.start = datetime(2025, 1, 1, tzinfo=UTC)
        self.end = datetime(2025, 1, 2, tzinfo=UTC)

    def _provider(self, routes):
        from pathlib import Path

        return _make_provider(SecureScoreProvider, routes, Path(self.tmp))

    def test_score_snapshot_normalization(self):
        routes = {
            "/security/secureScores": {
                "value": [
                    {
                        "id": "score-1",
                        "createdDateTime": "2025-01-01T08:00:00Z",
                        "currentScore": 350.0,
                        "maxScore": 500.0,
                        "tenantId": "t1",
                        "averageComparativeScores": [{"basis": "AllTenants", "averageScore": 320.0}],
                    }
                ]
            },
            "/security/secureScoreControlProfiles": {"value": []},
        }
        provider = self._provider(routes)
        events = run(provider.fetch(start_time=self.start, end_time=self.end))
        assert len(events) == 1
        ev = events[0]
        assert ev.action == "SecureScoreSnapshot"
        assert "350" in ev.target
        assert ev.result == "success"
        # delta is +30 (above average), so severity should be info
        assert ev.severity == "info"

    def test_control_profile_normalization(self):
        routes = {
            "/security/secureScores": {"value": []},
            "/security/secureScoreControlProfiles": {
                "value": [
                    {
                        "id": "ctrl-mfa",
                        "title": "Require MFA for all users",
                        "implementationStatus": "implemented",
                        "lastModifiedDateTime": "2025-01-01T09:00:00Z",
                        "rank": 1,
                    }
                ]
            },
        }
        provider = self._provider(routes)
        events = run(provider.fetch(start_time=self.start, end_time=self.end))
        assert len(events) == 1
        ev = events[0]
        assert ev.action == "SecureScoreControlProfile"
        assert ev.target == "Require MFA for all users"
        assert ev.result == "success"


# ---------------------------------------------------------------------------
# ServiceHealthProvider
# ---------------------------------------------------------------------------


class TestServiceHealthProvider(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp()
        self.start = datetime(2025, 1, 1, tzinfo=UTC)
        self.end = datetime(2025, 1, 2, tzinfo=UTC)

    def _provider(self, routes):
        from pathlib import Path

        return _make_provider(ServiceHealthProvider, routes, Path(self.tmp))

    def test_service_issue_normalization(self):
        routes = {
            "/admin/serviceAnnouncement/issues": {
                "value": [
                    {
                        "id": "issue-1",
                        "title": "Exchange Online degraded performance",
                        "service": "Exchange Online",
                        "classification": "incident",
                        "status": "investigating",
                        "lastModifiedDateTime": "2025-01-01T12:00:00Z",
                        "startDateTime": "2025-01-01T11:00:00Z",
                    }
                ]
            },
            "/admin/serviceAnnouncement/healthOverviews": {"value": []},
        }
        provider = self._provider(routes)
        events = run(provider.fetch(start_time=self.start, end_time=self.end))
        assert len(events) == 1
        ev = events[0]
        assert ev.action == "Exchange Online degraded performance"
        assert ev.service == "Exchange Online"
        assert ev.result == "failure"
        assert ev.severity == "medium"

    def test_health_overview_normalization(self):
        routes = {
            "/admin/serviceAnnouncement/issues": {"value": []},
            "/admin/serviceAnnouncement/healthOverviews": {
                "value": [
                    {
                        "id": "overview-1",
                        "service": "Microsoft Teams",
                        "status": "serviceRestored",
                    }
                ]
            },
        }
        provider = self._provider(routes)
        events = run(provider.fetch(start_time=self.start, end_time=self.end))
        assert len(events) == 1
        ev = events[0]
        assert ev.action == "ServiceHealthOverview"
        assert ev.service == "Microsoft Teams"
        assert ev.result == "success"


# ---------------------------------------------------------------------------
# AdvancedHuntingProvider
# ---------------------------------------------------------------------------


class TestAdvancedHuntingProvider(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp()
        self.start = datetime(2025, 1, 1, tzinfo=UTC)
        self.end = datetime(2025, 1, 1, 1, tzinfo=UTC)

    def test_identity_logon_events_normalization(self):
        from pathlib import Path

        async def fake_request_json(method, url, *, scope, **kwargs):
            return {
                "results": [
                    {
                        "Timestamp": "2025-01-01T00:30:00Z",
                        "AccountUpn": "victim@contoso.com",
                        "ActionType": "LogonFailed",
                        "Application": "Exchange Online",
                        "FailureReason": "WrongPassword",
                        "IPAddress": "5.6.7.8",
                        "ReportId": "rpt-1",
                        "_tv_table": "IdentityLogonEvents",
                    }
                ]
            }

        provider = AdvancedHuntingProvider(
            tenant_id="t1",
            client_id="c1",
            client_secret="s1",
            checkpoint_store=CheckpointStore(Path(self.tmp)),
            http_client=httpx.AsyncClient(transport=_AsyncMockTransport({})),
            queries=[("IdentityLogonEvents", "IdentityLogonEvents | limit 1")],
        )
        provider._request_json = fake_request_json  # type: ignore[method-assign]

        events = run(provider.fetch(start_time=self.start, end_time=self.end))
        assert len(events) == 1
        ev = events[0]
        assert ev.actor == "victim@contoso.com"
        assert ev.action == "LogonFailed"
        assert "IdentityLogonEvents" in ev.service

    def test_email_events_delivery_action_mapping(self):
        from pathlib import Path

        provider = AdvancedHuntingProvider(
            tenant_id="t1",
            client_id="c1",
            client_secret="s1",
            checkpoint_store=CheckpointStore(Path(self.tmp)),
            http_client=httpx.AsyncClient(transport=_AsyncMockTransport({})),
        )
        # Simulate a blocked email
        blocked_row = {
            "Timestamp": "2025-01-01T00:31:00Z",
            "SenderFromAddress": "phish@evil.test",
            "RecipientEmailAddress": "user@contoso.com",
            "Subject": "Urgent: wire transfer",
            "DeliveryAction": "Blocked",
            "ThreatTypes": "Phish",
            "ConfidenceLevel": "high",
            "NetworkMessageId": "net-1",
            "ReportId": "rpt-2",
            "_tv_table": "EmailEvents",
        }
        ev = provider.normalize(blocked_row)
        assert ev.result == "failure"
        assert ev.severity == "high"
        assert ev.actor == "phish@evil.test"

    def test_delivered_email_maps_to_success(self):
        from pathlib import Path

        provider = AdvancedHuntingProvider(
            tenant_id="t1",
            client_id="c1",
            client_secret="s1",
            checkpoint_store=CheckpointStore(Path(self.tmp)),
            http_client=httpx.AsyncClient(transport=_AsyncMockTransport({})),
        )
        row = {
            "Timestamp": "2025-01-01T00:32:00Z",
            "SenderFromAddress": "legit@partner.com",
            "Subject": "Invoice",
            "DeliveryAction": "Delivered",
            "_tv_table": "EmailEvents",
        }
        ev = provider.normalize(row)
        assert ev.result == "success"


# ---------------------------------------------------------------------------
# AttackSimulationProvider
# ---------------------------------------------------------------------------


class TestAttackSimulationProvider(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp()
        self.start = datetime(2025, 1, 1, tzinfo=UTC)
        self.end = datetime(2025, 2, 1, tzinfo=UTC)

    def _provider(self, routes):
        from pathlib import Path

        return _make_provider(AttackSimulationProvider, routes, Path(self.tmp))

    def test_simulation_user_result_normalization(self):
        sim_id = "sim-1"
        routes = {
            "/security/attackSimulation/simulations": {
                "value": [
                    {
                        "id": sim_id,
                        "displayName": "Q1 Phishing Test",
                        "launchDateTime": "2025-01-15T09:00:00Z",
                        "attackTechnique": "CredentialHarvesting",
                    }
                ]
            },
            f"/security/attackSimulation/simulations/{sim_id}/simulationUsers": {
                "value": [
                    {
                        "id": "user-result-1",
                        "simulationUser": {"email": "victim@contoso.com"},
                        "assignedDateTime": "2025-01-15T09:00:00Z",
                        "simulationEvents": [
                            {"simulationEventType": "SimulationEmailSent"},
                            {"simulationEventType": "LinkClicked"},
                            {"simulationEventType": "CredentialsEntered"},
                        ],
                    }
                ]
            },
        }
        provider = self._provider(routes)
        events = run(provider.fetch(start_time=self.start, end_time=self.end))
        assert len(events) == 1
        ev = events[0]
        assert ev.actor == "victim@contoso.com"
        assert ev.result == "failure"  # credentials entered
        assert ev.severity == "critical"
        assert "Q1 Phishing Test" in ev.action

    def test_reported_phish_maps_to_success(self):
        from pathlib import Path

        provider = AttackSimulationProvider(
            tenant_id="t1",
            client_id="c1",
            client_secret="s1",
            checkpoint_store=CheckpointStore(Path(self.tmp)),
            http_client=httpx.AsyncClient(transport=_AsyncMockTransport({})),
        )
        row = {
            "_tv_simulation_name": "Test Sim",
            "_tv_simulation_technique": "Phishing",
            "simulationUser": {"email": "hero@contoso.com"},
            "assignedDateTime": "2025-01-15T09:00:00Z",
            "simulationEvents": [
                {"simulationEventType": "SimulationEmailSent"},
                {"simulationEventType": "Reported"},
            ],
        }
        ev = provider.normalize(row)
        assert ev.actor == "hero@contoso.com"
        assert ev.result == "success"
        assert ev.severity == "low"


# ---------------------------------------------------------------------------
# PIMProvider
# ---------------------------------------------------------------------------


class TestPIMProvider(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp()
        self.start = datetime(2025, 1, 1, tzinfo=UTC)
        self.end = datetime(2025, 1, 1, 1, tzinfo=UTC)

    def _provider(self, routes):
        from pathlib import Path

        return _make_provider(PIMProvider, routes, Path(self.tmp))

    def test_role_activation_request_normalization(self):
        routes = {
            "/identityGovernance/privilegedAccess/aadRoles/roleAssignmentRequests": {
                "value": [
                    {
                        "id": "req-1",
                        "requestedDateTime": "2025-01-01T00:40:00Z",
                        "requestType": "UserAdd",
                        "assignmentState": "Active",
                        "status": "Granted",
                        "reason": "Emergency incident response",
                        "roleDefinition": {"displayName": "Global Administrator"},
                        "subject": {"userPrincipalName": "admin@contoso.com"},
                        "ticketInfo": {"ticketNumber": "INC-1234"},
                    }
                ]
            },
            "/identityGovernance/privilegedAccess/aadRoles/roleAssignments": {"value": []},
        }
        provider = self._provider(routes)
        events = run(provider.fetch(start_time=self.start, end_time=self.end))
        assert len(events) == 1
        ev = events[0]
        assert "pim:" in ev.action
        assert ev.target == "Global Administrator"
        assert ev.actor == "admin@contoso.com"
        assert ev.result == "success"
        assert ev.severity == "high"
        assert ev.raw.get("_tv_reason") == "Emergency incident response"
        assert ev.raw.get("_tv_ticket_ref") == "INC-1234"

    def test_active_assignment_normalization(self):
        routes = {
            "/identityGovernance/privilegedAccess/aadRoles/roleAssignmentRequests": {"value": []},
            "/identityGovernance/privilegedAccess/aadRoles/roleAssignments": {
                "value": [
                    {
                        "id": "assign-1",
                        "startDateTime": "2025-01-01T00:00:00Z",
                        "roleDefinition": {"displayName": "Security Reader"},
                        "subject": {"userPrincipalName": "analyst@contoso.com"},
                    }
                ]
            },
        }
        provider = self._provider(routes)
        events = run(provider.fetch(start_time=self.start, end_time=self.end))
        assert len(events) == 1
        ev = events[0]
        assert ev.action == "pim:active-assignment"
        assert ev.target == "Security Reader"
        assert ev.actor == "analyst@contoso.com"
        assert ev.severity == "low"


# ---------------------------------------------------------------------------
# CrossProviderEnricher — risk linking
# ---------------------------------------------------------------------------


class TestCrossProviderEnricherRiskLinking(unittest.TestCase):
    def _make_sign_in(self, correlation_id: str, request_id: str | None = None) -> NormalizedEvent:
        return NormalizedEvent(
            timestamp=datetime(2025, 1, 1, 0, 5, tzinfo=UTC),
            provider="entra_id",
            service="Microsoft Entra ID Sign-In",
            actor="victim@contoso.com",
            action="sign-in",
            result="success",
            correlation_id=correlation_id,
            request_id=request_id,
            raw={},
        )

    def _make_risk_detection(self, correlation_id: str | None = None, request_id: str | None = None) -> NormalizedEvent:
        return NormalizedEvent(
            timestamp=datetime(2025, 1, 1, 0, 4, tzinfo=UTC),
            provider="identity_protection",
            service="Microsoft Entra ID Identity Protection",
            actor="victim@contoso.com",
            action="anonymizedIPAddress",
            severity="high",
            correlation_id=correlation_id,
            request_id=request_id,
            raw={},
        )

    def test_risk_detection_linked_to_sign_in_via_correlation_id(self):
        sign_in = self._make_sign_in(correlation_id="shared-corr-1")
        risk = self._make_risk_detection(correlation_id="shared-corr-1")
        enricher = CrossProviderEnricher()
        enriched = enricher.enrich([sign_in, risk])
        sign_in_enriched = next(e for e in enriched if e.action == "sign-in")
        assert sign_in_enriched.model_extra.get("_tv_risk_linked") is True
        risk_ids = sign_in_enriched.model_extra.get("_tv_risk_event_ids") or []
        assert risk.cache_key() in risk_ids

    def test_no_false_link_when_no_shared_id(self):
        sign_in = self._make_sign_in(correlation_id="unique-corr-A")
        risk = self._make_risk_detection(correlation_id="unique-corr-B")
        enricher = CrossProviderEnricher()
        enriched = enricher.enrich([sign_in, risk])
        sign_in_enriched = next(e for e in enriched if e.action == "sign-in")
        assert not sign_in_enriched.model_extra.get("_tv_risk_linked")

    def test_risk_linked_via_request_id(self):
        sign_in = self._make_sign_in(correlation_id="corr-x", request_id="req-shared")
        risk = self._make_risk_detection(request_id="req-shared")
        enricher = CrossProviderEnricher()
        enriched = enricher.enrich([sign_in, risk])
        sign_in_enriched = next(e for e in enriched if e.action == "sign-in")
        assert sign_in_enriched.model_extra.get("_tv_risk_linked") is True


# ---------------------------------------------------------------------------
# ProviderRegistry — new aliases
# ---------------------------------------------------------------------------


class TestRegistryNewAliases(unittest.TestCase):
    NEW_ALIASES = {  # noqa: RUF012
        "identity_protection": "IdentityProtectionProvider",
        "entra_identity_protection": "IdentityProtectionProvider",
        "advanced_hunting": "AdvancedHuntingProvider",
        "hunting": "AdvancedHuntingProvider",
        "secure_score": "SecureScoreProvider",
        "service_health": "ServiceHealthProvider",
        "m365_health": "ServiceHealthProvider",
        "attack_simulation": "AttackSimulationProvider",
        "sim_training": "AttackSimulationProvider",
        "pim": "PIMProvider",
        "privileged_identity_management": "PIMProvider",
    }

    def test_all_new_aliases_resolve(self):
        for alias, expected_class_name in self.NEW_ALIASES.items():
            with self.subTest(alias=alias):
                cls = provider_registry.get(alias)
                self.assertEqual(cls.__name__, expected_class_name)


if __name__ == "__main__":
    unittest.main()
