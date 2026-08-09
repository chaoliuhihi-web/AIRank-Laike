from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4
from zipfile import ZipFile

import pytest
from sqlalchemy import bindparam, create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api.main import (
    BrandCheckRequest,
    BuyerQuestionCreateRequest,
    CompetitorCreateRequest,
    DownloadReceiptRequest,
    MySQLAssetBundleRepository,
    MySQLProjectRepository,
    MySQLReportRepository,
    MySQLScanRepository,
    ProjectCreateRequest,
    ScanRunCreateRequest,
    run_brand_check,
    scan_dispatch_mode,
)
from apps.api.provider_scan import ProviderCallError, ProviderScanResult, ProviderUnavailable
from apps.api.delivery_routes import (
    ContentReviewRequest,
    MySQLDeliveryRepository,
    PublishEvidenceRequest,
    PublishPackageCreateRequest,
)
from apps.api.knowledge_routes import (
    ComparisonCellRequest,
    ComparisonContentCreateRequest,
    ComparisonDimensionRequest,
    ComparisonSubjectRequest,
    ExplainerContentCreateRequest,
    ExplainerFactAssignmentRequest,
    FactConflictCreateRequest,
    FactConflictResolveRequest,
    FactProposalRequest,
    FactRevisionReviewRequest,
    GovernedContentCreateRequest,
    KnowledgeSourceCreateRequest,
    MySQLKnowledgeRepository,
    derive_knowledge_governance,
)
from apps.api.provider_operations import MySQLProviderOperations
from apps.api.provider_model_lifecycle import (
    MySQLProviderModelLifecycle,
    ProviderModelMigrationApproveRequest,
    ProviderModelMigrationCreateRequest,
    ProviderModelMigrationError,
    ProviderModelMigrationValidateRequest,
)
from apps.api.provider_usage import MySQLProviderUsageLedger, persist_provider_usage_event
from apps.api.provider_credentials import (
    CredentialRevokeRequest,
    CredentialUpsertRequest,
    MySQLProviderCredentialVault,
)
from apps.api.evidence_routes import MySQLEvidenceRepository
from apps.api.evidence_gap_routes import DeriveEvidenceGapsRequest, MySQLEvidenceGapRepository
from apps.api.fact_acquisition_routes import (
    FactAcquisitionEvidenceBindRequest,
    FactAcquisitionTaskCreateRequest,
    MySQLFactAcquisitionRepository,
)
from apps.api.retest_routes import MySQLRetestRepository, _comparison_data
from apps.api.report_packet import MySQLReportEvidencePacketRepository
from apps.api.question_routes import (
    MySQLQuestionGovernanceRepository,
    QuestionMapCompileRequest,
    QuestionObservationImportRequest,
    QuestionReviewRequest,
)
from apps.api.citation_support_routes import (
    CitationClaimCreateRequest,
    CitationSupportReviewCreateRequest,
    FactAccuracyReviewCreateRequest,
    MySQLCitationSupportRepository,
)
from apps.api.evidence_review_routes import (
    CitationReviewCaseCreateRequest,
    EvidenceReviewAssignmentClaimRequest,
    EvidenceReviewAssignmentHeartbeatRequest,
    EvidenceReviewAssignmentReleaseRequest,
    EvidenceReviewDecisionRequest,
    FactReviewCaseCreateRequest,
    MySQLEvidenceReviewEscalationRepository,
    MySQLEvidenceReviewRepository,
)
from apps.api.reviewer_routing_routes import (
    MySQLReviewerRoutingRepository,
    ReviewerDirectoryBindingPutRequest,
    ReviewerRoleRoutePutRequest,
    ReviewerTeamCreateRequest,
    ReviewerTeamMemberUpsertRequest,
)
from apps.api.opportunity_routing_routes import (
    MySQLOpportunityActionRoutingRepository,
    OpportunityActionMemberUpsertRequest,
    OpportunityActionTeamCreateRequest,
)
from apps.api.opportunity_directory_routes import (
    MySQLOpportunityActionDirectoryRepository,
    OpportunityActionDirectoryBindingPutRequest,
)
from airank_evidence import FilesystemObjectStorage, canonical_json_sha256
from airank_domain.measurement import sha256_text
from airank_score.quality import build_measurement_quality_report
from airank_provider_gateway import (
    CredentialKeyring,
    HealthState,
    ImplementationStatus,
    PROVIDER_MANIFESTS,
    ProbeLevel,
    ProbeResult,
    ProviderCapabilities,
    ProviderCapacityLease,
    ProviderGatewayError,
    ProviderManifest,
    ProviderRequestContext,
    ProviderSettings,
    resolve_provider_routes,
)
from airank_outbound_security import OutboundResponse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "worker"))
sys.path.insert(0, str(ROOT / "packages" / "domain" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "xinghe-adapter" / "src"))

from airank_domain import AsyncJob, AsyncJobStatus  # noqa: E402
from airank_worker import (  # noqa: E402
    MySQLJobLeaseStore,
    MySQLPublishExecutionRepository,
    PublisherError,
    PublisherGateway,
    ScanWorkerError,
    run_next_real_scan_job,
    run_next_publish_job,
    run_next_reviewer_directory_sync_job,
    run_next_opportunity_directory_sync_job,
    MySQLReviewNotificationRepository,
    ReviewNotificationConfig,
    ReviewNotificationWebhookClient,
    run_next_review_notification,
)
from airank_scheduler import (  # noqa: E402
    MySQLReviewEscalationScheduler,
    MySQLReviewerDirectorySyncScheduler,
    MySQLOpportunityDirectorySyncScheduler,
)
from airank_xinghe_adapter import (  # noqa: E402
    CapabilityProbe,
    CapabilityStatus,
    ProbeConfig,
    YudaoReviewer,
    YudaoReviewerDirectorySnapshot,
)


DEFAULT_MYSQL_URL = "mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike?charset=utf8mb4"
EXPECTED_ALEMBIC_HEAD = "20260809_0044"


def require_real_flag(flag: str) -> None:
    if os.getenv(flag) != "1":
        pytest.skip(f"set {flag}=1 to run real integration checks")


def database_url() -> str:
    return os.getenv("AIRANK_DATABASE_URL", DEFAULT_MYSQL_URL)


def cleanup_tenant(engine: Any, tenant_id: str) -> None:
    with engine.begin() as conn:
        tables = conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND column_name = 'tenant_id'
                  AND table_name LIKE 'airank\\_%'
                """
            )
        ).scalars().all()
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        try:
            for table_name in tables:
                conn.execute(
                    text(f"DELETE FROM `{table_name}` WHERE tenant_id = :tenant_id"),
                    {"tenant_id": tenant_id},
                )
        finally:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))


def test_real_mysql_alembic_head_and_schema_contract() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    env = {**os.environ, "AIRANK_DATABASE_URL": database_url()}
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "apps" / "api",
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr

    engine = create_engine(database_url(), pool_pre_ping=True)
    expected_database = engine.url.database
    assert expected_database
    with engine.connect() as conn:
        assert conn.execute(text("SELECT DATABASE()")).scalar_one() == expected_database
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == EXPECTED_ALEMBIC_HEAD
        table_count = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_name LIKE 'airank\\_%'
                """
            )
        ).scalar_one()
        assert table_count == 109
        for table_name in (
            "airank_provider_model_migrations",
            "airank_provider_model_migration_events",
            "airank_provider_price_versions",
            "airank_provider_usage_costs",
            "airank_provider_credentials",
            "airank_operation_guards",
            "airank_operation_guard_events",
            "airank_provider_credential_events",
            "airank_evidence_review_teams",
            "airank_evidence_review_team_members",
            "airank_evidence_review_routes",
            "airank_evidence_review_team_sync_bindings",
            "airank_evidence_review_team_sync_runs",
            "airank_notification_deliveries",
            "airank_notification_delivery_receipts",
            "airank_content_gap_derivation_runs",
            "airank_fact_acquisition_tasks",
            "airank_fact_acquisition_task_events",
            "airank_opportunity_derivation_runs",
            "airank_intervention_opportunity_snapshots",
            "airank_opportunity_actions",
            "airank_opportunity_action_events",
            "airank_opportunity_action_teams",
            "airank_opportunity_action_team_members",
            "airank_opportunity_action_routes",
            "airank_opportunity_action_plans",
            "airank_opportunity_action_dependencies",
            "airank_opportunity_action_plan_events",
            "airank_opportunity_action_team_sync_bindings",
            "airank_opportunity_action_team_sync_runs",
            "airank_opportunity_capacity_calendars",
            "airank_opportunity_capacity_exceptions",
            "airank_opportunity_capacity_events",
            "airank_opportunity_schedule_runs",
            "airank_opportunity_schedule_items",
        ):
            assert conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema=DATABASE() AND table_name=:table_name"
                ),
                {"table_name": table_name},
            ).scalar_one() == 1
        usage_hash_column = conn.execute(
            text(
                """
                SELECT is_nullable
                FROM information_schema.columns
                WHERE table_schema=DATABASE()
                  AND table_name='airank_provider_usage_events'
                  AND column_name='raw_usage_sha256'
                """
            )
        ).scalar_one()
        assert usage_hash_column == "NO"
        assert conn.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema=DATABASE()
                  AND table_name='airank_publish_attempts'
                  AND column_name='operation_id'
                """
            )
        ).scalar_one() == 1
        assert conn.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.referential_constraints
                WHERE constraint_schema=DATABASE()
                  AND constraint_name='fk_airank_publish_attempt_operation'
                """
            )
        ).scalar_one() == 1
        assert conn.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.statistics
                WHERE table_schema=DATABASE()
                  AND table_name='airank_publish_attempts'
                  AND index_name='uk_airank_publish_attempt_operation'
                  AND non_unique=0
                """
            )
        ).scalar_one() == 1
        assert conn.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema=DATABASE()
                  AND table_name='airank_report_evidence_packets'
                  AND column_name='integrity_audit_id'
                """
            )
        ).scalar_one() == 1
        assert conn.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema=DATABASE()
                  AND table_name='airank_provider_request_audits'
                  AND column_name IN ('credential_source', 'credential_id', 'credential_version')
                """
            )
        ).scalar_one() == 3
        assert conn.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema=DATABASE()
                  AND table_name='airank_provider_credential_events'
                  AND column_name='event_sequence'
                """
            )
        ).scalar_one() == 1
        assert conn.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema=DATABASE()
                  AND table_name='airank_content_gaps'
                  AND column_name IN (
                    'contract_version', 'derivation_policy',
                    'answer_snapshot_ids', 'evidence_snapshot_ids',
                    'citation_ids', 'fact_atom_ids', 'evidence_summary_json',
                    'evidence_sha256', 'quality_report_sha256', 'derived_by'
                  )
                """
            )
        ).scalar_one() == 10
        assert conn.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema=DATABASE()
                  AND table_name='airank_provider_request_audits'
                  AND column_name='route_id'
                """
            )
        ).scalar_one() == 1
        assert conn.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema=DATABASE()
                  AND table_name='airank_provider_routes'
                  AND column_name='request_contract_json'
                """
            )
        ).scalar_one() == 1
        assert conn.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema=DATABASE()
                  AND table_name='airank_provider_manifests'
                  AND column_name='request_defaults_json'
                """
            )
        ).scalar_one() == 1
        for table_name in (
            "airank_provider_route_controls",
            "airank_provider_route_control_events",
            "airank_report_evidence_packets",
        ):
            assert conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_schema=DATABASE() AND table_name=:table_name
                    """
                ),
                {"table_name": table_name},
            ).scalar_one() == 1

        url_columns = (
            ("airank_projects", "website_url"),
            ("airank_competitors", "website_url"),
            ("airank_source_citations", "url"),
            ("airank_fact_sources", "source_url"),
            ("airank_content_assets", "target_url"),
            ("airank_publish_packages", "published_url"),
            ("airank_object_refs", "object_uri"),
            ("airank_question_observation_batches", "source_uri"),
            ("airank_citation_source_captures", "requested_url"),
            ("airank_citation_source_captures", "final_url"),
        )
        for table_name, column_name in url_columns:
            url_length = conn.execute(
                text(
                    """
                    SELECT CHARACTER_MAXIMUM_LENGTH
                    FROM information_schema.columns
                    WHERE table_schema = DATABASE()
                      AND table_name = :table_name
                      AND column_name = :column_name
                    """
                ),
                {"table_name": table_name, "column_name": column_name},
            ).scalar_one()
            assert url_length == 2048


class _VerifiedCredentialProbe:
    def __init__(self) -> None:
        self.call_count = 0

    def verify(self, *, tenant_id: str, provider: str, route_id: str, secret: str) -> dict[str, object]:
        self.call_count += 1
        assert tenant_id.startswith("tenant_credential_it_")
        assert provider == "qianwen"
        assert route_id == "qianwen:default"
        assert secret.startswith("sk-")
        return {
            "status": "verified",
            "probe_level": "l3_generation",
            "model": "qwen-integration",
            "endpoint_host": "dashscope.example.test",
            "request_id_present": True,
            "provider_request_id_sha256": "b" * 64,
            "duration_ms": 9,
            "evidence_grade": "provider_api_search_unverified",
            "verified_at": "2026-08-09T01:00:00+00:00",
        }


def test_real_mysql_provider_credential_rotation_chain_and_fail_closed_revoke() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_credential_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    environment = {
        "QIANWEN_API_KEY": "environment-fallback-secret",
        "QIANWEN_API_URL": "https://dashscope.example.test/v1/chat/completions",
        "QIANWEN_MODEL": "qwen-integration",
        "AIRANK_ALLOW_CUSTOM_PROVIDER_ENDPOINTS": "true",
    }
    keyring = CredentialKeyring(
        active_encryption_key_id="enc-it-v1",
        encryption_keys={"enc-it-v1": b"e" * 32},
        active_fingerprint_key_id="fp-it-v1",
        fingerprint_keys={"fp-it-v1": b"f" * 32},
    )
    probe = _VerifiedCredentialProbe()
    repository = MySQLProviderCredentialVault(
        database_url(),
        keyring,
        verifier=probe,
        env=environment,
    )
    first_secret = "sk-real-mysql-first-secret"
    second_secret = "sk-real-mysql-second-secret"

    try:
        first_request = CredentialUpsertRequest(
            secret=first_secret,
            expected_version=0,
            reason="initial integration credential",
            confirm_billable=True,
        )
        first = repository.upsert(
            tenant_id,
            "qianwen",
            "qianwen:default",
            first_request,
            "integration-admin",
            "trc_credential_1",
            "integration-credential-upsert-1",
        )
        first_replay = repository.upsert(
            tenant_id,
            "qianwen",
            "qianwen:default",
            first_request,
            "integration-admin",
            "trc_credential_1_replay",
            "integration-credential-upsert-1",
        )
        second = repository.upsert(
            tenant_id,
            "qianwen",
            "qianwen:default",
            CredentialUpsertRequest(
                secret=second_secret,
                expected_version=1,
                reason="scheduled integration rotation",
                confirm_billable=True,
            ),
            "integration-admin",
            "trc_credential_2",
            "integration-credential-upsert-2",
        )
        assert first.credential_version == 1
        assert first_replay.idempotent_replay is True
        assert first_replay.operation_id == first.operation_id
        assert second.credential_version == 2
        assert probe.call_count == 2

        resolved = repository.resolve_settings(
            "qianwen",
            "qianwen:default",
            ProviderSettings(
                endpoint=environment["QIANWEN_API_URL"],
                api_key=environment["QIANWEN_API_KEY"],
                model=environment["QIANWEN_MODEL"],
                disabled=False,
                max_tokens=32,
                temperature=0.2,
                reasoning_effort=None,
                request_kind="chat_completions_search",
                allowed_endpoint_hosts=("dashscope.example.test",),
                allow_custom_endpoint=True,
            ),
            context=ProviderRequestContext(tenant_id=tenant_id),
        )
        assert resolved.api_key == second_secret
        assert resolved.credential_source == "tenant_vault"
        assert resolved.credential_id == second.credential_id

        repository.revoke(
            tenant_id,
            "qianwen",
            "qianwen:default",
            CredentialRevokeRequest(expected_version=2, reason="integration revoke verification"),
            "integration-admin",
            "trc_credential_3",
            "integration-credential-revoke-2",
        )

        unknown_claim = repository.operation_guard.claim(
            tenant_id=tenant_id,
            operation_type="provider_credential.upsert",
            resource_key="qianwen/qianwen:default",
            idempotency_key="integration-credential-unknown-outcome",
            request_sha256="c" * 64,
            request_key_id="fp-it-v1",
            actor="integration-admin",
            trace_id="trc_credential_unknown",
        )
        repository.operation_guard.mark_external_started(
            unknown_claim.operation_id,
            "integration-admin",
            "trc_credential_unknown",
        )
        unknown_operations = repository.list_operations(
            tenant_id, state="external_started"
        )
        assert unknown_operations.reconciliation_required_count == 1
        assert unknown_operations.operations[0].operation_id == unknown_claim.operation_id
        unknown_detail = repository.get_operation(tenant_id, unknown_claim.operation_id)
        assert unknown_detail is not None
        assert [event.event_sequence for event in unknown_detail.events] == [1, 2]
        assert repository.get_operation("tenant_other", unknown_claim.operation_id) is None

        with engine.connect() as conn:
            credentials = conn.execute(
                text(
                    "SELECT * FROM airank_provider_credentials "
                    "WHERE tenant_id=:tenant_id ORDER BY credential_version"
                ),
                {"tenant_id": tenant_id},
            ).mappings().all()
            events = conn.execute(
                text(
                    "SELECT * FROM airank_provider_credential_events "
                    "WHERE tenant_id=:tenant_id ORDER BY event_sequence"
                ),
                {"tenant_id": tenant_id},
            ).mappings().all()
            operations = conn.execute(
                text(
                    "SELECT * FROM airank_operation_guards "
                    "WHERE tenant_id=:tenant_id ORDER BY created_at"
                ),
                {"tenant_id": tenant_id},
            ).mappings().all()
            operation_events = conn.execute(
                text(
                    "SELECT * FROM airank_operation_guard_events "
                    "WHERE tenant_id=:tenant_id ORDER BY operation_id,event_sequence"
                ),
                {"tenant_id": tenant_id},
            ).mappings().all()

        assert [(row["status"], row["is_current"]) for row in credentials] == [
            ("rotated", 0),
            ("revoked", 1),
        ]
        assert all(row["secret_ciphertext"] == "" for row in credentials)
        assert all(row["secret_nonce"] == "" for row in credentials)
        serialized_rows = json.dumps(
            [dict(row) for row in [*credentials, *events, *operations, *operation_events]],
            ensure_ascii=False,
            default=str,
        )
        assert first_secret not in serialized_rows
        assert second_secret not in serialized_rows
        assert "integration-credential-upsert-1" not in serialized_rows
        assert "integration-credential-upsert-2" not in serialized_rows
        assert "integration-credential-revoke-2" not in serialized_rows
        assert "integration-credential-unknown-outcome" not in serialized_rows
        assert [row["event_sequence"] for row in events] == [1, 2, 3, 4]
        assert events[0]["previous_event_sha256"] is None
        for previous, current in zip(events, events[1:]):
            assert current["previous_event_sha256"] == previous["event_sha256"]
        assert len(operations) == 4
        assert sorted(row["state"] for row in operations) == [
            "external_started",
            "succeeded",
            "succeeded",
            "succeeded",
        ]
        for operation in operations:
            chain = [
                row for row in operation_events if row["operation_id"] == operation["id"]
            ]
            expected_sequence = [1, 2] if operation["state"] == "external_started" else [1, 2, 3]
            assert [row["event_sequence"] for row in chain] == expected_sequence
            assert chain[0]["previous_event_sha256"] is None
            for previous, current in zip(chain, chain[1:]):
                assert current["previous_event_sha256"] == previous["event_sha256"]

        with pytest.raises(ProviderGatewayError) as revoked_error:
            repository.resolve_settings(
                "qianwen",
                "qianwen:default",
                resolved,
                context=ProviderRequestContext(tenant_id=tenant_id),
            )
        assert revoked_error.value.code == "PROVIDER_CREDENTIAL_REVOKED"
    finally:
        cleanup_tenant(engine, tenant_id)
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT COUNT(*) FROM airank_operation_guards WHERE tenant_id=:tenant_id"),
            {"tenant_id": tenant_id},
        ).scalar_one() == 0
        assert conn.execute(
            text("SELECT COUNT(*) FROM airank_operation_guard_events WHERE tenant_id=:tenant_id"),
            {"tenant_id": tenant_id},
        ).scalar_one() == 0


def test_real_s3_compatible_object_storage_probe() -> None:
    require_real_flag("AIRANK_RUN_REAL_OBJECT_STORAGE")
    result = next(
        item
        for item in CapabilityProbe(ProbeConfig.from_env()).run()
        if item.capability == "object_storage"
    )

    assert result.status == CapabilityStatus.READY
    assert result.metadata["driver"] in {"s3", "minio"}
    assert result.metadata["probe"] == "write-read-delete"


def test_real_mysql_project_competitor_question_write_path() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    repo = MySQLProjectRepository(database_url())

    try:
        project = repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-real-write.example.com",
                brand_name_hint="AIRank Real Write",
                industry_hint="B2B SaaS",
            ),
        )
        competitor = repo.create_competitor(
            tenant_id,
            project.project_id,
            CompetitorCreateRequest(
                name="Real Competitor",
                website_url="https://competitor-real-write.example.com",
                reason="Real MySQL integration write verification.",
                evidence_urls=["https://evidence-real-write.example.com"],
                confidence=0.72,
                source="manual",
            ),
        )
        question = repo.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="Which AI visibility product should a B2B brand choose?",
                question_type="select",
                intent_level="high",
                buyer_stage="decision",
                source_reason="Real MySQL integration write verification.",
                recommended_providers=["chatgpt", "deepseek"],
                source="manual",
            ),
        )

        with engine.connect() as conn:
            project_row = conn.execute(
                text(
                    """
                    SELECT brand_name, website_url
                    FROM airank_projects
                    WHERE tenant_id = :tenant_id AND id = :project_id
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id},
            ).mappings().one()
            assert project_row["brand_name"] == "AIRank Real Write"
            assert project_row["website_url"] == "https://airank-real-write.example.com"

            competitor_meta = conn.execute(
                text(
                    """
                    SELECT metadata_json
                    FROM airank_competitors
                    WHERE tenant_id = :tenant_id AND id = :competitor_id
                    """
                ),
                {"tenant_id": tenant_id, "competitor_id": competitor.competitor_id},
            ).scalar_one()
            assert json.loads(competitor_meta)["evidence_urls"] == ["https://evidence-real-write.example.com"]

            question_meta = conn.execute(
                text(
                    """
                    SELECT metadata_json
                    FROM airank_buyer_questions
                    WHERE tenant_id = :tenant_id AND id = :question_id
                    """
                ),
                {"tenant_id": tenant_id, "question_id": question.question_id},
            ).scalar_one()
            assert json.loads(question_meta)["coverage_status"] == "needs_scan"
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_evidence_object_can_be_read_and_integrity_checked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    evidence_repo = MySQLEvidenceRepository(database_url())
    object_root = tmp_path / "objects"
    storage = FilesystemObjectStorage(object_root)
    payload = b"real mysql durable evidence object"
    stored = storage.put_bytes(payload, key="evidence/integration/object.png", content_type="image/png")
    object_ref_id = f"object_it_{uuid4().hex[:10]}"
    monkeypatch.setenv("AIRANK_OBJECT_STORAGE_DRIVER", "filesystem")
    monkeypatch.setenv("AIRANK_OBJECT_STORAGE_ROOT", str(object_root))

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-real-object.example.com",
                brand_name_hint="AIRank Real Object",
                industry_hint="B2B SaaS",
            ),
        )
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_object_refs (
                      id, tenant_id, project_id, object_type, object_uri,
                      content_type, byte_size, sha256, metadata_json, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, 'provider_answer_screenshot', :object_uri,
                      :content_type, :byte_size, :sha256, :metadata_json, :created_at
                    )
                    """
                ),
                {
                    "id": object_ref_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "object_uri": stored.uri,
                    "content_type": stored.content_type,
                    "byte_size": stored.byte_size,
                    "sha256": stored.sha256,
                    "metadata_json": json.dumps(
                        {"object_key": stored.key, "storage_driver": stored.driver, "immutable": True}
                    ),
                    "created_at": datetime.now(timezone.utc),
                },
            )

        evidence_object = evidence_repo.read_object(tenant_id, object_ref_id)
        assert evidence_object.payload == payload
        assert evidence_object.content_type == "image/png"
        assert evidence_object.sha256 == stored.sha256
        with pytest.raises(StarletteHTTPException) as cross_tenant_error:
            evidence_repo.read_object("tenant_other", object_ref_id)
        assert getattr(cross_tenant_error.value, "status_code", None) == 404
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_question_map_review_and_cohort_gate() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_qgov_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    question_repo = MySQLQuestionGovernanceRepository(database_url())
    scan_repo = MySQLScanRepository(database_url())

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-question-governance.example.com",
                brand_name_hint="AIRank Question Governance",
                industry_hint="B2B SaaS",
            ),
        )
        payload = QuestionMapCompileRequest(
            seed_questions=["企业应该如何选择 GEO 监测服务商？", "企业应该如何选择GEO监测服务商!"],
            include_template_candidates=False,
            persist=True,
            created_by="integration_reviewer",
        )
        compiled = question_repo.compile_map(tenant_id, project.project_id, payload, "integration_reviewer")

        assert compiled.question_count == 1
        assert compiled.duplicate_count == 1
        assert compiled.persisted_count == 1
        question = compiled.questions[0]
        assert question.status == "suggested"
        assert question.cohort_type == "blind"
        assert question.observed_query is False
        assert question.question_id

        with pytest.raises(StarletteHTTPException) as unreviewed_error:
            scan_repo.create_run(
                tenant_id,
                ScanRunCreateRequest(
                    project_id=project.project_id,
                    cohort_type="blind",
                    repetitions=1,
                    provider_scope=["deepseek"],
                    question_scope={"mode": "selected", "question_ids": [question.question_id]},
                ),
            )
        assert unreviewed_error.value.status_code == 404

        review = question_repo.review_question(
            tenant_id,
            project.project_id,
            question.question_id,
            QuestionReviewRequest(
                action="confirmed",
                reviewed_by="integration_reviewer",
                review_note="问题与采购阶段及目标用户匹配。",
            ),
            "integration_reviewer",
        )
        assert review.eligible_for_measurement is True

        run = scan_repo.create_run(
            tenant_id,
            ScanRunCreateRequest(
                project_id=project.project_id,
                cohort_type="blind",
                repetitions=1,
                provider_scope=["deepseek"],
                question_scope={"mode": "selected", "question_ids": [question.question_id]},
            ),
        )
        tasks = scan_repo.list_tasks(tenant_id, run.run_id)
        assert len(tasks) == 1
        assert tasks[0].cohort_type == "blind"

        replay = question_repo.compile_map(tenant_id, project.project_id, payload, "integration_reviewer")
        assert replay.idempotent_replay is True
        assert replay.map_id == compiled.map_id

        with engine.connect() as conn:
            counts = conn.execute(text("""
                SELECT
                  (SELECT COUNT(*) FROM airank_question_maps WHERE tenant_id=:tenant_id) AS map_count,
                  (SELECT COUNT(*) FROM airank_buyer_question_revisions WHERE tenant_id=:tenant_id) AS revision_count,
                  (SELECT COUNT(*) FROM airank_buyer_question_reviews WHERE tenant_id=:tenant_id) AS review_count
            """), {"tenant_id": tenant_id}).mappings().one()
            revision_status = conn.execute(text("""
                SELECT status, reviewed_by, reviewed_at
                FROM airank_buyer_question_revisions
                WHERE tenant_id=:tenant_id AND question_id=:question_id
            """), {"tenant_id": tenant_id, "question_id": question.question_id}).mappings().one()
        assert dict(counts) == {"map_count": 1, "revision_count": 1, "review_count": 1}
        assert revision_status["status"] == "suggested"
        assert revision_status["reviewed_by"] is None
        assert revision_status["reviewed_at"] is None
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_observed_query_batch_is_pii_safe_idempotent_and_compilable() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_qobs_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    question_repo = MySQLQuestionGovernanceRepository(database_url())

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-observed-query.example.com",
                brand_name_hint="AIRank Observed Query",
                industry_hint="B2B SaaS",
            ),
        )
        payload = QuestionObservationImportRequest(
            source_type="site_search",
            source_name="站内搜索导出",
            date_range_start="2026-08-01T00:00:00Z",
            date_range_end="2026-08-07T23:59:59Z",
            records=[
                {
                    "source_record_id": "query-1",
                    "question_text": "制造企业如何选择 GEO 监测平台？",
                    "occurrence_count": 9,
                    "observed_at": "2026-08-06T08:00:00Z",
                    "region": "江苏",
                },
                {
                    "source_record_id": "query-2",
                    "question_text": "请联系 buyer@example.com 获取 GEO 报价",
                    "occurrence_count": 1,
                },
            ],
            rights_attested=True,
            imported_by="integration_researcher",
        )
        imported = question_repo.import_observations(
            tenant_id,
            project.project_id,
            payload,
            "integration_researcher",
        )
        assert imported.batch.status == "ready"
        assert imported.batch.evidence_grade == "user_provided_snapshot"
        assert imported.batch.record_count == 1
        assert imported.batch.occurrence_count == 9
        assert imported.batch.pii_blocked_count == 1
        assert imported.batch.blocked_records[0].reasons == ["email"]
        assert len(imported.records) == 1

        replay = question_repo.import_observations(
            tenant_id,
            project.project_id,
            payload,
            "integration_researcher",
        )
        assert replay.batch.idempotent_replay is True
        assert replay.batch.batch_id == imported.batch.batch_id

        compiled = question_repo.compile_map(
            tenant_id,
            project.project_id,
            QuestionMapCompileRequest(
                observation_batch_ids=[imported.batch.batch_id],
                include_template_candidates=False,
                persist=True,
                created_by="integration_researcher",
            ),
            "integration_researcher",
        )
        assert compiled.question_count == 1
        assert compiled.questions[0].source_kind == "observed_query"
        assert compiled.questions[0].observed_query is True
        assert compiled.questions[0].provenance_records[0]["occurrence_count"] == 9

        with engine.connect() as conn:
            counts = conn.execute(text("""
                SELECT
                  (SELECT COUNT(*) FROM airank_question_observation_batches WHERE tenant_id=:tenant_id) AS batch_count,
                  (SELECT COUNT(*) FROM airank_question_observations WHERE tenant_id=:tenant_id) AS observation_count
            """), {"tenant_id": tenant_id}).mappings().one()
            stored_text = conn.execute(text("""
                SELECT CONCAT(COALESCE(GROUP_CONCAT(question_text), ''),
                              COALESCE(GROUP_CONCAT(normalized_question_text), ''))
                FROM airank_question_observations
                WHERE tenant_id=:tenant_id
            """), {"tenant_id": tenant_id}).scalar_one()
            manifest = conn.execute(text("""
                SELECT CAST(manifest_json AS CHAR)
                FROM airank_question_observation_batches
                WHERE tenant_id=:tenant_id AND id=:batch_id
            """), {"tenant_id": tenant_id, "batch_id": imported.batch.batch_id}).scalar_one()
        assert dict(counts) == {"batch_count": 1, "observation_count": 1}
        assert "buyer@example.com" not in stored_text
        assert "buyer@example.com" not in manifest
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_scan_queue_and_asset_bundle_paths() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    scan_repo = MySQLScanRepository(database_url())
    asset_repo = MySQLAssetBundleRepository(database_url())
    evidence_repo = MySQLEvidenceRepository(database_url())
    snapshot_id = f"snapshot_it_{uuid4().hex[:10]}"
    evidence_snapshot_id = f"evidence_it_{uuid4().hex[:10]}"

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-real-scan.example.com",
                brand_name_hint="AIRank Real Scan",
                industry_hint="B2B SaaS",
            ),
        )
        question_one = project_repo.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="Which AI visibility platform should our company choose?",
                status="confirmed",
                recommended_providers=["chatgpt"],
            ),
        )
        question_two = project_repo.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="How should a company compare AI visibility platforms?",
                question_type="compare",
                status="confirmed",
                recommended_providers=["deepseek"],
            ),
        )

        run = scan_repo.create_run(
            tenant_id,
            ScanRunCreateRequest(
                project_id=project.project_id,
                name="Real MySQL scan queue verification",
                provider_scope=["chatgpt", "deepseek"],
                question_scope={
                    "mode": "selected",
                    "question_ids": [question_one.question_id, question_two.question_id],
                },
            ),
        )
        tasks = scan_repo.list_tasks(tenant_id, run.run_id)

        assert run.status == "queued"
        assert run.metrics["task_count"] == 12
        assert len(tasks) == 12
        assert {task.provider for task in tasks} == {"chatgpt", "deepseek"}

        with engine.begin() as conn:
            jobs = conn.execute(
                text(
                    """
                    SELECT payload_json
                    FROM airank_async_jobs
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND job_type = 'scan.provider'
                    ORDER BY created_at ASC
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id},
            ).scalars().all()
            assert len(jobs) == 12
            first_payload = json.loads(jobs[0])
            assert first_payload["run_id"] == run.run_id
            assert first_payload["scan_task_id"].startswith("scan_task_")
            assert first_payload["question_id"] in {question_one.question_id, question_two.question_id}

            sample_task = tasks[0]
            answer_text = "AIRank 是候选方案之一。"
            answer_sha256 = hashlib.sha256(answer_text.encode("utf-8")).hexdigest()
            raw_response = {"id": "provider_request_it", "answer": answer_text}
            raw_json = json.dumps(raw_response, ensure_ascii=False, sort_keys=True)
            raw_sha256 = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
            conn.execute(
                text(
                    """
                    INSERT INTO airank_answer_snapshots (
                      id, tenant_id, project_id, run_id, task_id, question_id,
                      provider, cohort_type, prompt_version_id, sample_index,
                      session_id, collector_surface, evidence_level, sample_status,
                      answer_text, answer_sha256, raw_response_sha256,
                      brand_mentioned, brand_rank, mention_class,
                      target_entity_mentions_json, competitor_mentions_json,
                      sentiment, confidence, model_name, search_enabled,
                      external_trace_id, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :run_id, :task_id, :question_id,
                      :provider, :cohort_type, :prompt_version_id, :sample_index,
                      :session_id, :collector_surface, :evidence_level, 'valid',
                      :answer_text, :answer_sha256, :raw_response_sha256,
                      1, 2, 'candidate', JSON_ARRAY(), JSON_ARRAY(),
                      'neutral', NULL, 'model-it', 1,
                      'provider_request_it', :created_at
                    )
                    """
                ),
                {
                    "id": snapshot_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "run_id": run.run_id,
                    "task_id": sample_task.task_id,
                    "question_id": sample_task.question_id,
                    "provider": sample_task.provider,
                    "cohort_type": sample_task.cohort_type,
                    "prompt_version_id": sample_task.prompt_version_id,
                    "sample_index": sample_task.sample_index,
                    "session_id": sample_task.session_id,
                    "collector_surface": sample_task.collector_surface,
                    "evidence_level": sample_task.evidence_level,
                    "answer_text": answer_text,
                    "answer_sha256": answer_sha256,
                    "raw_response_sha256": raw_sha256,
                    "created_at": datetime.now(timezone.utc),
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_evidence_snapshots (
                      id, tenant_id, project_id, answer_snapshot_id,
                      raw_response_json, raw_response_sha256,
                      request_metadata_json, captured_at, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :answer_snapshot_id,
                      :raw_response_json, :raw_response_sha256,
                      :request_metadata_json, :captured_at, :captured_at
                    )
                    """
                ),
                {
                    "id": evidence_snapshot_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "answer_snapshot_id": snapshot_id,
                    "raw_response_json": raw_json,
                    "raw_response_sha256": raw_sha256,
                    "request_metadata_json": json.dumps({"collector_surface": sample_task.collector_surface}),
                    "captured_at": datetime.now(timezone.utc),
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_source_citations (
                      id, tenant_id, project_id, snapshot_id, citation_order,
                      title, url, host, source_type, cited_text, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :snapshot_id, 1,
                      '真实引用', 'https://evidence.example.com/source',
                      'evidence.example.com', 'provider_native', '支持回答的引用片段', :created_at
                    )
                    """
                ),
                {
                    "id": f"citation_it_{uuid4().hex[:10]}",
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "snapshot_id": snapshot_id,
                    "created_at": datetime.now(timezone.utc),
                },
            )

            conn.execute(
                text(
                    """
                    INSERT INTO airank_content_assets (
                      id, tenant_id, project_id, asset_type, title, body_md, status
                    )
                    VALUES (
                      'asset_real_fact_page', :tenant_id, :project_id,
                      'fact_page', '企业事实页', '真实 MySQL 资产包验证', 'approved'
                    )
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_publish_packages (
                      id, tenant_id, project_id, asset_id, status
                    )
                    VALUES (
                      'pkg_real_fact_page', :tenant_id, :project_id,
                      'asset_real_fact_page', 'published'
                    )
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_content_gaps (
                      id, tenant_id, project_id, title, severity, suggested_asset_type, status
                    )
                    VALUES (
                      'gap_real_case', :tenant_id, :project_id,
                      '缺少客户案例页', 'high', 'case_page', 'open'
                    )
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id},
            )

        bundle = asset_repo.get_bundle(tenant_id, project.project_id)
        samples, sample_aggregates = evidence_repo.list_samples(
            tenant_id,
            project.project_id,
            run.run_id,
            100,
        )
        detail = evidence_repo.get_sample(tenant_id, snapshot_id)
        assert bundle.assets[0].asset_id == "asset_real_fact_page"
        assert bundle.assets[0].progress == 100
        assert "1 个未绑定样本证据的历史缺口" in bundle.recommendation
        assert "不能直接用于内容建议" in bundle.recommendation
        assert [sample.snapshot_id for sample in samples] == [snapshot_id]
        assert sample_aggregates == {
            "total": 1,
            "valid_count": 1,
            "valid_unmentioned_count": 0,
            "citation_sample_count": 1,
        }
        assert detail.answer_text == "AIRank 是候选方案之一。"
        assert detail.citation_count == 1
        assert detail.citations[0].url == "https://evidence.example.com/source"
        assert detail.raw_response["id"] == "provider_request_it"
        assert detail.screenshot.object_ref_id is None

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_scan_tasks
                    SET status='failed', error_code='provider_not_executed'
                    WHERE tenant_id=:tenant_id AND run_id=:run_id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_scan_tasks
                    SET status='completed', error_code=NULL
                    WHERE tenant_id=:tenant_id AND id=:task_id
                    """
                ),
                {"tenant_id": tenant_id, "task_id": tasks[0].task_id},
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_scan_runs
                    SET status='completed'
                    WHERE tenant_id=:tenant_id AND id=:run_id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            )
        quality = MySQLRetestRepository(database_url()).get_quality_report(
            tenant_id,
            project.project_id,
            run.run_id,
        )
        assert quality["publishable"] is False
        assert quality["metrics"]["total_sample_count"] == 12
        assert quality["metrics"]["valid_sample_count"] == 1
        assert {item["code"] for item in quality["checks"] if item["status"] == "blocked"} >= {
            "valid_sample_rate",
            "raw_response_hashes_present",
            "consumer_conversation_isolation_verified",
            "consumer_screenshots_complete",
            "consumer_source_panels_inspected",
            "consumer_source_panel_evidence_consistent",
        }
        assert quality["surface_evidence"] == [
            {
                "surface": "web",
                "evidence_level": "consumer_web",
                "sample_count": 12,
                "valid_sample_count": 1,
                "evidence_complete_count": 0,
                "screenshot_count": 0,
                "source_panel_captured_count": 0,
                "source_panel_not_present_count": 0,
                "blocker_count": 1,
            }
        ]
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_brand_check_defaults_to_durable_worker_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_worker_dispatch_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    monkeypatch.setenv("AIRANK_DATABASE_URL", database_url())
    monkeypatch.setenv("AIRANK_PROVIDER_MODE", "api")
    monkeypatch.delenv("AIRANK_SCAN_DISPATCH_MODE", raising=False)

    try:
        assert scan_dispatch_mode() == "worker"
        result = run_brand_check(
            tenant_id,
            BrandCheckRequest(
                brand_name="AIRank Worker Dispatch",
                website_url="https://airank-worker-dispatch.example.com",
                industry_hint="B2B SaaS",
                buyer_questions=["企业应该如何选择 GEO 监测服务商？"],
            ),
        )

        assert result.scan_run.status == "queued"
        assert {task.status for task in result.tasks} == {"queued"}
        with engine.connect() as conn:
            counts = conn.execute(
                text(
                    """
                    SELECT
                      (SELECT COUNT(*) FROM airank_async_jobs
                       WHERE tenant_id=:tenant_id AND job_type='scan.provider'
                         AND status='queued') AS queued_jobs,
                      (SELECT COUNT(*) FROM airank_answer_snapshots
                       WHERE tenant_id=:tenant_id) AS snapshot_count
                    """
                ),
                {"tenant_id": tenant_id},
            ).mappings().one()
        assert counts["queued_jobs"] == len(result.tasks)
        assert counts["snapshot_count"] == 0
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_scan_worker_fail_closes_only_expired_task_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_scan_lease_expiry_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    scan_repo = MySQLScanRepository(database_url())
    monkeypatch.setenv("AIRANK_DATABASE_URL", database_url())
    monkeypatch.setenv("AIRANK_PROVIDER_MODE", "api")

    def provider_must_not_run(**_kwargs: Any) -> ProviderScanResult:
        raise AssertionError("expired run lease must not replay Provider calls")

    monkeypatch.setattr("apps.api.main.call_api_provider_for_brand_rank", provider_must_not_run)

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-scan-lease.example.com",
                brand_name_hint="AIRank Scan Lease",
                industry_hint="B2B SaaS",
            ),
        )
        question = project_repo.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="企业如何选择可审计的 GEO 监测服务？",
                status="confirmed",
                recommended_providers=["qianwen"],
            ),
        )
        run = scan_repo.create_run(
            tenant_id,
            ScanRunCreateRequest(
                project_id=project.project_id,
                name="Expired worker lease",
                repetitions=2,
                collector_surfaces=["api"],
                provider_scope=["qianwen"],
                question_scope={"mode": "selected", "question_ids": [question.question_id]},
            ),
        )
        store = MySQLJobLeaseStore(database_url())
        owner_started_at = datetime.now(timezone.utc)
        owner_job = store.claim_next(
            "scan-worker-that-crashes",
            owner_started_at,
            job_types={"scan.provider"},
            tenant_id=tenant_id,
        )
        assert owner_job is not None
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_scan_runs
                    SET status='running', started_at=:started_at, updated_at=:started_at
                    WHERE tenant_id=:tenant_id AND id=:run_id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id, "started_at": owner_started_at},
            )

            conn.execute(
                text(
                    """
                    UPDATE airank_scan_tasks
                    SET status='running', attempt_count=1,
                        started_at=:started_at, updated_at=:started_at
                    WHERE tenant_id=:tenant_id AND id=:task_id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "task_id": owner_job.payload["scan_task_id"],
                    "started_at": owner_started_at,
                },
            )

        recovered = run_next_real_scan_job(
            store,
            worker_id="scan-recovery-worker",
            now=owner_started_at + timedelta(seconds=owner_job.timeout_seconds + 1),
            tenant_id=tenant_id,
        )
        assert recovered is not None
        assert recovered.status == "failed"
        assert recovered.task_count == 2
        assert recovered.failed_count == 1

        with engine.connect() as conn:
            run_row = conn.execute(
                text("SELECT status, error_message FROM airank_scan_runs WHERE tenant_id=:tenant_id AND id=:run_id"),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            ).mappings().one()
            task_rows = conn.execute(
                text(
                    """
                    SELECT status, error_code FROM airank_scan_tasks
                    WHERE tenant_id=:tenant_id AND run_id=:run_id ORDER BY id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            ).mappings().all()
            job_rows = conn.execute(
                text(
                    """
                    SELECT status, error_code FROM airank_async_jobs
                    WHERE tenant_id=:tenant_id
                      AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.run_id'))=:run_id
                    ORDER BY id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            ).mappings().all()
            evidence_rows = conn.execute(
                text(
                    """
                    SELECT a.answer_text, a.answer_sha256, a.raw_response_sha256,
                           a.sample_status, e.raw_response_json, e.raw_response_sha256 AS evidence_sha256
                    FROM airank_answer_snapshots a
                    JOIN airank_evidence_snapshots e
                      ON e.tenant_id=a.tenant_id AND e.answer_snapshot_id=a.id
                    WHERE a.tenant_id=:tenant_id AND a.run_id=:run_id
                    ORDER BY a.id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            ).mappings().all()
            attempt_rows = conn.execute(
                text(
                    """
                    SELECT status, attempt_number, answer_snapshot_id, evidence_snapshot_id,
                           error_code, completed_at
                    FROM airank_scan_task_attempts
                    WHERE tenant_id=:tenant_id AND run_id=:run_id
                    ORDER BY attempt_number, id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            ).mappings().all()

        assert run_row["status"] == "running"
        assert run_row["error_message"] is None
        assert {(row["status"], row["error_code"]) for row in task_rows} == {
            ("failed", "SCAN_TASK_LEASE_EXPIRED"),
            ("queued", None),
        }
        assert sorted(row["status"] for row in job_rows) == ["failed", "queued"]
        assert len(evidence_rows) == 1
        assert len(attempt_rows) == 1
        assert attempt_rows[0]["status"] == "unknown"
        assert attempt_rows[0]["attempt_number"] == 1
        assert attempt_rows[0]["answer_snapshot_id"]
        assert attempt_rows[0]["evidence_snapshot_id"]
        assert attempt_rows[0]["error_code"] == "SCAN_TASK_LEASE_EXPIRED"
        assert attempt_rows[0]["completed_at"] is not None
        for row in evidence_rows:
            raw = json.loads(row["raw_response_json"])
            assert row["answer_text"] == ""
            assert row["answer_sha256"] is None
            assert row["sample_status"] == "failed"
            assert row["raw_response_sha256"] == row["evidence_sha256"]
            assert raw["failure"]["error_code"] == "SCAN_TASK_LEASE_EXPIRED"
            assert raw["failure"]["automatic_replay_suppressed"] is True
            assert raw["capture_metadata"]["provider_response_available"] is False
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_scan_worker_internal_failure_preserves_only_claimed_task_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_scan_internal_failure_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    scan_repo = MySQLScanRepository(database_url())
    monkeypatch.setenv("AIRANK_DATABASE_URL", database_url())
    monkeypatch.setenv("AIRANK_PROVIDER_MODE", "api")

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-worker-failure.example.com",
                brand_name_hint="AIRank Worker Failure",
                industry_hint="B2B SaaS",
            ),
        )
        question = project_repo.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="企业如何验证 GEO 采样可追溯？",
                status="confirmed",
                recommended_providers=["qianwen"],
            ),
        )
        run = scan_repo.create_run(
            tenant_id,
            ScanRunCreateRequest(
                project_id=project.project_id,
                name="Worker internal failure evidence",
                repetitions=2,
                collector_surfaces=["api"],
                provider_scope=["qianwen"],
                question_scope={"mode": "selected", "question_ids": [question.question_id]},
            ),
        )

        def fail_before_provider(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("simulated internal dependency failure")

        monkeypatch.setattr("apps.api.main.get_mysql_project", fail_before_provider)
        with pytest.raises(ScanWorkerError) as caught:
            run_next_real_scan_job(
                MySQLJobLeaseStore(database_url()),
                worker_id="scan-internal-failure-worker",
                tenant_id=tenant_id,
            )
        assert caught.value.code == "SCAN_WORKER_INTERNAL_ERROR"
        assert caught.value.retryable is False

        with engine.connect() as conn:
            counts = conn.execute(
                text(
                    """
                    SELECT
                      (SELECT COUNT(*) FROM airank_scan_tasks
                       WHERE tenant_id=:tenant_id AND run_id=:run_id
                         AND status='failed' AND error_code='SCAN_WORKER_INTERNAL_ERROR') AS failed_tasks,
                      (SELECT COUNT(*) FROM airank_async_jobs
                       WHERE tenant_id=:tenant_id
                         AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.run_id'))=:run_id
                         AND status='failed' AND error_code='SCAN_WORKER_INTERNAL_ERROR') AS failed_jobs,
                      (SELECT COUNT(*) FROM airank_answer_snapshots
                       WHERE tenant_id=:tenant_id AND run_id=:run_id
                         AND sample_status='failed' AND raw_response_sha256 IS NOT NULL) AS failure_snapshots,
                      (SELECT status FROM airank_scan_runs
                       WHERE tenant_id=:tenant_id AND id=:run_id) AS run_status
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            ).mappings().one()
            attempt_statuses = conn.execute(
                text(
                    """
                    SELECT status, error_code, answer_snapshot_id, evidence_snapshot_id
                    FROM airank_scan_task_attempts
                    WHERE tenant_id=:tenant_id AND run_id=:run_id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            ).mappings().all()
        assert counts == {
            "failed_tasks": 1,
            "failed_jobs": 1,
            "failure_snapshots": 1,
            "run_status": "running",
        }
        assert len(attempt_statuses) == 1
        assert attempt_statuses[0]["status"] == "failed"
        assert attempt_statuses[0]["error_code"] == "SCAN_WORKER_INTERNAL_ERROR"
        assert attempt_statuses[0]["answer_snapshot_id"]
        assert attempt_statuses[0]["evidence_snapshot_id"]
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_scan_preserves_failed_task_as_immutable_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_failure_evidence_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    scan_repo = MySQLScanRepository(database_url())
    evidence_repo = MySQLEvidenceRepository(database_url())
    quality_repo = MySQLRetestRepository(database_url())
    calls = 0

    def provider_call(**kwargs: Any) -> ProviderScanResult:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ProviderUnavailable("doubao", "login required for this isolated browser session")
        answer_text = "可选方案包括其他平台，当前回答未提及目标品牌。"
        return ProviderScanResult(
            provider="doubao",
            provider_label="豆包",
            answer_text=answer_text,
            brand_mentioned=False,
            brand_rank=None,
            competitor_mentions=[],
            sentiment="neutral",
            mention_class="not_mentioned",
            target_entity_mentions=[],
            confidence=None,
            external_trace_id="browser:failure-evidence:1",
            native_citations=[],
            raw_metadata={
                "capture_mode": "consumer_browser",
                "collector_surface": "web",
                "evidence_level": "consumer_web",
                "cohort_type": kwargs["cohort_type"],
                "session_id": kwargs["session_id"],
                "prompt_version_id": kwargs["prompt_version_id"],
                "prompt_sha256": "a" * 64,
                "answer_sha256": hashlib.sha256(answer_text.encode("utf-8")).hexdigest(),
                "source_panel_status": "not_present",
                "source_panel_capture_mode": "visible_page_inspected_no_sources",
            },
        )

    monkeypatch.setenv("AIRANK_DATABASE_URL", database_url())
    monkeypatch.setenv("AIRANK_PROVIDER_MODE", "browser")
    monkeypatch.setattr("apps.api.main.call_provider_for_brand_rank", provider_call)

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-failure-evidence.example.com",
                brand_name_hint="AIRank Failure Evidence",
                industry_hint="B2B SaaS",
            ),
        )
        question = project_repo.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="企业应该如何选择 GEO 监测服务商？",
                status="confirmed",
                recommended_providers=["doubao"],
            ),
        )
        run = scan_repo.create_run(
            tenant_id,
            ScanRunCreateRequest(
                project_id=project.project_id,
                name="Immutable failed sample evidence",
                repetitions=2,
                collector_surfaces=["web"],
                provider_scope=["doubao"],
                question_scope={"mode": "selected", "question_ids": [question.question_id]},
            ),
        )

        lease_store = MySQLJobLeaseStore(database_url())
        first_dispatch = run_next_real_scan_job(
            lease_store,
            worker_id="scan-integration-worker",
            tenant_id=tenant_id,
        )
        assert first_dispatch is not None
        assert first_dispatch.run_id == run.run_id
        assert first_dispatch.status == "completed"
        assert first_dispatch.task_count == 2
        assert first_dispatch.completed_count == 1
        assert first_dispatch.failed_count == 0
        with engine.connect() as conn:
            durable_mid_run = conn.execute(
                text(
                    """
                    SELECT
                      (SELECT status FROM airank_scan_runs
                       WHERE tenant_id=:tenant_id AND id=:run_id) AS run_status,
                      (SELECT COUNT(*) FROM airank_answer_snapshots
                       WHERE tenant_id=:tenant_id AND run_id=:run_id) AS snapshot_count,
                      (SELECT COUNT(*) FROM airank_scan_tasks
                       WHERE tenant_id=:tenant_id AND run_id=:run_id AND status='queued') AS queued_count
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            ).mappings().one()
        assert durable_mid_run == {"run_status": "running", "snapshot_count": 1, "queued_count": 1}

        dispatch = run_next_real_scan_job(
            lease_store,
            worker_id="scan-integration-worker",
            tenant_id=tenant_id,
        )
        assert dispatch is not None
        assert dispatch.run_id == run.run_id
        assert dispatch.status == "failed"
        assert dispatch.task_count == 2
        assert dispatch.completed_count == 1
        assert dispatch.failed_count == 1

        with engine.connect() as conn:
            job_rows = conn.execute(
                text(
                    """
                    SELECT id, status FROM airank_async_jobs
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.run_id'))=:run_id
                    ORDER BY id
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id, "run_id": run.run_id},
            ).mappings().all()
        assert sorted(row["status"] for row in job_rows) == ["failed", "succeeded"]
        with engine.connect() as conn:
            attempt_rows = conn.execute(
                text(
                    """
                    SELECT status, attempt_number, answer_snapshot_id, evidence_snapshot_id
                    FROM airank_scan_task_attempts
                    WHERE tenant_id=:tenant_id AND run_id=:run_id
                    ORDER BY status, id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            ).mappings().all()
        assert {row["status"] for row in attempt_rows} == {"blocked", "succeeded"}
        assert {row["attempt_number"] for row in attempt_rows} == {1}
        assert all(row["answer_snapshot_id"] and row["evidence_snapshot_id"] for row in attempt_rows)

        failed_job_id = next(row["id"] for row in job_rows if row["status"] == "failed")
        lease_store.requeue_for_retry(failed_job_id, datetime.now(timezone.utc))
        replay = run_next_real_scan_job(
            lease_store,
            worker_id="scan-integration-worker",
            tenant_id=tenant_id,
        )
        assert replay is not None
        assert replay.status == "failed"
        assert replay.idempotent_replay is True
        assert calls == 2
        with engine.connect() as conn:
            snapshot_count = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM airank_answer_snapshots
                    WHERE tenant_id=:tenant_id AND run_id=:run_id
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            ).scalar_one()
        assert snapshot_count == 2

        samples, summary = evidence_repo.list_samples(tenant_id, project.project_id, run.run_id, 20)
        assert summary == {
            "total": 2,
            "valid_count": 1,
            "valid_unmentioned_count": 1,
            "citation_sample_count": 0,
        }
        assert {sample.sample_status for sample in samples} == {"valid", "blocked"}
        blocked_sample = next(sample for sample in samples if sample.sample_status == "blocked")
        assert blocked_sample.answer_sha256 is None
        detail = evidence_repo.get_sample(tenant_id, blocked_sample.snapshot_id)
        assert detail.answer_text == ""
        assert detail.raw_response_sha256
        assert detail.raw_response["sample_status"] == "blocked"
        assert detail.raw_response["failure"]["error_code"] == "SCAN_PROVIDER_BLOCKED"
        assert detail.request_metadata["failure"]["blocked"] is True
        assert len(detail.attempts) == 1
        assert detail.attempts[0].status == "blocked"
        assert detail.attempts[0].attempt_number == 1
        assert detail.attempts[0].answer_snapshot_id == blocked_sample.snapshot_id
        assert detail.attempts[0].evidence_snapshot_id == detail.evidence_snapshot_id

        quality = quality_repo.get_quality_report(tenant_id, project.project_id, run.run_id)
        raw_hash_check = next(check for check in quality["checks"] if check["code"] == "raw_response_hashes_present")
        assert raw_hash_check["status"] == "pass"
        assert quality["metrics"]["failed_sample_count"] == 0
        assert quality["metrics"]["blocked_sample_count"] == 1
        assert quality["metrics"]["not_mentioned_count"] == 1
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_failed_scan_remains_quality_auditable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_failed_quality_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    scan_repo = MySQLScanRepository(database_url())

    def failed_provider(**_kwargs: Any) -> ProviderScanResult:
        raise ProviderCallError(
            "qianwen",
            "provider returned an empty answer",
            error_code="PROVIDER_EMPTY_RESPONSE",
            public_metadata={
                "capture_mode": "provider_api",
                "collector_surface": "api",
                "evidence_level": "provider_api_search_unverified",
                "model_name": "qwen-integration-empty",
                "endpoint_host": "dashscope.aliyuncs.com",
                "configuration_fingerprint": "f" * 64,
                "prompt_sha256": "a" * 64,
                "route_id": "qianwen:default",
                "provider_request_id": "request-empty-integration-1",
                "duration_ms": 4321,
                "attempt_count": 2,
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 4096,
                    "total_tokens": 4108,
                    "precision": "exact",
                    "source": "provider_response",
                },
                "request_contract": {
                    "max_tokens": 4096,
                    "max_tokens_field": "max_tokens",
                    "temperature": 0.2,
                    "reasoning_effort": None,
                },
                "provider_raw_response": {
                    "id": "request-empty-integration-1",
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {"content": "", "reasoning_content": "still reasoning"},
                        }
                    ],
                    "usage": {"total_tokens": 4108},
                },
            },
        )

    monkeypatch.setenv("AIRANK_DATABASE_URL", database_url())
    monkeypatch.setenv("AIRANK_PROVIDER_MODE", "api")
    monkeypatch.setenv("QIANWEN_API_KEY", "integration-test-secret-never-persisted")
    monkeypatch.setenv(
        "QIANWEN_API_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    )
    monkeypatch.setenv("QIANWEN_MODEL", "qwen-integration-empty")
    monkeypatch.setenv("AIRANK_OBJECT_STORAGE_DRIVER", "local")
    monkeypatch.setenv("AIRANK_OBJECT_STORAGE_ROOT", str(tmp_path / "objects"))
    monkeypatch.setattr("apps.api.main.call_api_provider_for_brand_rank", failed_provider)

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-failed-quality.example.com",
                brand_name_hint="AIRank Failed Quality",
                industry_hint="B2B SaaS",
            ),
        )
        question = project_repo.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="企业应该如何选择可审计的 GEO 监测服务商？",
                status="confirmed",
                recommended_providers=["qianwen"],
            ),
        )
        run = scan_repo.create_run(
            tenant_id,
            ScanRunCreateRequest(
                project_id=project.project_id,
                name="Failed run quality audit",
                repetitions=1,
                collector_surfaces=["api"],
                provider_scope=["qianwen"],
                question_scope={"mode": "selected", "question_ids": [question.question_id]},
            ),
        )

        dispatch = run_next_real_scan_job(
            MySQLJobLeaseStore(database_url()),
            worker_id="failed-quality-worker",
            tenant_id=tenant_id,
        )
        assert dispatch is not None
        assert dispatch.status == "failed"
        quality = MySQLRetestRepository(database_url()).get_quality_report(
            tenant_id,
            project.project_id,
            run.run_id,
        )
        run_status_check = next(
            check for check in quality["checks"] if check["code"] == "run_status_publishable"
        )
        assert quality["publishable"] is False
        assert quality["metrics"]["failed_sample_count"] == 1
        assert quality["metrics"]["blocked_sample_count"] == 0
        assert run_status_check["status"] == "blocked"
        assert run_status_check["actual"] == "failed"
        with engine.connect() as conn:
            audit = conn.execute(
                text(
                    """
                    SELECT provider_request_id, attempt_count, duration_ms, metadata_json
                    FROM airank_provider_request_audits
                    WHERE tenant_id=:tenant_id AND run_id=:run_id AND outcome='failed'
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run.run_id},
            ).mappings().one()
            usage = conn.execute(
                text(
                    """
                    SELECT total_tokens, precision_status
                    FROM airank_provider_usage_events
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id},
            ).mappings().one()
            evidence = conn.execute(
                text(
                    """
                    SELECT raw_response_json
                    FROM airank_evidence_snapshots
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id},
            ).scalar_one()
        assert audit["provider_request_id"] == "request-empty-integration-1"
        assert audit["attempt_count"] == 2
        assert audit["duration_ms"] == 4321
        assert "request_contract" in str(audit["metadata_json"])
        assert usage == {"total_tokens": 4108, "precision_status": "exact"}
        assert "request-empty-integration-1" in str(evidence)
        assert "still reasoning" in str(evidence)
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_report_repository_and_download_receipt() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    report_repo = MySQLReportRepository(database_url())
    packet_id = f"report_packet_{uuid4().hex[:20]}"
    packet_object_id = f"object_{uuid4().hex[:24]}"
    packet_sha256 = hashlib.sha256(packet_id.encode("utf-8")).hexdigest()

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-real-report.example.com",
                brand_name_hint="AIRank Real Report",
                industry_hint="B2B SaaS",
            ),
        )
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_reports (
                      id, tenant_id, project_id, report_type, title, status,
                      metrics_json, generated_at
                    )
                    VALUES (
                      'report_real_exec', :tenant_id, :project_id, 'executive',
                      'AIRank 真实诊断报告', 'generated',
                      JSON_OBJECT(
                        'summary', '真实 MySQL 报告列表验证',
                        'report_status', 'generated',
                        'baseline_quality', JSON_OBJECT('contract_version', 'airank.measurement-quality.v4', 'publishable', TRUE),
                        'compare_quality', JSON_OBJECT('contract_version', 'airank.measurement-quality.v4', 'publishable', TRUE)
                      ),
                      CURRENT_TIMESTAMP(3)
                    )
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_object_refs (
                      id, tenant_id, project_id, object_type, object_uri,
                      content_type, byte_size, sha256, metadata_json
                    ) VALUES (
                      :id, :tenant_id, :project_id, 'report_evidence_packet',
                      :object_uri, 'application/json', 2, :sha256,
                      JSON_OBJECT('immutable', TRUE, 'object_key', 'integration/report.json', 'storage_driver', 'filesystem')
                    )
                    """
                ),
                {
                    "id": packet_object_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "object_uri": "file:///tmp/airank-integration-report.json",
                    "sha256": packet_sha256,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_report_evidence_packets (
                      id, tenant_id, project_id, report_id, schema_version,
                      report_sha256, source_record_sha256, object_ref_id,
                      content_sha256, byte_size, summary_json, idempotency_key,
                      created_by, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, 'report_real_exec',
                      'airank.report-evidence-packet.v1', :report_sha256,
                      :source_record_sha256, :object_ref_id, :content_sha256,
                      2, JSON_OBJECT('samples', 1, 'citations', 0, 'evidence_objects', 0, 'known_limitations', 0),
                      :idempotency_key, 'integration_reporter', CURRENT_TIMESTAMP(3)
                    )
                    """
                ),
                {
                    "id": packet_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "report_sha256": "8" * 64,
                    "source_record_sha256": "9" * 64,
                    "object_ref_id": packet_object_id,
                    "content_sha256": packet_sha256,
                    "idempotency_key": f"integration-{packet_id}",
                },
            )

        report_list = report_repo.list_reports(tenant_id, project.project_id)
        assert [report.report_id for report in report_list.reports] == ["report_real_exec"]
        assert report_list.reports[0].desc == "真实 MySQL 报告列表验证"

        receipt = report_repo.record_download_receipt(
            tenant_id,
            "report_real_exec",
            DownloadReceiptRequest(packet_id=packet_id, content_sha256=packet_sha256),
            "integration_reporter",
            "trc_real_report",
        )
        assert receipt.status == "recorded"

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_reports (
                      id, tenant_id, project_id, report_type, title, status,
                      metrics_json, generated_at
                    ) VALUES (
                      'report_real_blocked', :tenant_id, :project_id, 'retest',
                      'AIRank 质量阻断报告', 'quality_blocked',
                      JSON_OBJECT('report_status', 'quality_blocked'),
                      CURRENT_TIMESTAMP(3)
                    )
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project.project_id},
            )
        with pytest.raises(StarletteHTTPException) as blocked_download:
            report_repo.record_download_receipt(
                tenant_id,
                "report_real_blocked",
                DownloadReceiptRequest(packet_id=packet_id, content_sha256=packet_sha256),
                "integration_reporter",
                "trc_real_blocked",
            )
        assert blocked_download.value.status_code == 409
        assert blocked_download.value.detail["code"] == "REPORT_QUALITY_BLOCKED"

        with engine.connect() as conn:
            audit = conn.execute(
                text(
                    """
                    SELECT event_type, entity_type, entity_id, trace_id, payload_json
                    FROM airank_audit_events
                    WHERE tenant_id = :tenant_id
                    """
                ),
                {"tenant_id": tenant_id},
            ).mappings().one()
        assert audit["event_type"] == "report.download_receipt"
        assert audit["entity_type"] == "report"
        assert audit["entity_id"] == "report_real_exec"
        assert audit["trace_id"] == "trc_real_report"
        assert json.loads(audit["payload_json"])["report_id"] == "report_real_exec"
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_report_evidence_packet_round_trip(tmp_path: Path) -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_report_packet_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    scan_repo = MySQLScanRepository(database_url())
    quality_repo = MySQLRetestRepository(database_url())
    storage = FilesystemObjectStorage(tmp_path / "report-packets")
    packet_repo = MySQLReportEvidencePacketRepository(
        database_url(),
        object_storage=storage,
    )

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-report-packet.example.com",
                brand_name_hint="AIRank Report Packet",
                industry_hint="B2B SaaS",
            ),
        )
        question = project_repo.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="企业应该如何选择有证据链的 GEO 监测服务？",
                status="confirmed",
                recommended_providers=["qianwen"],
            ),
        )
        runs = [
            scan_repo.create_run(
                tenant_id,
                ScanRunCreateRequest(
                    project_id=project.project_id,
                    name=name,
                    repetitions=3,
                    collector_surfaces=["api"],
                    provider_scope=["qianwen"],
                    question_scope={"mode": "selected", "question_ids": [question.question_id]},
                ),
            )
            for name in ("Report packet T0", "Report packet T+7")
        ]
        captured_at = datetime.now(timezone.utc)
        with engine.begin() as conn:
            for run_index, run in enumerate(runs):
                tasks = scan_repo.list_tasks(tenant_id, run.run_id)
                assert len(tasks) == 3
                for task in tasks:
                    snapshot_id = f"snapshot_packet_{uuid4().hex[:16]}"
                    evidence_id = f"evidence_packet_{uuid4().hex[:16]}"
                    audit_id = f"provider_audit_{uuid4().hex[:16]}"
                    answer_text = (
                        "当前有效回答未提及目标品牌。"
                        if run_index == 0
                        else "目标品牌是可进一步核验的候选方案。"
                    )
                    answer_sha256 = hashlib.sha256(answer_text.encode("utf-8")).hexdigest()
                    raw_json = json.dumps(
                        {"request_id": f"request-{task.task_id}", "answer": answer_text},
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    raw_sha256 = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
                    provider_request_id = f"request-{task.task_id}"
                    conn.execute(
                        text(
                            """
                            INSERT INTO airank_answer_snapshots (
                              id, tenant_id, project_id, run_id, task_id, question_id,
                              provider, cohort_type, prompt_version_id, sample_index,
                              session_id, collector_surface, evidence_level, sample_status,
                              answer_text, answer_sha256, raw_response_sha256,
                              brand_mentioned, brand_rank, mention_class,
                              competitor_mentions_json, model_name, model_version,
                              search_enabled, locale, region, external_trace_id, created_at
                            ) VALUES (
                              :id, :tenant_id, :project_id, :run_id, :task_id, :question_id,
                              :provider, :cohort_type, :prompt_version_id, :sample_index,
                              :session_id, :collector_surface, :evidence_level, 'valid',
                              :answer_text, :answer_sha256, :raw_response_sha256,
                              :brand_mentioned, :brand_rank, :mention_class,
                              JSON_ARRAY(), 'qwen3.6-plus', 'qwen3.6-plus',
                              0, 'zh-CN', 'CN', :external_trace_id, :created_at
                            )
                            """
                        ),
                        {
                            "id": snapshot_id,
                            "tenant_id": tenant_id,
                            "project_id": project.project_id,
                            "run_id": run.run_id,
                            "task_id": task.task_id,
                            "question_id": task.question_id,
                            "provider": task.provider,
                            "cohort_type": task.cohort_type,
                            "prompt_version_id": task.prompt_version_id,
                            "sample_index": task.sample_index,
                            "session_id": task.session_id,
                            "collector_surface": task.collector_surface,
                            "evidence_level": task.evidence_level,
                            "answer_text": answer_text,
                            "answer_sha256": answer_sha256,
                            "raw_response_sha256": raw_sha256,
                            "brand_mentioned": run_index == 1,
                            "brand_rank": 2 if run_index == 1 else None,
                            "mention_class": "candidate" if run_index == 1 else "not_mentioned",
                            "external_trace_id": provider_request_id,
                            "created_at": captured_at,
                        },
                    )
                    source_hosts = {
                        1: "news.example.com",
                        2: "docs.example.com",
                        3: None,
                    }
                    source_host = source_hosts[task.sample_index]
                    conn.execute(
                        text(
                            """
                            INSERT INTO airank_source_citations (
                              id, tenant_id, project_id, snapshot_id,
                              citation_order, title, url, host, source_type,
                              cited_text, metadata_json, created_at
                            ) VALUES (
                              :id, :tenant_id, :project_id, :snapshot_id,
                              1, :title, :url, :host, 'provider_native',
                              :cited_text, JSON_OBJECT('integration_test', TRUE),
                              :created_at
                            )
                            """
                        ),
                        {
                            "id": f"citation_packet_{uuid4().hex[:16]}",
                            "tenant_id": tenant_id,
                            "project_id": project.project_id,
                            "snapshot_id": snapshot_id,
                            "title": "Packet source governance fixture",
                            "url": (
                                f"https://{source_host}/evidence"
                                if source_host
                                else "https://example.invalid/unresolved-host"
                            ),
                            "host": source_host,
                            "cited_text": "报告来源治理集成测试引用。",
                            "created_at": captured_at,
                        },
                    )
                    conn.execute(
                        text(
                            """
                            INSERT INTO airank_evidence_snapshots (
                              id, tenant_id, project_id, answer_snapshot_id,
                              raw_response_json, raw_response_sha256,
                              request_metadata_json, captured_at, created_at
                            ) VALUES (
                              :id, :tenant_id, :project_id, :snapshot_id,
                              :raw_json, :raw_sha256, :request_metadata_json,
                              :captured_at, :captured_at
                            )
                            """
                        ),
                        {
                            "id": evidence_id,
                            "tenant_id": tenant_id,
                            "project_id": project.project_id,
                            "snapshot_id": snapshot_id,
                            "raw_json": raw_json,
                            "raw_sha256": raw_sha256,
                            "request_metadata_json": json.dumps(
                                {
                                    "provider_request": {
                                        "provider": task.provider,
                                        "collector_surface": "api",
                                    }
                                }
                            ),
                            "captured_at": captured_at,
                        },
                    )
                    conn.execute(
                        text(
                            """
                            INSERT INTO airank_provider_request_audits (
                              id, tenant_id, project_id, run_id, task_id,
                              answer_snapshot_id, provider_key, model_name,
                              endpoint_host, configuration_fingerprint,
                              provider_request_id, prompt_sha256, outcome,
                              evidence_grade, attempt_count, duration_ms,
                              requested_at, completed_at, metadata_json
                            ) VALUES (
                              :id, :tenant_id, :project_id, :run_id, :task_id,
                              :snapshot_id, 'qianwen', 'qwen3.6-plus',
                              'dashscope.aliyuncs.com', :configuration_fingerprint,
                              :provider_request_id, :prompt_sha256, 'succeeded',
                              'provider_api_search_not_used', 1, 100,
                              :captured_at, :captured_at, JSON_OBJECT('integration_test', TRUE)
                            )
                            """
                        ),
                        {
                            "id": audit_id,
                            "tenant_id": tenant_id,
                            "project_id": project.project_id,
                            "run_id": run.run_id,
                            "task_id": task.task_id,
                            "snapshot_id": snapshot_id,
                            "configuration_fingerprint": "a" * 64,
                            "provider_request_id": provider_request_id,
                            "prompt_sha256": "b" * 64,
                            "captured_at": captured_at,
                        },
                    )
                    conn.execute(
                        text(
                            """
                            UPDATE airank_scan_tasks
                            SET status='completed', attempt_count=1,
                                started_at=:captured_at, finished_at=:captured_at,
                                updated_at=:captured_at
                            WHERE tenant_id=:tenant_id AND id=:task_id
                            """
                        ),
                        {"captured_at": captured_at, "tenant_id": tenant_id, "task_id": task.task_id},
                    )
                conn.execute(
                    text(
                        """
                        UPDATE airank_scan_runs
                        SET status='completed', started_at=:captured_at,
                            finished_at=:captured_at, updated_at=:captured_at
                        WHERE tenant_id=:tenant_id AND id=:run_id
                        """
                    ),
                    {"captured_at": captured_at, "tenant_id": tenant_id, "run_id": run.run_id},
                )

            for normalized_host, valid_until, authority_level, usage_policy in (
                (
                    "news.example.com",
                    captured_at + timedelta(days=30),
                    "high",
                    "primary_evidence",
                ),
                (
                    "docs.example.com",
                    captured_at - timedelta(days=1),
                    "medium",
                    "context_only",
                ),
            ):
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_source_classification_revisions (
                          id, tenant_id, project_id, normalized_host,
                          revision_number, source_category_l1, source_type,
                          ecosystem, classification_status, classification_method,
                          classification_confidence, authority_level, usage_policy,
                          risk_level, evidence_note, evidence_url,
                          source_dataset_name, source_dataset_version, valid_until,
                          reviewed_by, reviewed_at, supersedes_revision_id,
                          idempotency_key, request_sha256, created_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :normalized_host,
                          1, 'news_media', 'integration_source',
                          'AIRank integration fixture', 'reviewed', 'human_review',
                          'high', :authority_level, :usage_policy,
                          'low', :evidence_note, :evidence_url,
                          NULL, NULL, :valid_until,
                          'integration_reviewer', :reviewed_at, NULL,
                          :idempotency_key, :request_sha256, :created_at
                        )
                        """
                    ),
                    {
                        "id": f"source_class_{uuid4().hex}",
                        "tenant_id": tenant_id,
                        "project_id": project.project_id,
                        "normalized_host": normalized_host,
                        "authority_level": authority_level,
                        "usage_policy": usage_policy,
                        "evidence_note": "Integration reviewer verified the fixture source identity.",
                        "evidence_url": f"https://{normalized_host}/about",
                        "valid_until": valid_until,
                        "reviewed_at": captured_at - timedelta(days=2),
                        "idempotency_key": f"source-governance-{normalized_host}-{uuid4().hex[:8]}",
                        "request_sha256": "d" * 64,
                        "created_at": captured_at - timedelta(days=2),
                    },
                )

        baseline_quality = quality_repo.get_quality_report(
            tenant_id, project.project_id, runs[0].run_id
        )
        compare_quality = quality_repo.get_quality_report(
            tenant_id, project.project_id, runs[1].run_id
        )
        assert baseline_quality["publishable"] is True
        assert compare_quality["publishable"] is True
        assert baseline_quality["metrics"]["not_mentioned_count"] == 3
        gap_repository = MySQLEvidenceGapRepository(database_url())
        gap_payload = DeriveEvidenceGapsRequest(
            run_id=runs[0].run_id,
            requested_by="integration_evidence_gap_reviewer",
        )
        gap_derivation = gap_repository.derive(
            tenant_id,
            project.project_id,
            gap_payload,
            idempotency_key=f"evidence-gap-{runs[0].run_id}",
            actor="integration_evidence_gap_reviewer",
            trace_id="trc_evidence_gap_mysql",
        )
        gap_replay = gap_repository.derive(
            tenant_id,
            project.project_id,
            gap_payload,
            idempotency_key=f"evidence-gap-replay-{runs[0].run_id}",
            actor="integration_evidence_gap_reviewer",
            trace_id="trc_evidence_gap_mysql_replay",
        )
        mentioned_derivation = gap_repository.derive(
            tenant_id,
            project.project_id,
            DeriveEvidenceGapsRequest(
                run_id=runs[1].run_id,
                requested_by="integration_evidence_gap_reviewer",
            ),
            idempotency_key=f"evidence-gap-{runs[1].run_id}",
            actor="integration_evidence_gap_reviewer",
            trace_id="trc_evidence_gap_mysql_mentioned",
        )
        assert gap_derivation.gap_count == 1
        assert gap_derivation.skipped_group_count == 0
        assert gap_derivation.idempotent_replay is False
        assert gap_replay.idempotent_replay is True
        assert gap_replay.derivation_run_id == gap_derivation.derivation_run_id
        assert mentioned_derivation.gap_count == 0
        assert mentioned_derivation.skipped_group_count == 1
        gap = gap_derivation.gaps[0]
        assert gap.normal_unmentioned_count == 3
        assert len(gap.answer_snapshot_ids) == 3
        assert len(gap.evidence_snapshot_ids) == 3
        assert len(gap.evidence_sha256) == 64
        with engine.connect() as conn:
            assert conn.execute(
                text(
                    "SELECT COUNT(*) FROM airank_answer_snapshots "
                    "WHERE tenant_id=:tenant_id AND id IN :snapshot_ids"
                ).bindparams(bindparam("snapshot_ids", expanding=True)),
                {"tenant_id": tenant_id, "snapshot_ids": gap.answer_snapshot_ids},
            ).scalar_one() == 3
            assert conn.execute(
                text(
                    "SELECT COUNT(*) FROM airank_evidence_snapshots "
                    "WHERE tenant_id=:tenant_id AND id IN :evidence_ids"
                ).bindparams(bindparam("evidence_ids", expanding=True)),
                {"tenant_id": tenant_id, "evidence_ids": gap.evidence_snapshot_ids},
            ).scalar_one() == 3
        fact_task_repository = MySQLFactAcquisitionRepository(database_url())
        fact_task = fact_task_repository.create_task(
            tenant_id,
            project.project_id,
            gap.gap_id,
            FactAcquisitionTaskCreateRequest(
                requested_by="integration_knowledge_operator",
            ),
            idempotency_key=f"fact-task-{gap.gap_id}",
            actor="integration_knowledge_operator",
            trace_id="trc_fact_task_mysql",
        )
        fact_task_replay = fact_task_repository.create_task(
            tenant_id,
            project.project_id,
            gap.gap_id,
            FactAcquisitionTaskCreateRequest(
                requested_by="integration_knowledge_operator",
            ),
            idempotency_key=f"fact-task-replay-{gap.gap_id}",
            actor="integration_knowledge_operator",
            trace_id="trc_fact_task_mysql_replay",
        )
        assert fact_task.status == "open"
        assert fact_task.resolution_state == "needs_fact_proposal"
        assert fact_task.generation_allowed is False
        assert fact_task.event_count == 1
        assert fact_task_replay.task_id == fact_task.task_id
        assert fact_task_replay.idempotent_replay is True
        gap_bundle = MySQLAssetBundleRepository(database_url()).get_bundle(
            tenant_id, project.project_id
        )
        assert [item.asset_id for item in gap_bundle.assets] == [f"gap_{gap.gap_id}"]
        assert gap_bundle.assets[0].status == "待补事实"
        assert "3 条不可变有效样本" in gap_bundle.assets[0].desc
        knowledge_repo = MySQLKnowledgeRepository(database_url())
        source = knowledge_repo.create_source(
            tenant_id,
            project.project_id,
            KnowledgeSourceCreateRequest(
                idempotency_key=f"fact-task-source-{uuid4().hex}",
                source_type="official_product_documentation",
                title="AIRank fact acquisition integration evidence",
                content_text="AIRank 保存不可变回答、来源和请求元数据，并允许指标下钻到样本。",
                source_uri="https://airank-report-packet.example.com/evidence/fact-acquisition",
                authority_level="official",
                risk_level="low",
            ),
        )
        proposed_fact = knowledge_repo.propose_fact(
            tenant_id,
            project.project_id,
            FactProposalRequest(
                title="样本级证据追溯能力",
                fact_type="brand_claim",
                subject_type="brand",
                subject_ref_id="AIRank Report Packet",
                fact_text="AIRank 保存不可变回答、来源和请求元数据，并允许指标下钻到样本。",
                source_ids=[source.source_id],
                risk_level="low",
                disclosure="public",
                created_by="integration_knowledge_operator",
            ),
        )
        approved_fact = knowledge_repo.review_revision(
            tenant_id,
            project.project_id,
            proposed_fact.revision_id,
            FactRevisionReviewRequest(
                action="approved",
                reviewed_by="integration_fact_reviewer",
                review_note="Official source boundary verified for integration acceptance.",
            ),
        )
        assert approved_fact.eligible_for_generation is True
        resolved_task = fact_task_repository.bind_evidence(
            tenant_id,
            project.project_id,
            fact_task.task_id,
            FactAcquisitionEvidenceBindRequest(
                fact_revision_ids=[approved_fact.revision_id],
                expected_version=1,
                requested_by="integration_knowledge_operator",
            ),
            idempotency_key=f"fact-task-bind-{gap.gap_id}",
            actor="integration_knowledge_operator",
            trace_id="trc_fact_task_bind_mysql",
        )
        assert resolved_task.status == "resolved"
        assert resolved_task.resolution_state == "ready_for_intervention"
        assert resolved_task.generation_allowed is True
        assert resolved_task.event_count == 2
        assert len(resolved_task.last_event_sha256) == 64
        with engine.connect() as conn:
            gap_resolution = conn.execute(
                text(
                    "SELECT status, fact_atom_ids FROM airank_content_gaps "
                    "WHERE tenant_id=:tenant_id AND id=:gap_id"
                ),
                {"tenant_id": tenant_id, "gap_id": gap.gap_id},
            ).mappings().one()
            assert gap_resolution["status"] == "ready_for_intervention"
            assert approved_fact.fact_id in json.loads(gap_resolution["fact_atom_ids"])
            task_events = conn.execute(
                text(
                    "SELECT task_version, previous_event_sha256, event_sha256 "
                    "FROM airank_fact_acquisition_task_events "
                    "WHERE tenant_id=:tenant_id AND task_id=:task_id "
                    "ORDER BY task_version"
                ),
                {"tenant_id": tenant_id, "task_id": fact_task.task_id},
            ).mappings().all()
            assert [int(event["task_version"]) for event in task_events] == [1, 2]
            assert task_events[0]["previous_event_sha256"] is None
            assert task_events[1]["previous_event_sha256"] == task_events[0]["event_sha256"]
        resolved_gap_bundle = MySQLAssetBundleRepository(database_url()).get_bundle(
            tenant_id, project.project_id
        )
        assert resolved_gap_bundle.assets[0].status == "待生成"
        report_id = f"report_packet_it_{uuid4().hex[:12]}"
        retest_run_id = f"retest_packet_it_{uuid4().hex[:12]}"
        window_id = f"window_packet_it_{uuid4().hex[:12]}"
        asset_id = f"asset_packet_it_{uuid4().hex[:12]}"
        package_id = f"package_packet_it_{uuid4().hex[:12]}"
        with engine.begin() as conn:
            baseline = MySQLRetestRepository._load_run(
                conn, tenant_id, project.project_id, runs[0].run_id
            )
            compare = MySQLRetestRepository._load_run(
                conn, tenant_id, project.project_id, runs[1].run_id
            )
            result = _comparison_data(
                window={
                    "id": window_id,
                    "window_label": "T+7",
                    "package_id": package_id,
                },
                baseline_run_id=runs[0].run_id,
                compare_run_id=runs[1].run_id,
                baseline_quality=build_measurement_quality_report(
                    run_id=runs[0].run_id,
                    samples=baseline.samples,
                    signatures=baseline.signature,
                    evidence_manifests=baseline.evidence_manifests,
                    run_status=baseline.run_status,
                ),
                compare_quality=build_measurement_quality_report(
                    run_id=runs[1].run_id,
                    samples=compare.samples,
                    signatures=compare.signature,
                    evidence_manifests=compare.evidence_manifests,
                    run_status=compare.run_status,
                ),
                baseline_signature=baseline.signature,
                compare_signature=compare.signature,
                completed_at=captured_at,
            ).model_copy(
                update={"retest_run_id": retest_run_id, "report_id": report_id}
            )
            result_json = result.model_dump(mode="json")
            evidence_index = {
                "package_id": package_id,
                "window_id": window_id,
                "baseline_run_id": runs[0].run_id,
                "compare_run_id": runs[1].run_id,
                "evidence_refs": result.evidence_refs,
            }
            conn.execute(
                text(
                    """
                    INSERT INTO airank_content_assets (
                      id, tenant_id, project_id, asset_type, title, body_md, status
                    ) VALUES (
                      :id, :tenant_id, :project_id, 'fact_page',
                      '证据包复测占位资产', '仅用于真实 MySQL 门禁。', 'approved'
                    )
                    """
                ),
                {"id": asset_id, "tenant_id": tenant_id, "project_id": project.project_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_publish_packages (
                      id, tenant_id, project_id, asset_id, channel, status
                    ) VALUES (
                      :id, :tenant_id, :project_id, :asset_id, 'export', 'published'
                    )
                    """
                ),
                {
                    "id": package_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "asset_id": asset_id,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_retest_observation_windows (
                      id, tenant_id, project_id, package_id, baseline_run_id,
                      window_label, due_at, status, compare_run_id, result_json,
                      completed_at, created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :package_id, :baseline_run_id,
                      'T+7', :completed_at, 'completed', :compare_run_id, :result_json,
                      :completed_at, :completed_at, :completed_at
                    )
                    """
                ),
                {
                    "id": window_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "package_id": package_id,
                    "baseline_run_id": runs[0].run_id,
                    "compare_run_id": runs[1].run_id,
                    "result_json": json.dumps(result_json, ensure_ascii=False),
                    "completed_at": captured_at,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_retest_runs (
                      id, tenant_id, project_id, package_id, observation_window_id,
                      baseline_run_id, compare_run_id, comparison_contract_version,
                      created_by, status, summary_json, started_at, finished_at,
                      created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :package_id, :window_id,
                      :baseline_run_id, :compare_run_id, 'airank.retest-comparison.v1',
                      'integration_reporter', 'completed', :summary_json,
                      :completed_at, :completed_at, :completed_at, :completed_at
                    )
                    """
                ),
                {
                    "id": retest_run_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "package_id": package_id,
                    "window_id": window_id,
                    "baseline_run_id": runs[0].run_id,
                    "compare_run_id": runs[1].run_id,
                    "summary_json": json.dumps(result_json, ensure_ascii=False),
                    "completed_at": captured_at,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_reports (
                      id, tenant_id, project_id, report_type, title, status,
                      run_id, retest_run_id, metrics_json, report_sha256, evidence_index_json,
                      generated_by, generated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, 'retest',
                      'T+7 GEO 复测证据包集成报告', :status, :run_id, :retest_run_id,
                      :metrics_json, :report_sha256, :evidence_index_json,
                      'integration_reporter', :generated_at
                    )
                    """
                ),
                {
                    "id": report_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "run_id": runs[1].run_id,
                    "retest_run_id": retest_run_id,
                    "status": result.report_status,
                    "metrics_json": json.dumps(result_json, ensure_ascii=False),
                    "report_sha256": result.report_sha256,
                    "evidence_index_json": json.dumps(evidence_index),
                    "generated_at": captured_at,
                },
            )

        packet = packet_repo.create_packet(
            tenant_id,
            report_id,
            f"packet-{report_id}",
            "integration_reporter",
            "trc_report_packet_it",
        )
        assert packet.summary.sample_count == 6
        assert packet.idempotent_replay is False
        with engine.connect() as conn:
            object_metadata = conn.execute(
                text("SELECT metadata_json FROM airank_object_refs WHERE id=:id"),
                {"id": packet.object_ref_id},
            ).scalar_one()
        if isinstance(object_metadata, str):
            object_metadata = json.loads(object_metadata)
        manifest_bytes = storage.get_bytes(object_metadata["object_key"])
        assert hashlib.sha256(manifest_bytes).hexdigest() == packet.content_sha256
        with ZipFile(io.BytesIO(manifest_bytes)) as archive:
            manifest = json.loads(archive.read("manifest/report-evidence.json"))
            assert "score_0_to_5" in archive.read("review/scorecard.csv").decode("utf-8-sig")
        assert manifest["schema_version"] == "airank.report-evidence-packet.v7"
        assert manifest["evidence_integrity"]["status"] == "passed"
        assert manifest["counts"]["samples"] == 6
        assert manifest["counts"]["citations"] == 6
        assert sum(
            item["mention_class"] == "not_mentioned" for item in manifest["sample_index"]
        ) == 3
        source_summary = manifest["source_governance"]["summary"]
        assert source_summary["source_host_count"] == 2
        assert source_summary["classified_host_count"] == 2
        assert source_summary["effective_classified_host_count"] == 1
        assert source_summary["expired_classification_count"] == 1
        assert source_summary["unresolved_citation_count"] == 2
        assert source_summary["authority_coverage_rate"] == 0.5
        assert source_summary["authority_summary_eligible"] is False
        assert "source_classification_expired" in manifest["measurement"]["known_limitations"]
        assert "citation_host_unresolved" in manifest["measurement"]["known_limitations"]
        reviewed_entry = next(
            item
            for item in manifest["source_governance"]["entries"]
            if item["normalized_host"] == "news.example.com"
        )
        revision = reviewed_entry["current_revision"]
        revision_record = {
            key: value
            for key, value in revision.items()
            if key != "revision_record_sha256"
        }
        assert revision["revision_record_sha256"] == canonical_json_sha256(
            revision_record
        )
        assert packet.summary.source_host_count == 2
        assert packet.summary.source_authority_resolved_count == 1
        assert packet.summary.source_authority_coverage_rate == 0.5
        assert packet.summary.source_authority_summary_eligible is False

        receipt = MySQLReportRepository(database_url()).record_download_receipt(
            tenant_id,
            report_id,
            DownloadReceiptRequest(
                packet_id=packet.packet_id,
                content_sha256=packet.content_sha256,
            ),
            "integration_reporter",
            "trc_report_packet_download_it",
        )
        assert receipt.packet_id == packet.packet_id
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_worker_lease_store_claims_and_completes_job() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_it_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    store = MySQLJobLeaseStore(database_url())
    now = utc_datetime() - timedelta(days=1)
    job_id = f"job_{uuid4().hex[:12]}"

    try:
        store.add(
            AsyncJob(
                id=job_id,
                tenant_id=tenant_id,
                project_id=None,
                job_type="scan.provider",
                priority=-1000,
                scheduled_at=now,
                payload={"provider": "chatgpt"},
            )
        )

        claim_time = utc_datetime()
        claimed = store.claim_next("worker-real-it", claim_time)
        assert claimed is not None
        assert claimed.id == job_id
        assert claimed.status == AsyncJobStatus.RUNNING
        assert claimed.locked_by == "worker-real-it"
        assert claimed.payload == {"provider": "chatgpt"}

        heartbeat = store.heartbeat(claimed.id, "worker-real-it", claim_time)
        assert heartbeat.heartbeat_at == claim_time

        finished = store.succeed(claimed.id, "worker-real-it", claim_time, {"snapshots": 1})
        assert finished.status == AsyncJobStatus.SUCCEEDED
        assert finished.result == {"snapshots": 1}

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT status, locked_by, result_json
                    FROM airank_async_jobs
                    WHERE tenant_id = :tenant_id AND id = :job_id
                    """
                ),
                {"tenant_id": tenant_id, "job_id": claimed.id},
            ).mappings().one()
        assert row["status"] == "succeeded"
        assert row["locked_by"] == "worker-real-it"
        assert json.loads(row["result_json"]) == {"snapshots": 1}
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_provider_operations_are_shared_and_idempotent() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_provider_{uuid4().hex[:10]}"
    provider = f"provider_{uuid4().hex[:8]}"
    fingerprint = "a" * 64
    engine = create_engine(database_url(), pool_pre_ping=True)
    env = {
        "AIRANK_PROVIDER_CIRCUIT_FAILURE_THRESHOLD": "1",
        "AIRANK_PROVIDER_CIRCUIT_COOLDOWN_SECONDS": "1",
        "AIRANK_PROVIDER_DEFAULT_QUOTA_UNITS": "1",
        "AIRANK_PROVIDER_QUOTA_RESERVATION_TTL_SECONDS": "30",
        "AIRANK_PROVIDER_QPS": "1",
        "AIRANK_PROVIDER_CONCURRENCY": "1",
    }
    first_worker = MySQLProviderOperations(database_url(), env=env)
    second_worker = MySQLProviderOperations(database_url(), env=env)
    context = ProviderRequestContext(
        tenant_id=tenant_id,
        project_id="project_provider_it",
        idempotency_key="scan_task_provider_it",
    )
    race_tenant_id = f"{tenant_id}_race"
    capacity_tenant_id = f"{tenant_id}_capacity"

    try:
        reservation = first_worker.reserve(provider, context=context)
        with pytest.raises(ProviderGatewayError) as duplicate_error:
            second_worker.reserve(provider, context=context)
        assert duplicate_error.value.code == "PROVIDER_REQUEST_IN_PROGRESS"
        assert duplicate_error.value.retryable is True

        second_worker.commit(reservation)
        with engine.connect() as conn:
            bucket = conn.execute(
                text(
                    """
                    SELECT used_units, reserved_units
                    FROM airank_provider_quota_buckets
                    WHERE tenant_id = :tenant_id AND provider_key = :provider_key
                    """
                ),
                {"tenant_id": tenant_id, "provider_key": provider},
            ).mappings().one()
        assert int(bucket["used_units"]) == 1
        assert int(bucket["reserved_units"]) == 0

        with pytest.raises(ProviderGatewayError) as quota_error:
            first_worker.reserve(
                provider,
                context=ProviderRequestContext(
                    tenant_id=tenant_id,
                    project_id="project_provider_it",
                    idempotency_key="scan_task_provider_it_2",
                ),
            )
        assert quota_error.value.code == "PROVIDER_QUOTA_EXHAUSTED"

        def reserve_from_worker(index: int) -> str:
            worker = first_worker if index == 1 else second_worker
            try:
                return worker.reserve(
                    provider,
                    context=ProviderRequestContext(
                        tenant_id=race_tenant_id,
                        project_id="project_provider_race",
                        idempotency_key=f"scan_task_race_{index}",
                    ),
                ).reservation_id
            except ProviderGatewayError as exc:
                return exc.code

        with ThreadPoolExecutor(max_workers=2) as executor:
            race_results = list(executor.map(reserve_from_worker, (1, 2)))
        assert sum(result.startswith("quota_") for result in race_results) == 1
        assert race_results.count("PROVIDER_QUOTA_EXHAUSTED") == 1

        capacity_context_1 = ProviderRequestContext(
            tenant_id=capacity_tenant_id,
            project_id="project_provider_capacity",
            idempotency_key="capacity_task_1",
        )
        capacity_context_2 = ProviderRequestContext(
            tenant_id=capacity_tenant_id,
            project_id="project_provider_capacity",
            idempotency_key="capacity_task_2",
        )
        capacity_context_3 = ProviderRequestContext(
            tenant_id=capacity_tenant_id,
            project_id="project_provider_capacity",
            idempotency_key="capacity_task_3",
        )
        capacity_lease_1 = first_worker.acquire_capacity(
            provider, fingerprint, context=capacity_context_1
        )
        with pytest.raises(ProviderGatewayError) as concurrency_error:
            second_worker.acquire_capacity(
                provider, fingerprint, context=capacity_context_2
            )
        assert concurrency_error.value.code == "PROVIDER_DISTRIBUTED_CONCURRENCY_LIMITED"
        assert concurrency_error.value.retryable is True

        first_worker.release_capacity(capacity_lease_1)
        with pytest.raises(ProviderGatewayError) as rate_error:
            second_worker.acquire_capacity(
                provider, fingerprint, context=capacity_context_2
            )
        assert rate_error.value.code == "PROVIDER_DISTRIBUTED_RATE_LIMITED"
        assert rate_error.value.retryable is True

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_provider_capacity_states
                    SET available_tokens=0, last_refill_at=:last_refill_at
                    WHERE provider_key=:provider_key
                      AND configuration_fingerprint=:configuration_fingerprint
                    """
                ),
                {
                    "last_refill_at": datetime.now(timezone.utc).replace(tzinfo=None)
                    - timedelta(seconds=2),
                    "provider_key": provider,
                    "configuration_fingerprint": fingerprint,
                },
            )
        capacity_lease_2 = second_worker.acquire_capacity(
            provider, fingerprint, context=capacity_context_2
        )
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_provider_capacity_leases
                    SET expires_at=:expired_at WHERE id=:lease_id
                    """
                ),
                {
                    "expired_at": datetime.now(timezone.utc).replace(tzinfo=None)
                    - timedelta(seconds=1),
                    "lease_id": capacity_lease_2.lease_id,
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE airank_provider_capacity_states
                    SET available_tokens=0, last_refill_at=:last_refill_at
                    WHERE provider_key=:provider_key
                      AND configuration_fingerprint=:configuration_fingerprint
                    """
                ),
                {
                    "last_refill_at": datetime.now(timezone.utc).replace(tzinfo=None)
                    - timedelta(seconds=2),
                    "provider_key": provider,
                    "configuration_fingerprint": fingerprint,
                },
            )
        recovered_lease = first_worker.acquire_capacity(
            provider, fingerprint, context=capacity_context_3
        )
        with engine.connect() as conn:
            capacity_state = conn.execute(
                text(
                    """
                    SELECT in_flight_count FROM airank_provider_capacity_states
                    WHERE provider_key=:provider_key
                      AND configuration_fingerprint=:configuration_fingerprint
                    """
                ),
                {
                    "provider_key": provider,
                    "configuration_fingerprint": fingerprint,
                },
            ).scalar_one()
            expired_status = conn.execute(
                text(
                    "SELECT status FROM airank_provider_capacity_leases WHERE id=:lease_id"
                ),
                {"lease_id": capacity_lease_2.lease_id},
            ).scalar_one()
        assert int(capacity_state) == 1
        assert expired_status == "expired"
        first_worker.release_capacity(recovered_lease)

        race_fingerprint = "b" * 64

        def acquire_capacity_from_worker(index: int) -> str:
            worker = first_worker if index == 1 else second_worker
            try:
                return worker.acquire_capacity(
                    provider,
                    race_fingerprint,
                    context=ProviderRequestContext(
                        tenant_id=capacity_tenant_id,
                        project_id="project_provider_capacity_race",
                        idempotency_key=f"capacity_race_{index}",
                    ),
                ).lease_id
            except ProviderGatewayError as exc:
                return exc.code

        with ThreadPoolExecutor(max_workers=2) as executor:
            capacity_race_results = list(
                executor.map(acquire_capacity_from_worker, (1, 2))
            )
        assert sum(result.startswith("capacity_") for result in capacity_race_results) == 1
        assert capacity_race_results.count(
            "PROVIDER_DISTRIBUTED_CONCURRENCY_LIMITED"
        ) == 1
        winning_capacity_lease_id = next(
            result for result in capacity_race_results if result.startswith("capacity_")
        )
        first_worker.release_capacity(
            ProviderCapacityLease(
                provider=provider,
                configuration_fingerprint=race_fingerprint,
                tenant_id=capacity_tenant_id,
                lease_id=winning_capacity_lease_id,
            )
        )

        first_worker.failure(provider, fingerprint, retryable=True)
        assert second_worker.allow(provider, fingerprint) is False
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_provider_circuit_states
                    SET opened_at = :opened_at
                    WHERE provider_key = :provider_key
                      AND configuration_fingerprint = :configuration_fingerprint
                    """
                ),
                {
                    "opened_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=2),
                    "provider_key": provider,
                    "configuration_fingerprint": fingerprint,
                },
            )
        assert first_worker.allow(provider, fingerprint) is True
        assert second_worker.allow(provider, fingerprint) is False
        second_worker.success(provider, fingerprint)
        assert first_worker.allow(provider, fingerprint) is True

        checked_at = datetime.now(timezone.utc)
        first_worker.record_probe(
            ProbeResult(
                provider=provider,
                level=ProbeLevel.GENERATION,
                state=HealthState.HEALTHY,
                checked_at=checked_at,
                duration_ms=12,
                model="model-it",
                endpoint_host="provider.example.test",
                request_id_present=True,
            )
        )
        with engine.connect() as conn:
            probe = conn.execute(
                text(
                    """
                    SELECT health_state, request_id_present
                    FROM airank_provider_probe_runs
                    WHERE provider_key = :provider_key
                    ORDER BY checked_at DESC LIMIT 1
                    """
                ),
                {"provider_key": provider},
            ).mappings().one()
        assert probe["health_state"] == "healthy"
        assert bool(probe["request_id_present"]) is True
    finally:
        cleanup_tenant(engine, capacity_tenant_id)
        cleanup_tenant(engine, race_tenant_id)
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM airank_provider_probe_runs WHERE provider_key = :provider_key"),
                {"provider_key": provider},
            )
            conn.execute(
                text("DELETE FROM airank_provider_circuit_states WHERE provider_key = :provider_key"),
                {"provider_key": provider},
            )
            conn.execute(
                text("DELETE FROM airank_provider_capacity_states WHERE provider_key = :provider_key"),
                {"provider_key": provider},
            )
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_provider_route_manifests_are_public_and_versioned() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    provider = f"provider_route_{uuid4().hex[:8]}"
    route_id = f"route-{uuid4().hex[:8]}"
    route_env = f"{provider.upper()}_ROUTES_JSON"
    engine = create_engine(database_url(), pool_pre_ping=True)
    env = {
        "AIRANK_ALLOW_CUSTOM_PROVIDER_ENDPOINTS": "true",
        "ROUTE_TEST_PRIMARY_KEY": "secret-route-value-never-persisted",
        route_env: json.dumps(
            [
                {
                    "route_id": route_id,
                    "priority": 100,
                    "endpoint": "https://route-primary.example.test/v1/chat/completions",
                    "model": "route-model-v1",
                    "key_env": "ROUTE_TEST_PRIMARY_KEY",
                }
            ]
        ),
    }
    manifest = ProviderManifest(
        provider=provider,
        label="Provider Route Integration",
        implementation_status=ImplementationStatus.PARTIAL,
        collection_mode="provider_api",
        endpoint_env=f"{provider.upper()}_API_URL",
        endpoint_default="https://route-default.example.test/v1/chat/completions",
        key_env=f"{provider.upper()}_API_KEY",
        model_env=f"{provider.upper()}_MODEL",
        model_default="route-model-default",
        disabled_env=f"{provider.upper()}_DISABLED",
        request_kind="openai_chat",
        capabilities=ProviderCapabilities(web_search=False, citations=False),
        allowed_endpoint_hosts=("route-primary.example.test",),
    )
    operations = MySQLProviderOperations(database_url(), env=env)

    try:
        operations.sync_manifests([manifest])
        with engine.connect() as conn:
            first = conn.execute(
                text(
                    """
                    SELECT route_id, priority, endpoint_host, model_name,
                           request_contract_json, configuration_fingerprint, is_current
                    FROM airank_provider_routes
                    WHERE provider_key=:provider_key AND route_id=:route_id
                    """
                ),
                {"provider_key": provider, "route_id": route_id},
            ).mappings().one()
        assert first["endpoint_host"] == "route-primary.example.test"
        assert first["model_name"] == "route-model-v1"
        assert len(str(first["configuration_fingerprint"])) == 64
        assert bool(first["is_current"]) is True
        assert '"max_tokens": 4096' in str(first["request_contract_json"])
        assert "secret-route-value-never-persisted" not in json.dumps(
            dict(first), default=str
        )

        env[route_env] = json.dumps(
            [
                {
                    "route_id": route_id,
                    "priority": 100,
                    "endpoint": "https://route-primary.example.test/v1/chat/completions",
                    "model": "route-model-v2",
                    "key_env": "ROUTE_TEST_PRIMARY_KEY",
                }
            ]
        )
        operations.sync_manifests([manifest])
        with engine.connect() as conn:
            versions = conn.execute(
                text(
                    """
                    SELECT model_name, is_current FROM airank_provider_routes
                    WHERE provider_key=:provider_key AND route_id=:route_id
                    ORDER BY created_at, route_version
                    """
                ),
                {"provider_key": provider, "route_id": route_id},
            ).mappings().all()
        assert len(versions) == 2
        assert sum(bool(row["is_current"]) for row in versions) == 1
        assert next(row["model_name"] for row in versions if row["is_current"]) == "route-model-v2"

        env["ROUTE_TEST_PRIMARY_KEY"] = "rotated-secret-route-value-never-persisted"
        operations.sync_manifests([manifest])
        with engine.connect() as conn:
            route_versions = conn.execute(
                text(
                    """
                    SELECT model_name, configuration_fingerprint, is_current
                    FROM airank_provider_routes
                    WHERE provider_key=:provider_key AND route_id=:route_id
                    ORDER BY created_at, route_version
                    """
                ),
                {"provider_key": provider, "route_id": route_id},
            ).mappings().all()
            manifest_versions = conn.execute(
                text(
                    """
                    SELECT configuration_fingerprint, is_current
                    FROM airank_provider_manifests
                    WHERE provider_key=:provider_key
                    ORDER BY created_at, manifest_version
                    """
                ),
                {"provider_key": provider},
            ).mappings().all()
        assert len(route_versions) == 3
        assert len({str(row["configuration_fingerprint"]) for row in route_versions}) == 3
        assert sum(bool(row["is_current"]) for row in route_versions) == 1
        assert len(manifest_versions) == 3
        assert len({str(row["configuration_fingerprint"]) for row in manifest_versions}) == 3
        assert sum(bool(row["is_current"]) for row in manifest_versions) == 1
        assert "rotated-secret-route-value-never-persisted" not in json.dumps(
            [dict(row) for row in route_versions + manifest_versions], default=str
        )
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM airank_provider_routes WHERE provider_key=:provider_key"),
                {"provider_key": provider},
            )
            conn.execute(
                text("DELETE FROM airank_provider_manifests WHERE provider_key=:provider_key"),
                {"provider_key": provider},
            )


def test_real_mysql_provider_route_controls_apply_without_restart_and_are_audited() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    suffix = uuid4().hex[:8]
    primary_route = f"primary-{suffix}"
    secondary_route = f"secondary-{suffix}"
    env = {
        "QIANWEN_API_KEY": "default-secret-never-persisted",
        "QIANWEN_MODEL": "qwen-default",
        "QIANWEN_PRIMARY_TEST_KEY": "primary-secret-never-persisted",
        "QIANWEN_SECONDARY_TEST_KEY": "secondary-secret-never-persisted",
        "QIANWEN_ROUTES_JSON": json.dumps(
            [
                {
                    "route_id": primary_route,
                    "priority": 100,
                    "model": "qwen-primary-test",
                    "key_env": "QIANWEN_PRIMARY_TEST_KEY",
                },
                {
                    "route_id": secondary_route,
                    "priority": 50,
                    "model": "qwen-secondary-test",
                    "key_env": "QIANWEN_SECONDARY_TEST_KEY",
                },
            ]
        ),
    }
    engine = create_engine(database_url(), pool_pre_ping=True)
    operations = MySQLProviderOperations(database_url(), env=env)
    configured = resolve_provider_routes(PROVIDER_MANIFESTS["qianwen"], env)

    try:
        record = operations.set_route_control(
            "qianwen",
            primary_route,
            enabled=False,
            priority_override=None,
            expected_version=0,
            changed_by="integration-route-admin",
            reason="planned primary maintenance",
        )
        assert record["control_version"] == 1
        assert [route.route_id for route in operations.apply_routes("qianwen", configured)] == [
            secondary_route
        ]
        route_status = operations.list_route_status([PROVIDER_MANIFESTS["qianwen"]])
        primary_status = next(item for item in route_status if item["route_id"] == primary_route)
        secondary_status = next(item for item in route_status if item["route_id"] == secondary_route)
        assert primary_status["enabled"] is False
        assert primary_status["control_version"] == 1
        assert primary_status["request_count_24h"] == 0
        assert secondary_status["enabled"] is True
        assert secondary_status["effective_priority"] == 50
        assert "secret-never-persisted" not in json.dumps(route_status, default=str)

        with pytest.raises(ProviderGatewayError) as stale:
            operations.set_route_control(
                "qianwen",
                primary_route,
                enabled=True,
                priority_override=200,
                expected_version=0,
                changed_by="stale-admin",
                reason="stale update",
            )
        assert stale.value.code == "PROVIDER_ROUTE_CONTROL_CONFLICT"

        with pytest.raises(ProviderGatewayError) as last_route:
            operations.set_route_control(
                "qianwen",
                secondary_route,
                enabled=False,
                priority_override=None,
                expected_version=0,
                changed_by="integration-route-admin",
                reason="must not disable all routes",
            )
        assert last_route.value.code == "PROVIDER_LAST_ROUTE_DISABLE_FORBIDDEN"

        with engine.connect() as conn:
            event = conn.execute(
                text(
                    """
                    SELECT previous_control_json, new_control_json, changed_by, reason
                    FROM airank_provider_route_control_events
                    WHERE provider_key='qianwen' AND route_id=:route_id
                    """
                ),
                {"route_id": primary_route},
            ).mappings().one()
        serialized = json.dumps(dict(event), default=str)
        assert event["changed_by"] == "integration-route-admin"
        assert "planned primary maintenance" in serialized
        assert "secret-never-persisted" not in serialized
    finally:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    DELETE FROM airank_provider_route_control_events
                    WHERE provider_key='qianwen' AND route_id IN (:primary_route, :secondary_route)
                    """
                ),
                {"primary_route": primary_route, "secondary_route": secondary_route},
            )
            conn.execute(
                text(
                    """
                    DELETE FROM airank_provider_route_controls
                    WHERE provider_key='qianwen' AND route_id IN (:primary_route, :secondary_route)
                    """
                ),
                {"primary_route": primary_route, "secondary_route": secondary_route},
            )


def test_real_mysql_provider_usage_ledger_keeps_raw_usage_and_cost_provenance_separate() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    suffix = uuid4().hex[:10]
    tenant_id = f"tenant_usage_{suffix}"
    project_id = f"project_usage_{suffix}"
    route_id = f"route-usage-{suffix}"
    model_name = f"qwen-usage-{suffix}"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    engine = create_engine(database_url(), pool_pre_ping=True)
    ledger = MySQLProviderUsageLedger(database_url())

    try:
        with engine.begin() as conn:
            for index, outcome in enumerate(("failed", "success", "success"), start=1):
                audit_id = f"audit_usage_{suffix}_{index}"
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_provider_request_audits (
                          id, tenant_id, project_id, provider_key, route_id, model_name,
                          endpoint_host, configuration_fingerprint, provider_request_id,
                          prompt_sha256, outcome, attempt_count, duration_ms,
                          requested_at, completed_at
                        )
                        VALUES (
                          :id, :tenant_id, :project_id, 'qianwen', :route_id, :model_name,
                          'dashscope.aliyuncs.com', :configuration_fingerprint, :provider_request_id,
                          :prompt_sha256, :outcome, 1, 100,
                          :requested_at, :completed_at
                        )
                        """
                    ),
                    {
                        "id": audit_id,
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "route_id": route_id,
                        "model_name": model_name,
                        "configuration_fingerprint": hashlib.sha256(audit_id.encode()).hexdigest(),
                        "provider_request_id": f"provider-request-{index}",
                        "prompt_sha256": hashlib.sha256(f"prompt-{index}".encode()).hexdigest(),
                        "outcome": outcome,
                        "requested_at": now,
                        "completed_at": now,
                    },
                )
                if index == 1:
                    usage = {
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "total_tokens": 150,
                        "precision": "exact",
                        "source": "provider_response",
                    }
                elif index == 2:
                    usage = {
                        "input_tokens": 20,
                        "output_tokens": 10,
                        "total_tokens": 30,
                        "precision": "exact",
                        "source": "provider_response",
                        "cost_amount": "0.01",
                        "cost_currency": "CNY",
                        "cost_precision": "exact",
                        "cost_source": "provider_response_billed",
                    }
                else:
                    usage = {
                        "precision": "unknown",
                        "source": "missing",
                    }
                persist_provider_usage_event(
                    conn,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    request_audit_id=audit_id,
                    provider_key="qianwen",
                    model_name=model_name,
                    usage=usage,
                    occurred_at=now,
                )

        before_price = ledger.list_usage(tenant_id=tenant_id)
        assert before_price["summary"]["event_count"] == 3
        assert before_price["summary"]["exact_cost_count"] == 1
        assert before_price["summary"]["unknown_cost_count"] == 2
        assert next(event for event in before_price["events"] if event["outcome"] == "failed")[
            "usage_precision"
        ] == "exact"

        price = ledger.create_price_version(
            tenant_id=tenant_id,
            provider_key="qianwen",
            route_id=route_id,
            model_name=model_name,
            currency="CNY",
            input_price_per_million="2",
            output_price_per_million="8",
            effective_from=now - timedelta(minutes=1),
            effective_until=None,
            source_kind="official_price_page",
            source_reference="https://example.test/verified-price",
            expected_previous_version=0,
            reason="real mysql usage ledger verification",
            created_by="integration-provider-admin",
        )
        assert price["catalog_version"] == 1
        assert price["backfilled_usage_count"] == 1

        after_price = ledger.list_usage(tenant_id=tenant_id)
        assert after_price["summary"] == {
            "event_count": 3,
            "exact_usage_count": 2,
            "estimated_usage_count": 0,
            "unknown_usage_count": 1,
            "exact_cost_count": 1,
            "estimated_cost_count": 1,
            "unknown_cost_count": 1,
            "known_cost_event_count": 2,
            "cost_coverage_rate": 0.666667,
            "known_cost_amount": "0.010600000000",
            "known_cost_currency": "CNY",
            "aggregate_cost_precision": "unknown",
        }
        route_operations = MySQLProviderOperations(
            database_url(),
            env={
                "QIANWEN_API_KEY": "runtime-only-usage-ledger-key",
                "QIANWEN_ROUTES_JSON": json.dumps(
                    [
                        {
                            "route_id": route_id,
                            "model": model_name,
                            "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                            "key_env": "QIANWEN_API_KEY",
                        }
                    ]
                ),
            },
        )
        route_status = route_operations.list_route_status(
            [PROVIDER_MANIFESTS["qianwen"]], tenant_id=tenant_id
        )[0]
        assert route_status["usage_event_count_24h"] == 3
        assert route_status["known_cost_event_count_24h"] == 2
        assert route_status["unknown_cost_event_count_24h"] == 1
        assert route_status["cost_coverage_rate_24h"] == 0.666667
        assert route_status["aggregate_cost_precision_24h"] == "unknown"
        assert "runtime-only-usage-ledger-key" not in json.dumps(route_status, default=str)
        estimated = ledger.list_usage(tenant_id=tenant_id, cost_precision="estimated")
        assert estimated["summary"]["event_count"] == 1
        assert estimated["events"][0]["cost_source"] == "catalog_calculated"
        assert estimated["events"][0]["price_version_id"] == price["price_version_id"]
        assert len(estimated["events"][0]["raw_usage_sha256"]) == 64
        assert len(estimated["events"][0]["calculation_sha256"]) == 64
        assert ledger.list_usage(tenant_id=f"other_{tenant_id}")["summary"]["event_count"] == 0

        replay = ledger.create_price_version(
            tenant_id=tenant_id,
            provider_key="qianwen",
            route_id=route_id,
            model_name=model_name,
            currency="CNY",
            input_price_per_million="2",
            output_price_per_million="8",
            effective_from=now - timedelta(minutes=1),
            effective_until=None,
            source_kind="official_price_page",
            source_reference="https://example.test/verified-price",
            expected_previous_version=0,
            reason="real mysql usage ledger verification",
            created_by="integration-provider-admin",
        )
        assert replay["replay_status"] == "idempotent_replay"
        assert replay["backfilled_usage_count"] == 0

        with pytest.raises(ProviderGatewayError) as stale:
            ledger.create_price_version(
                tenant_id=tenant_id,
                provider_key="qianwen",
                route_id=route_id,
                model_name=model_name,
                currency="CNY",
                input_price_per_million="3",
                output_price_per_million="9",
                effective_from=now,
                effective_until=None,
                source_kind="manual_verified",
                source_reference="manual-price-recheck",
                expected_previous_version=0,
                reason="stale version must be rejected",
                created_by="integration-provider-admin",
            )
        assert stale.value.code == "PROVIDER_PRICE_VERSION_CONFLICT"
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_knowledge_governance_derives_expiry_and_conflict_queue() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_knowledge_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    knowledge_repo = MySQLKnowledgeRepository(database_url())
    now = datetime.now(timezone.utc)

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-knowledge.example.com",
                brand_name_hint="AIRank Knowledge",
                industry_hint="B2B SaaS",
            ),
        )
        expired_source = knowledge_repo.create_source(
            tenant_id,
            project.project_id,
            KnowledgeSourceCreateRequest(
                idempotency_key="knowledge-expired-source-it",
                source_type="qualification",
                title="已过期资质",
                content_text="该资质仅用于验证过期提醒。",
                source_uri="https://airank-knowledge.example.com/expired",
                authority_level="official",
                risk_level="low",
                valid_until=now - timedelta(days=2),
            ),
        )
        expiring_source = knowledge_repo.create_source(
            tenant_id,
            project.project_id,
            KnowledgeSourceCreateRequest(
                idempotency_key="knowledge-expiring-source-it",
                source_type="official_website",
                title="即将到期产品说明",
                content_text="AIRank 提供可追溯的多平台 GEO 测量。",
                source_uri="https://airank-knowledge.example.com/facts",
                authority_level="official",
                risk_level="low",
                valid_until=now + timedelta(days=5),
            ),
        )
        original = knowledge_repo.propose_fact(
            tenant_id,
            project.project_id,
            FactProposalRequest(
                title="测量能力",
                fact_text="AIRank 提供可追溯的多平台 GEO 测量。",
                source_ids=[expiring_source.source_id],
                risk_level="low",
                disclosure="public",
                created_by="integration-test",
                valid_until=now + timedelta(days=3),
            ),
        )
        approved = knowledge_repo.review_revision(
            tenant_id,
            project.project_id,
            original.revision_id,
            FactRevisionReviewRequest(action="approved", reviewed_by="integration-reviewer"),
        )
        revised = knowledge_repo.revise_fact(
            tenant_id,
            project.project_id,
            original.fact_id,
            FactProposalRequest(
                title="测量能力",
                fact_text="AIRank 只提供单平台 GEO 测量。",
                source_ids=[expiring_source.source_id],
                risk_level="low",
                disclosure="public",
                created_by="integration-test",
            ),
        )
        conflict = knowledge_repo.create_conflict(
            tenant_id,
            project.project_id,
            original.fact_id,
            FactConflictCreateRequest(
                left_revision_id=original.revision_id,
                right_revision_id=revised.revision_id,
                conflict_type="value_mismatch",
                description="平台覆盖范围冲突",
            ),
        )

        listed_sources = knowledge_repo.list_sources(tenant_id, project.project_id)
        open_conflicts = knowledge_repo.list_conflicts(tenant_id, project.project_id, "open")
        facts = knowledge_repo.list_facts(tenant_id, project.project_id)
        governance = derive_knowledge_governance(
            listed_sources,
            facts,
            open_conflicts,
            within_days=7,
            as_of=now,
        )

        approved_after_conflict = next(item for item in facts if item.revision_id == approved.revision_id)
        expiring_source_after_read = next(item for item in listed_sources if item.source_id == expiring_source.source_id)
        assert expiring_source_after_read.valid_until is not None
        assert expiring_source_after_read.valid_until.utcoffset() == timedelta(0)
        assert approved_after_conflict.valid_until is not None
        assert approved_after_conflict.valid_until.utcoffset() == timedelta(0)
        assert open_conflicts[0].detected_at.utcoffset() == timedelta(0)
        assert approved_after_conflict.eligible_for_generation is False
        assert approved_after_conflict.eligibility_reason == "open_conflict"
        assert [item.conflict_id for item in open_conflicts] == [conflict.conflict_id]
        assert governance.expired_source_count == 1
        assert governance.expiring_source_count == 1
        assert governance.expiring_fact_count == 1
        assert governance.open_conflict_count == 1
        assert governance.action_required_count == 4
        assert any(alert.entity_id == expired_source.source_id for alert in governance.alerts)

        knowledge_repo.resolve_conflict(
            tenant_id,
            project.project_id,
            conflict.conflict_id,
            FactConflictResolveRequest(
                resolution="resolved_left",
                resolved_by="integration-reviewer",
                resolution_note="官方原文支持左版本",
            ),
        )
        assert knowledge_repo.list_conflicts(tenant_id, project.project_id, "open") == []
        restored = next(
            item for item in knowledge_repo.list_facts(tenant_id, project.project_id)
            if item.revision_id == approved.revision_id
        )
        assert restored.eligible_for_generation is True
        assert restored.eligibility_reason == "approved_current_fact"
        with pytest.raises(StarletteHTTPException) as duplicate_error:
            knowledge_repo.create_conflict(
                tenant_id,
                project.project_id,
                original.fact_id,
                FactConflictCreateRequest(
                    left_revision_id=revised.revision_id,
                    right_revision_id=original.revision_id,
                    conflict_type="value_mismatch",
                    description="同一修订对不能重复登记",
                ),
            )
        assert duplicate_error.value.status_code == 409
        assert duplicate_error.value.detail["code"] == "STATE_CONFLICT"
        assert duplicate_error.value.detail["details"]["status"] == "resolved_left"

        source_revision = knowledge_repo.revise_source(
            tenant_id,
            project.project_id,
            expiring_source.source_id,
            KnowledgeSourceCreateRequest(
                idempotency_key="knowledge-source-revision-it",
                source_type="official_website",
                title="AIRank 产品说明 2026-08",
                content_text="AIRank 提供可追溯的多平台 GEO 测量和审计日志。",
                source_uri="https://airank-knowledge.example.com/facts",
                authority_level="official",
                risk_level="low",
            ),
        )
        source_replay = knowledge_repo.revise_source(
            tenant_id,
            project.project_id,
            expiring_source.source_id,
            KnowledgeSourceCreateRequest(
                idempotency_key="knowledge-source-revision-it",
                source_type="official_website",
                title="AIRank 产品说明 2026-08",
                content_text="AIRank 提供可追溯的多平台 GEO 测量和审计日志。",
                source_uri="https://airank-knowledge.example.com/facts",
                authority_level="official",
                risk_level="low",
            ),
        )
        sources_after_revision = knowledge_repo.list_sources(tenant_id, project.project_id)
        facts_after_source_revision = knowledge_repo.list_facts(tenant_id, project.project_id)
        search = knowledge_repo.search_segments(tenant_id, project.project_id, "审计日志", 10)
        governance_after_revision = derive_knowledge_governance(
            sources_after_revision,
            facts_after_source_revision,
            knowledge_repo.list_conflicts(tenant_id, project.project_id, "open"),
            within_days=7,
            as_of=now,
        )

        assert source_revision.parent_source_id == expiring_source.source_id
        assert source_revision.revision_number == 2
        assert source_replay.source_id == source_revision.source_id
        assert source_replay.idempotent_replay is True
        assert next(item for item in sources_after_revision if item.source_id == expiring_source.source_id).status == "stale"
        invalidated = next(
            item for item in facts_after_source_revision
            if item.revision_id == approved.revision_id
        )
        assert invalidated.eligible_for_generation is False
        assert invalidated.eligibility_reason == "source_stale"
        assert governance_after_revision.stale_source_count == 1
        assert search.retrieval_mode == "lexical_only"
        assert search.vector_status == "not_configured"
        assert search.returned_count == 1
        assert search.results[0].source_id == source_revision.source_id
        assert search.results[0].text == "AIRank 提供可追溯的多平台 GEO 测量和审计日志。"
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_comparison_and_explainer_assets_reach_reviewed_publish_snapshots() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_specialized_content_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    knowledge_repo = MySQLKnowledgeRepository(database_url())
    delivery_repo = MySQLDeliveryRepository(database_url())
    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-specialized-content.example.com",
                brand_name_hint="AIRank Specialized Content",
                industry_hint="B2B SaaS",
            ),
        )
        subjects = [
            ComparisonSubjectRequest(subject_id="subject_airank", display_name="AIRank", subject_type="brand"),
            ComparisonSubjectRequest(subject_id="subject_peer", display_name="竞品甲", subject_type="competitor"),
        ]
        dimensions = [
            ComparisonDimensionRequest(dimension_id=f"d{index}", label=f"核验维度 {index}")
            for index in range(1, 11)
        ]
        cells: list[ComparisonCellRequest] = []
        for subject in subjects:
            for dimension in dimensions:
                fact_text = f"{subject.display_name} 在{dimension.label}下的已核验事实。"
                source = knowledge_repo.create_source(
                    tenant_id,
                    project.project_id,
                    KnowledgeSourceCreateRequest(
                        idempotency_key=f"comparison-{subject.subject_id}-{dimension.dimension_id}",
                        source_type="official_document",
                        title=f"{subject.display_name} {dimension.label}来源",
                        content_text=fact_text,
                        authority_level="official",
                        risk_level="low",
                    ),
                )
                fact = knowledge_repo.propose_fact(
                    tenant_id,
                    project.project_id,
                    FactProposalRequest(
                        title=f"{subject.display_name} {dimension.label}",
                        fact_text=fact_text,
                        source_ids=[source.source_id],
                        subject_type=subject.subject_type,
                        subject_ref_id=subject.subject_id,
                        risk_level="low",
                        disclosure="public",
                        created_by="integration-test",
                    ),
                )
                knowledge_repo.review_revision(
                    tenant_id,
                    project.project_id,
                    fact.revision_id,
                    FactRevisionReviewRequest(action="approved", reviewed_by="integration-reviewer"),
                )
                cells.append(ComparisonCellRequest(subject_id=subject.subject_id, dimension_id=dimension.dimension_id, fact_revision_ids=[fact.revision_id]))

        comparison = knowledge_repo.create_comparison_content(
            tenant_id,
            project.project_id,
            ComparisonContentCreateRequest(
                title="只进入 brief hash 的对比要求",
                direction="使用同一维度且不输出排名",
                target_subject_id="subject_airank",
                subjects=subjects,
                dimensions=dimensions,
                cells=cells,
                created_by="integration-test",
            ),
        )
        comparison_review = delivery_repo.review_content(
            tenant_id,
            comparison.asset_id,
            ContentReviewRequest(action="approved", reviewed_by="integration-reviewer"),
        )
        comparison_package = delivery_repo.create_package(
            tenant_id,
            comparison.asset_id,
            PublishPackageCreateRequest(channel="export", idempotency_key="comparison-export-it", requested_by="integration-test"),
        )

        roles = ["definition", "mechanism", "mechanism", "step", "step", "step", "criterion", "criterion", "misconception", "faq", "faq", "boundary"]
        assignments: list[ExplainerFactAssignmentRequest] = []
        for index, role in enumerate(roles, start=1):
            fact_text = f"第{index}条已审核说明：" + "该事实基于当前有效来源的精确原文边界，用于解释适用范围、执行条件与验证方式，不扩展为来源之外的承诺。" * 3
            source = knowledge_repo.create_source(
                tenant_id,
                project.project_id,
                KnowledgeSourceCreateRequest(
                    idempotency_key=f"explainer-source-{index:02d}",
                    source_type="official_document",
                    title=f"解释来源 {index}",
                    content_text=fact_text,
                    authority_level="official",
                    risk_level="low",
                ),
            )
            fact = knowledge_repo.propose_fact(
                tenant_id,
                project.project_id,
                FactProposalRequest(
                    title=f"解释证据 {index}",
                    fact_text=fact_text,
                    source_ids=[source.source_id],
                    subject_type="brand",
                    subject_ref_id="subject_airank",
                    risk_level="low",
                    disclosure="public",
                    created_by="integration-test",
                ),
            )
            knowledge_repo.review_revision(
                tenant_id,
                project.project_id,
                fact.revision_id,
                FactRevisionReviewRequest(action="approved", reviewed_by="integration-reviewer"),
            )
            assignments.append(ExplainerFactAssignmentRequest(fact_revision_id=fact.revision_id, content_role=role))

        explainer = knowledge_repo.create_explainer_content(
            tenant_id,
            project.project_id,
            ExplainerContentCreateRequest(
                title="只进入 brief hash 的解释要求",
                direction="覆盖七类解释证据",
                subject_id="subject_airank",
                subject_type="brand",
                display_name="AIRank",
                brand_names=["来客"],
                assignments=assignments,
                created_by="integration-test",
            ),
        )
        explainer_review = delivery_repo.review_content(
            tenant_id,
            explainer.asset_id,
            ContentReviewRequest(action="approved", reviewed_by="integration-reviewer"),
        )
        explainer_package = delivery_repo.create_package(
            tenant_id,
            explainer.asset_id,
            PublishPackageCreateRequest(channel="export", idempotency_key="explainer-export-it", requested_by="integration-test"),
        )

        with engine.begin() as conn:
            comparison_manifest = conn.execute(text("SELECT manifest_json FROM airank_publish_snapshots WHERE tenant_id=:tenant_id AND id=:snapshot_id"), {"tenant_id": tenant_id, "snapshot_id": comparison_package.snapshot_id}).scalar_one()
            explainer_manifest = conn.execute(text("SELECT manifest_json FROM airank_publish_snapshots WHERE tenant_id=:tenant_id AND id=:snapshot_id"), {"tenant_id": tenant_id, "snapshot_id": explainer_package.snapshot_id}).scalar_one()
        if isinstance(comparison_manifest, str):
            comparison_manifest = json.loads(comparison_manifest)
        if isinstance(explainer_manifest, str):
            explainer_manifest = json.loads(explainer_manifest)

        assert comparison.skill_id == "intervention.comparison-builder"
        assert comparison.section_count == 10
        assert len(comparison.claim_support_ids) == 20
        assert comparison_review.fact_check_status == "passed"
        assert comparison_package.status == "packaged"
        assert comparison_manifest["generation_skill"] == {"skill_id": "intervention.comparison-builder", "version": "1.0.0"}
        assert explainer.skill_id == "intervention.explainer-builder"
        assert explainer.section_count == 7
        assert len(explainer.claim_support_ids) == 12
        assert explainer_review.fact_check_status == "passed"
        assert explainer_package.status == "packaged"
        assert explainer_manifest["generation_skill"] == {"skill_id": "intervention.explainer-builder", "version": "1.0.0"}
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_publish_worker_persists_delivery_receipt_without_auto_retest() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_publish_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    knowledge_repo = MySQLKnowledgeRepository(database_url())
    delivery_repo = MySQLDeliveryRepository(database_url())
    execution_repo = MySQLPublishExecutionRepository(database_url())
    job_store = MySQLJobLeaseStore(database_url())

    class FakeTransport:
        calls: list[dict[str, Any]] = []

        def request(self, method, url, *, headers, payload, timeout_seconds):
            self.calls.append({"method": method, "url": url, "headers": dict(headers), "payload": payload})
            return 201, {}, {
                "id": "remote_publish_it",
                "published_url": "https://publisher.example.test/pages/airank-proof",
            }

    class FailingTransport:
        def request(self, method, url, *, headers, payload, timeout_seconds):
            raise PublisherError("PUBLISH_NETWORK_FAILED", "simulated network failure", retryable=True)

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-publish.example.com",
                brand_name_hint="AIRank Publish",
                industry_hint="B2B SaaS",
            ),
        )
        source = knowledge_repo.create_source(
            tenant_id,
            project.project_id,
            KnowledgeSourceCreateRequest(
                idempotency_key="publish-source-it",
                source_type="official_website",
                title="AIRank 官方事实",
                content_text=(
                    "AIRank 提供带原始回答和引用证据的多平台 GEO 测量。"
                    "AIRank 的内容审校保留逐主张证据支持。"
                ),
                source_uri="https://airank-publish.example.com/facts",
                authority_level="official",
                risk_level="low",
            ),
        )
        fact = knowledge_repo.propose_fact(
            tenant_id,
            project.project_id,
            FactProposalRequest(
                title="AIRank 产品能力",
                fact_text="AIRank 提供带原始回答和引用证据的多平台 GEO 测量。",
                source_ids=[source.source_id],
                risk_level="low",
                disclosure="public",
                created_by="integration-test",
            ),
        )
        knowledge_repo.review_revision(
            tenant_id,
            project.project_id,
            fact.revision_id,
            FactRevisionReviewRequest(action="approved", reviewed_by="integration-reviewer"),
        )
        second_fact = knowledge_repo.propose_fact(
            tenant_id,
            project.project_id,
            FactProposalRequest(
                title="逐主张审校",
                fact_text="AIRank 的内容审校保留逐主张证据支持。",
                source_ids=[source.source_id],
                risk_level="low",
                disclosure="public",
                created_by="integration-test",
            ),
        )
        knowledge_repo.review_revision(
            tenant_id,
            project.project_id,
            second_fact.revision_id,
            FactRevisionReviewRequest(action="approved", reviewed_by="integration-reviewer"),
        )
        original_source_text = (
            "AIRank 提供带原始回答和引用证据的多平台 GEO 测量。"
            "AIRank 的内容审校保留逐主张证据支持。"
        )
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_knowledge_source_contents
                    SET content_text = CONCAT(content_text, 'tampered')
                    WHERE tenant_id=:tenant_id AND knowledge_source_id=:source_id
                    """
                ),
                {"tenant_id": tenant_id, "source_id": source.source_id},
            )
        with pytest.raises(StarletteHTTPException) as tampered_source:
            knowledge_repo.create_governed_content(
                tenant_id,
                project.project_id,
                GovernedContentCreateRequest(
                    asset_type="fact_page",
                    title="不得使用篡改来源",
                    direction="来源完整性失败时不生成正文",
                    fact_revision_ids=[fact.revision_id],
                    created_by="integration-test",
                ),
            )
        assert tampered_source.value.status_code == 409
        assert tampered_source.value.detail["details"]["reason"] == "source_content_integrity_failed"
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_knowledge_source_contents
                    SET content_text=:content_text
                    WHERE tenant_id=:tenant_id AND knowledge_source_id=:source_id
                    """
                ),
                {
                    "content_text": original_source_text,
                    "tenant_id": tenant_id,
                    "source_id": source.source_id,
                },
            )
        uncovered_asset = knowledge_repo.create_governed_content(
            tenant_id,
            project.project_id,
            GovernedContentCreateRequest(
                asset_type="fact_page",
                title="AIRank 逐主张证据门禁",
                direction="验证每条主张分别有证据",
                fact_revision_ids=[fact.revision_id, second_fact.revision_id],
                created_by="integration-test",
            ),
        )
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_claim_supports
                    SET assertion_id = :covered_assertion_id
                    WHERE tenant_id = :tenant_id AND id = :support_id
                    """
                ),
                {
                    "covered_assertion_id": uncovered_asset.claim_assertion_ids[0],
                    "tenant_id": tenant_id,
                    "support_id": uncovered_asset.claim_support_ids[1],
                },
            )
        with pytest.raises(StarletteHTTPException) as uncovered_review:
            delivery_repo.review_content(
                tenant_id,
                uncovered_asset.asset_id,
                ContentReviewRequest(
                    action="approved", reviewed_by="integration-reviewer"
                ),
            )
        assert uncovered_review.value.status_code == 409
        assert uncovered_review.value.detail["code"] == "CONTENT_EVIDENCE_MISSING"
        asset = knowledge_repo.create_governed_content(
            tenant_id,
            project.project_id,
            GovernedContentCreateRequest(
                asset_type="fact_page",
                title="AIRank 企业事实页",
                direction="只陈述审核通过的事实",
                fact_revision_ids=[fact.revision_id],
                created_by="integration-test",
            ),
        )
        with engine.connect() as conn:
            stored_asset = conn.execute(
                text(
                    """
                    SELECT body_md, content_sha256, metadata_json
                    FROM airank_content_assets
                    WHERE tenant_id=:tenant_id AND id=:asset_id
                    """
                ),
                {"tenant_id": tenant_id, "asset_id": asset.asset_id},
            ).mappings().one()
            exact_support = conn.execute(
                text(
                    """
                    SELECT quoted_text, source_start, source_end
                    FROM airank_claim_supports
                    WHERE tenant_id=:tenant_id AND id=:support_id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "support_id": asset.claim_support_ids[0],
                },
            ).mappings().one()
        stored_metadata = stored_asset["metadata_json"]
        if isinstance(stored_metadata, str):
            stored_metadata = json.loads(stored_metadata)
        assert "direction" not in stored_metadata
        assert stored_asset["body_md"].startswith("# AIRank 产品能力｜企业事实证据页")
        assert stored_metadata["blueprint_sha256"] == asset.blueprint_sha256
        assert stored_metadata["editorial_brief_sha256"]
        assert stored_metadata["claim_bindings"][0]["source_sha256"] == source.content_sha256
        assert "只陈述审核通过的事实" not in stored_asset["body_md"]
        assert hashlib.sha256(stored_asset["body_md"].encode("utf-8")).hexdigest() == stored_asset["content_sha256"]
        assert exact_support["quoted_text"] == fact.fact_text
        assert int(exact_support["source_end"]) - int(exact_support["source_start"]) == len(fact.fact_text)
        delivery_repo.review_content(
            tenant_id,
            asset.asset_id,
            ContentReviewRequest(action="approved", reviewed_by="integration-reviewer"),
        )
        listed_assets = knowledge_repo.list_governed_content(tenant_id, project.project_id)
        assert len(listed_assets) == 2
        listed_asset = next(item for item in listed_assets if item.asset_id == asset.asset_id)
        assert listed_asset.status == "approved"
        assert listed_asset.fact_revision_ids == [fact.revision_id]
        assert len(listed_asset.claim_assertion_ids) == 1
        assert len(listed_asset.claim_support_ids) == 1
        package = delivery_repo.create_package(
            tenant_id,
            asset.asset_id,
            PublishPackageCreateRequest(
                channel="http",
                idempotency_key="publish-package-it",
                requested_by="integration-test",
                target_endpoint="https://publisher.example.test/v1/publish",
            ),
        )
        exported = delivery_repo.get_export(tenant_id, package.package_id)
        assert exported.manifest["contract_version"] == "airank.publish-snapshot.v2"
        assert exported.manifest["blueprint_sha256"] == asset.blueprint_sha256
        assert exported.manifest["generation_skill"] == {
            "skill_id": "intervention.page-blueprint",
            "version": "1.1.0",
        }
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_async_jobs SET priority = -1000
                    WHERE tenant_id = :tenant_id AND job_type = 'publish.package'
                    """
                ),
                {"tenant_id": tenant_id},
            )
        transport = FakeTransport()
        gateway = PublisherGateway(
            env={
                "AIRANK_PUBLISH_ALLOWED_HOSTS": "publisher.example.test",
                "AIRANK_PUBLISH_HTTP_BEARER_TOKEN": "integration-secret",
            },
            transport=transport,
            resolver=lambda host, port, **_: [(2, 1, 6, "", ("93.184.216.34", port))],
        )

        receipt = run_next_publish_job(
            job_store,
            execution_repo,
            gateway,
            worker_id="publisher-integration",
        )

        assert receipt is not None
        assert receipt.published_url == "https://publisher.example.test/pages/airank-proof"
        assert "integration-secret" not in repr(receipt)
        with engine.connect() as conn:
            package_row = conn.execute(
                text(
                    """
                    SELECT status, published_url, published_at, metadata_json
                    FROM airank_publish_packages
                    WHERE tenant_id = :tenant_id AND id = :package_id
                    """
                ),
                {"tenant_id": tenant_id, "package_id": package.package_id},
            ).mappings().one()
            attempt = conn.execute(
                text(
                    """
                    SELECT a.status, a.request_sha256, a.response_sha256,
                           a.response_status, a.operation_id,
                           o.state AS operation_state, o.idempotency_key_sha256
                    FROM airank_publish_attempts a
                    JOIN airank_operation_guards o ON o.id = a.operation_id
                    WHERE a.tenant_id = :tenant_id AND a.package_id = :package_id
                    """
                ),
                {"tenant_id": tenant_id, "package_id": package.package_id},
            ).mappings().one()
            retest_count = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM airank_retest_observation_windows
                    WHERE tenant_id = :tenant_id AND package_id = :package_id
                    """
                ),
                {"tenant_id": tenant_id, "package_id": package.package_id},
            ).scalar_one()
            operation_events = conn.execute(
                text(
                    """
                    SELECT event_sequence, event_type, previous_event_sha256, event_sha256
                    FROM airank_operation_guard_events
                    WHERE tenant_id = :tenant_id AND operation_id = :operation_id
                    ORDER BY event_sequence
                    """
                ),
                {"tenant_id": tenant_id, "operation_id": attempt["operation_id"]},
            ).mappings().all()
        assert package_row["status"] == "delivered"
        assert package_row["published_at"] is None
        assert attempt["status"] == "succeeded"
        assert len(attempt["request_sha256"]) == 64
        assert len(attempt["response_sha256"]) == 64
        assert int(attempt["response_status"]) == 201
        assert attempt["operation_state"] == "succeeded"
        assert attempt["idempotency_key_sha256"] != "publish-package-it"
        assert [row["event_type"] for row in operation_events] == [
            "operation_claimed",
            "external_effect_started",
            "operation_succeeded",
        ]
        assert operation_events[0]["previous_event_sha256"] is None
        assert operation_events[1]["previous_event_sha256"] == operation_events[0]["event_sha256"]
        assert operation_events[2]["previous_event_sha256"] == operation_events[1]["event_sha256"]
        listed_attempts = delivery_repo.list_attempts(tenant_id, package.package_id)
        assert listed_attempts[0].operation_state == "succeeded"
        assert listed_attempts[0].external_effect_started is True
        assert listed_attempts[0].reconciliation_required is False
        operation_detail = delivery_repo.get_operation(
            tenant_id,
            str(listed_attempts[0].operation_id),
        )
        assert operation_detail.replay_status == "available"
        assert [event.event_sequence for event in operation_detail.events] == [1, 2, 3]
        assert retest_count == 0
        assert "integration-secret" not in str(package_row["metadata_json"])
        assert transport.calls[0]["headers"]["Idempotency-Key"] == "publish-package-it"

        retry_package = delivery_repo.create_package(
            tenant_id,
            asset.asset_id,
            PublishPackageCreateRequest(
                channel="http",
                idempotency_key="publish-retry-package-it",
                requested_by="integration-test",
                target_endpoint="https://publisher.example.test/v1/publish",
            ),
        )
        with engine.begin() as conn:
            retry_job_id = conn.execute(
                text(
                    """
                    SELECT id FROM airank_async_jobs
                    WHERE tenant_id = :tenant_id AND job_type = 'publish.package'
                      AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.package_id')) = :package_id
                    """
                ),
                {"tenant_id": tenant_id, "package_id": retry_package.package_id},
            ).scalar_one()
            conn.execute(
                text("UPDATE airank_async_jobs SET priority = -1000 WHERE id = :id"),
                {"id": retry_job_id},
            )
        failing_gateway = PublisherGateway(
            env={
                "AIRANK_PUBLISH_ALLOWED_HOSTS": "publisher.example.test",
                "AIRANK_PUBLISH_HTTP_BEARER_TOKEN": "integration-secret",
            },
            transport=FailingTransport(),
            resolver=lambda host, port, **_: [(2, 1, 6, "", ("93.184.216.34", port))],
        )
        with pytest.raises(PublisherError) as failed_publish:
            run_next_publish_job(
                job_store,
                execution_repo,
                failing_gateway,
                worker_id="publisher-integration",
            )
        assert failed_publish.value.code == "OPERATION_OUTCOME_UNKNOWN"
        assert job_store.get(retry_job_id).status.value == "failed"

        job_store.requeue_for_retry(retry_job_id, datetime.now(timezone.utc))
        call_count_before_blocked_replay = len(transport.calls)
        with pytest.raises(PublisherError) as blocked_replay:
            run_next_publish_job(
                job_store,
                execution_repo,
                gateway,
                worker_id="publisher-integration-retry",
            )
        assert blocked_replay.value.code == "OPERATION_OUTCOME_UNKNOWN"
        assert len(transport.calls) == call_count_before_blocked_replay
        with engine.connect() as conn:
            retry_package_status = conn.execute(
                text(
                    """
                    SELECT status FROM airank_publish_packages
                    WHERE tenant_id = :tenant_id AND id = :package_id
                    """
                ),
                {"tenant_id": tenant_id, "package_id": retry_package.package_id},
            ).scalar_one()
            attempt_statuses = conn.execute(
                text(
                    """
                    SELECT status FROM airank_publish_attempts
                    WHERE tenant_id = :tenant_id AND package_id = :package_id
                    ORDER BY attempt_number
                    """
                ),
                {"tenant_id": tenant_id, "package_id": retry_package.package_id},
            ).scalars().all()
        assert retry_package_status == "outcome_unknown"
        assert attempt_statuses == ["outcome_unknown"]

        stale_package = delivery_repo.create_package(
            tenant_id,
            asset.asset_id,
            PublishPackageCreateRequest(
                channel="http",
                idempotency_key="publish-stale-package-it",
                requested_by="integration-test",
                target_endpoint="https://publisher.example.test/v1/publish",
            ),
        )
        stale_snapshot = execution_repo.load_snapshot(tenant_id, stale_package.package_id)
        stale_request_sha256 = gateway.request_sha256(stale_snapshot)
        stale_claim = execution_repo.operation_guard.claim(
            tenant_id=tenant_id,
            operation_type="publisher.publish",
            resource_key=stale_package.package_id,
            idempotency_key=stale_snapshot.idempotency_key,
            request_sha256=stale_request_sha256,
            request_key_id=None,
            actor="publisher-stale-setup",
            trace_id="job-stale-setup",
        )
        execution_repo.begin_attempt(
            stale_snapshot,
            stale_request_sha256,
            stale_claim.operation_id,
            datetime.now(timezone.utc) - timedelta(seconds=700),
        )
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_async_jobs SET priority = -1000
                    WHERE tenant_id = :tenant_id AND job_type = 'publish.package'
                      AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.package_id')) = :package_id
                    """
                ),
                {"tenant_id": tenant_id, "package_id": stale_package.package_id},
            )
        with pytest.raises(PublisherError) as stale_blocked:
            run_next_publish_job(
                job_store,
                execution_repo,
                gateway,
                worker_id="publisher-stale-recovery",
            )
        assert stale_blocked.value.code == "PUBLISH_ATTEMPT_ABANDONED_BEFORE_EXTERNAL"
        with engine.connect() as conn:
            stale_attempts = conn.execute(
                text(
                    """
                    SELECT status, error_code FROM airank_publish_attempts
                    WHERE tenant_id = :tenant_id AND package_id = :package_id
                    ORDER BY attempt_number
                    """
                ),
                {"tenant_id": tenant_id, "package_id": stale_package.package_id},
            ).mappings().all()
        assert [row["status"] for row in stale_attempts] == ["failed"]
        assert stale_attempts[0]["error_code"] == "PUBLISH_ATTEMPT_ABANDONED_BEFORE_EXTERNAL"

        wordpress_package = delivery_repo.create_package(
            tenant_id,
            asset.asset_id,
            PublishPackageCreateRequest(
                channel="wordpress",
                idempotency_key="publish-wordpress-reconcile-it",
                requested_by="integration-test",
                target_endpoint="https://publisher.example.test/wp-json/wp/v2/posts",
            ),
        )
        with engine.begin() as conn:
            wordpress_job_id = conn.execute(
                text(
                    """
                    SELECT id FROM airank_async_jobs
                    WHERE tenant_id = :tenant_id AND job_type = 'publish.package'
                      AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.package_id')) = :package_id
                    """
                ),
                {"tenant_id": tenant_id, "package_id": wordpress_package.package_id},
            ).scalar_one()
            conn.execute(
                text("UPDATE airank_async_jobs SET priority = -1000 WHERE id = :id"),
                {"id": wordpress_job_id},
            )

        class WordPressLostResponseTransport:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def request(self, method, url, *, headers, payload, timeout_seconds):
                del url, headers, payload, timeout_seconds
                self.calls.append(method)
                if method == "GET":
                    return 200, {}, []
                raise PublisherError(
                    "PUBLISH_NETWORK_FAILED",
                    "simulated response loss after WordPress accepted the request",
                    retryable=True,
                )

        lost_response_transport = WordPressLostResponseTransport()
        wordpress_gateway = PublisherGateway(
            env={
                "AIRANK_PUBLISH_ALLOWED_HOSTS": "publisher.example.test",
                "AIRANK_WORDPRESS_USERNAME": "integration-publisher",
                "AIRANK_WORDPRESS_APP_PASSWORD": "integration-app-password",
            },
            transport=lost_response_transport,
            resolver=lambda host, port, **_: [(2, 1, 6, "", ("93.184.216.34", port))],
        )
        with pytest.raises(PublisherError) as wordpress_unknown:
            run_next_publish_job(
                job_store,
                execution_repo,
                wordpress_gateway,
                worker_id="publisher-wordpress-lost-response",
            )
        assert wordpress_unknown.value.code == "OPERATION_OUTCOME_UNKNOWN"
        assert lost_response_transport.calls == ["GET", "POST"]

        class WordPressReconciliationTransport:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def request(self, method, url, *, headers, payload, timeout_seconds):
                del url, headers, payload, timeout_seconds
                self.calls.append(method)
                return 200, {}, [
                    {
                        "id": "wordpress_remote_it",
                        "link": "https://publisher.example.test/pages/airank-proof",
                    }
                ]

        reconciliation_transport = WordPressReconciliationTransport()
        reconciliation_gateway = PublisherGateway(
            env={
                "AIRANK_PUBLISH_ALLOWED_HOSTS": "publisher.example.test",
                "AIRANK_WORDPRESS_USERNAME": "integration-publisher",
                "AIRANK_WORDPRESS_APP_PASSWORD": "integration-app-password",
            },
            transport=reconciliation_transport,
            resolver=lambda host, port, **_: [(2, 1, 6, "", ("93.184.216.34", port))],
        )
        job_store.requeue_for_retry(wordpress_job_id, datetime.now(timezone.utc))
        wordpress_recovered = run_next_publish_job(
            job_store,
            execution_repo,
            reconciliation_gateway,
            worker_id="publisher-wordpress-reconciliation",
        )
        assert wordpress_recovered is not None
        assert wordpress_recovered.idempotent_replay is True
        assert reconciliation_transport.calls == ["GET"]
        with engine.connect() as conn:
            wordpress_attempt = conn.execute(
                text(
                    """
                    SELECT a.status, a.operation_id, o.state AS operation_state,
                           o.external_effect_started
                    FROM airank_publish_attempts a
                    JOIN airank_operation_guards o ON o.id = a.operation_id
                    WHERE a.tenant_id = :tenant_id AND a.package_id = :package_id
                    """
                ),
                {"tenant_id": tenant_id, "package_id": wordpress_package.package_id},
            ).mappings().one()
        assert wordpress_attempt["status"] == "succeeded"
        assert wordpress_attempt["operation_state"] == "succeeded"
        assert bool(wordpress_attempt["external_effect_started"]) is True

        screenshot_bytes = b"immutable publication screenshot"
        screenshot_sha256 = hashlib.sha256(screenshot_bytes).hexdigest()
        baseline_run_id = f"run_publish_baseline_{uuid4().hex[:8]}"
        manual_run_id = f"run_publish_manual_{uuid4().hex[:8]}"
        screenshot_ref_id = f"object_publish_{uuid4().hex[:8]}"
        completed_at = datetime.now(timezone.utc)
        with engine.begin() as conn:
            for run_id, run_type in ((baseline_run_id, "baseline"), (manual_run_id, "manual")):
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_scan_runs (
                          id, tenant_id, project_id, name, run_type, status,
                          finished_at, created_by, created_at, updated_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :name, :run_type, 'completed',
                          :finished_at, 'integration-test', :created_at, :created_at
                        )
                        """
                    ),
                    {
                        "id": run_id,
                        "tenant_id": tenant_id,
                        "project_id": project.project_id,
                        "name": f"publication {run_type}",
                        "run_type": run_type,
                        "finished_at": completed_at,
                        "created_at": completed_at,
                    },
                )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_object_refs (
                      id, tenant_id, project_id, object_type, object_uri,
                      content_type, byte_size, sha256, metadata_json, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, 'publication_screenshot', :object_uri,
                      'image/png', :byte_size, :sha256, JSON_OBJECT('immutable', TRUE), :created_at
                    )
                    """
                ),
                {
                    "id": screenshot_ref_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "object_uri": f"memory://publication/{screenshot_ref_id}.png",
                    "byte_size": len(screenshot_bytes),
                    "sha256": screenshot_sha256,
                    "created_at": completed_at,
                },
            )

        with pytest.raises(StarletteHTTPException) as non_baseline:
            delivery_repo.mark_published(
                tenant_id,
                package.package_id,
                PublishEvidenceRequest(
                    published_url=receipt.published_url,
                    baseline_run_id=manual_run_id,
                    recorded_by="integration-reviewer",
                ),
            )
        assert non_baseline.value.detail["code"] == "RETEST_BASELINE_REQUIRED"

        with pytest.raises(StarletteHTTPException) as mismatched_screenshot:
            delivery_repo.mark_published(
                tenant_id,
                package.package_id,
                PublishEvidenceRequest(
                    published_url=receipt.published_url,
                    baseline_run_id=baseline_run_id,
                    recorded_by="integration-reviewer",
                    screenshot_ref_id=screenshot_ref_id,
                    screenshot_sha256="0" * 64,
                ),
            )
        assert mismatched_screenshot.value.detail["code"] == "PUBLICATION_SCREENSHOT_EVIDENCE_INVALID"

        published = delivery_repo.mark_published(
            tenant_id,
            package.package_id,
            PublishEvidenceRequest(
                published_url=receipt.published_url,
                baseline_run_id=baseline_run_id,
                recorded_by="integration-reviewer",
                screenshot_ref_id=screenshot_ref_id,
                screenshot_sha256=screenshot_sha256,
            ),
        )
        assert published.status == "published"
        with engine.connect() as conn:
            observation_windows = conn.execute(
                text(
                    """
                    SELECT window_label, baseline_run_id, status
                    FROM airank_retest_observation_windows
                    WHERE tenant_id=:tenant_id AND package_id=:package_id
                    ORDER BY due_at, window_label
                    """
                ),
                {"tenant_id": tenant_id, "package_id": package.package_id},
            ).mappings().all()
            published_metadata = conn.execute(
                text(
                    """
                    SELECT metadata_json FROM airank_publish_packages
                    WHERE tenant_id=:tenant_id AND id=:package_id
                    """
                ),
                {"tenant_id": tenant_id, "package_id": package.package_id},
            ).scalar_one()
        if isinstance(published_metadata, str):
            published_metadata = json.loads(published_metadata)
        assert {row["window_label"] for row in observation_windows} == {"T0", "T+7", "T+14", "T+30"}
        assert all(row["baseline_run_id"] == baseline_run_id for row in observation_windows)
        assert published_metadata["publication_evidence"]["screenshot_ref_id"] == screenshot_ref_id
        assert published_metadata["publication_evidence"]["screenshot_sha256"] == screenshot_sha256
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_yudao_login_permission_and_capability_probe() -> None:
    require_real_flag("AIRANK_RUN_REAL_YUDAO")
    base_url = os.getenv("YUDAO_BASE_URL", "http://127.0.0.1:48080").rstrip("/")
    tenant_id = os.getenv("YUDAO_TENANT_ID", "1")
    username = os.getenv("YUDAO_USERNAME")
    password = os.getenv("YUDAO_PASSWORD")
    assert username, "YUDAO_USERNAME is required when AIRANK_RUN_REAL_YUDAO=1"
    assert password, "YUDAO_PASSWORD is required when AIRANK_RUN_REAL_YUDAO=1"

    login_payload = request_json(
        f"{base_url}/admin-api/system/auth/login",
        method="POST",
        headers={"Content-Type": "application/json", "tenant-id": tenant_id},
        body={"username": username, "password": password},
    )
    assert login_payload["code"] == 0
    token = extract_yudao_token(login_payload)
    assert token

    permission_payload = request_json(
        f"{base_url}/admin-api/system/auth/get-permission-info",
        headers={"Authorization": f"Bearer {token}", "tenant-id": tenant_id},
    )
    assert permission_payload["code"] == 0
    assert isinstance(permission_payload.get("data"), dict)
    assert permission_payload["data"].get("user")

    config = replace(
        ProbeConfig.from_env(
            {
                "AIRANK_AUTH_MODE": "yudao",
                "YUDAO_BASE_URL": base_url,
                "YUDAO_BEARER_TOKEN": token,
                "YUDAO_TENANT_ID": tenant_id,
                "AIRANK_OBJECT_STORAGE_DRIVER": "local",
                "AIRANK_OBJECT_STORAGE_ROOT": ".runtime/objects",
            }
        ),
        timeout_seconds=5,
    )
    results = {result.capability: result for result in CapabilityProbe(config).run()}

    assert results["yudao_auth"].status == CapabilityStatus.READY
    assert results["yudao_tenant_user"].status == CapabilityStatus.READY
    assert results["yudao_auth"].metadata["http_status"] == "200"


def test_real_mysql_independent_evidence_review_agreement_and_adjudication() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_review_quality_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    scan_repo = MySQLScanRepository(database_url())
    citation_repo = MySQLCitationSupportRepository(database_url())
    review_repo = MySQLEvidenceReviewRepository(database_url())
    routing_repo = MySQLReviewerRoutingRepository(database_url())
    knowledge_repo = MySQLKnowledgeRepository(database_url())

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://airank-review-quality.example.com",
                brand_name_hint="AIRank Review Quality",
                industry_hint="B2B SaaS",
            ),
        )
        question = project_repo.create_buyer_question(
            tenant_id,
            project.project_id,
            BuyerQuestionCreateRequest(
                question_text="AIRank 的证据结论如何保证复核质量？",
                status="confirmed",
                recommended_providers=["qianwen"],
            ),
        )
        run = scan_repo.create_run(
            tenant_id,
            ScanRunCreateRequest(
                project_id=project.project_id,
                name="Independent evidence review integration",
                repetitions=3,
                collector_surfaces=["api"],
                provider_scope=["qianwen"],
                question_scope={"mode": "selected", "question_ids": [question.question_id]},
            ),
        )
        task = scan_repo.list_tasks(tenant_id, run.run_id)[0]
        snapshot_id = f"snapshot_review_{uuid4().hex[:12]}"
        citation_id = f"citation_review_{uuid4().hex[:12]}"
        capture_id = f"capture_review_{uuid4().hex[:12]}"
        segment_id = f"segment_review_{uuid4().hex[:12]}"
        object_id = f"object_review_{uuid4().hex[:12]}"
        capture_job_id = f"job_review_{uuid4().hex[:12]}"
        answer_text = "AIRank 支持独立双人证据复核。"
        source_text = "AIRank 支持独立双人证据复核。所有结论保留审核历史。"
        captured_at = datetime.now(timezone.utc)
        answer_sha256 = sha256_text(answer_text)
        source_sha256 = sha256_text(source_text)

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO airank_answer_snapshots (
                      id, tenant_id, project_id, run_id, task_id, question_id,
                      provider, cohort_type, prompt_version_id, sample_index,
                      session_id, collector_surface, evidence_level, sample_status,
                      answer_text, answer_sha256, raw_response_sha256,
                      brand_mentioned, brand_rank, mention_class,
                      target_entity_mentions_json, competitor_mentions_json,
                      sentiment, confidence, model_name, search_enabled,
                      external_trace_id, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :run_id, :task_id, :question_id,
                      'qianwen', :cohort_type, :prompt_version_id, :sample_index,
                      :session_id, 'api', 'provider_api_search_unverified', 'valid',
                      :answer_text, :answer_sha256, :raw_response_sha256,
                      1, 1, 'recommended', JSON_ARRAY('AIRank'), JSON_ARRAY(),
                      'positive', NULL, 'qwen-review-fixture', 0,
                      'integration-review-request', :created_at
                    )
                    """
                ),
                {
                    "id": snapshot_id,
                    "tenant_id": tenant_id,
                    "project_id": project.project_id,
                    "run_id": run.run_id,
                    "task_id": task.task_id,
                    "question_id": task.question_id,
                    "cohort_type": task.cohort_type,
                    "prompt_version_id": task.prompt_version_id,
                    "sample_index": task.sample_index,
                    "session_id": task.session_id,
                    "answer_text": answer_text,
                    "answer_sha256": answer_sha256,
                    "raw_response_sha256": "a" * 64,
                    "created_at": captured_at,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_source_citations (
                      id, tenant_id, project_id, snapshot_id, citation_order,
                      title, url, host, source_type, cited_text, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :snapshot_id, 1,
                      '独立复核说明', 'https://evidence.example.com/review-quality',
                      'evidence.example.com', 'provider_native', :cited_text, :created_at
                    )
                    """
                ),
                {"id": citation_id, "tenant_id": tenant_id, "project_id": project.project_id, "snapshot_id": snapshot_id, "cited_text": source_text, "created_at": captured_at},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_async_jobs (
                      id, tenant_id, project_id, job_type, status,
                      payload_json, created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, 'citation.capture', 'completed',
                      JSON_OBJECT('integration_test', TRUE), :created_at, :created_at
                    )
                    """
                ),
                {"id": capture_job_id, "tenant_id": tenant_id, "project_id": project.project_id, "created_at": captured_at},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_object_refs (
                      id, tenant_id, project_id, object_type, object_uri,
                      content_type, byte_size, sha256, metadata_json, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, 'citation_source_page',
                      :object_uri, 'text/html', :byte_size, :sha256,
                      :metadata_json, :created_at
                    )
                    """
                ),
                {"id": object_id, "tenant_id": tenant_id, "project_id": project.project_id, "object_uri": f"local://review-quality/{object_id}", "byte_size": len(source_text.encode("utf-8")), "sha256": source_sha256, "metadata_json": json.dumps({"kind": "citation_source_page", "citation_id": citation_id, "capture_id": capture_id}, ensure_ascii=False), "created_at": captured_at},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_citation_source_captures (
                      id, tenant_id, project_id, citation_id, job_id,
                      idempotency_key, request_sha256, requested_url, final_url,
                      status, capture_version, evidence_grade, response_status,
                      content_type, response_bytes, content_sha256,
                      visible_text_sha256, raw_object_ref_id, connected_ip,
                      redirect_count, requested_by, started_at, completed_at,
                      created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :citation_id, :job_id,
                      :idempotency_key, :request_sha256, :url, :url,
                      'completed', 'airank.citation-source-capture.v1',
                      'source_page_dns_pinned', 200, 'text/html', :response_bytes,
                      :content_sha256, :content_sha256, :raw_object_ref_id,
                      '93.184.216.34', 0, 'integration-capture', :at, :at, :at, :at
                    )
                    """
                ),
                {"id": capture_id, "tenant_id": tenant_id, "project_id": project.project_id, "citation_id": citation_id, "job_id": capture_job_id, "idempotency_key": f"capture-{uuid4().hex}", "request_sha256": "b" * 64, "url": "https://evidence.example.com/review-quality", "response_bytes": len(source_text.encode("utf-8")), "content_sha256": source_sha256, "raw_object_ref_id": object_id, "at": captured_at},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_citation_source_segments (
                      id, tenant_id, project_id, capture_id, segment_index,
                      source_start, source_end, segment_text, segment_sha256, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :capture_id, 0,
                      0, :source_end, :segment_text, :segment_sha256, :created_at
                    )
                    """
                ),
                {"id": segment_id, "tenant_id": tenant_id, "project_id": project.project_id, "capture_id": capture_id, "source_end": len(source_text), "segment_text": source_text, "segment_sha256": source_sha256, "created_at": captured_at},
            )

        citation_claim = citation_repo.create_claim(
            tenant_id,
            snapshot_id,
            CitationClaimCreateRequest(
                answer_start=0,
                answer_end=len(answer_text),
                extraction_method="manual",
                claim_kind="unclassified",
                created_by="integration-claim-reviewer",
            ),
        )
        citation_case = review_repo.create_citation_case(
            tenant_id,
            project.project_id,
            CitationReviewCaseCreateRequest(
                claim_id=citation_claim.claim_id,
                purpose="benchmark",
                review=CitationSupportReviewCreateRequest(
                    citation_id=citation_id,
                    support_label="supports",
                    evidence_grade="source_page_snapshot",
                    source_excerpt=source_text,
                    source_content_sha256=source_sha256,
                    source_object_ref_id=object_id,
                    source_capture_id=capture_id,
                    source_segment_id=segment_id,
                    source_start=0,
                    source_end=len(source_text),
                    rationale="第一审核人独立核对不可变来源页面。",
                    review_method="human",
                    reviewed_by="reviewer-1",
                ),
            ),
            "mysql-citation-review-case",
            "reviewer-1",
            "trace-review-primary",
        )
        assert citation_case.status == "awaiting_secondary"
        routing = routing_repo.create_team(
            tenant_id,
            project.project_id,
            ReviewerTeamCreateRequest(name="Integration evidence reviewers"),
            "mysql-review-team",
            "review-admin",
            "trace-review-team",
        )
        review_team_id = routing.teams[0].team_id
        binding_routing = routing_repo.put_sync_binding(
            tenant_id,
            project.project_id,
            review_team_id,
            "secondary",
            ReviewerDirectoryBindingPutRequest(
                external_group_id="42",
                sync_interval_minutes=60,
                default_max_active_assignments=2,
            ),
            "review-admin",
            "trace-review-yudao-binding",
        )
        assert binding_routing.external_sync_state == "pending"
        assert binding_routing.sync_bindings[0].external_group_id == "42"

        directory_snapshot = YudaoReviewerDirectorySnapshot(
            department_id="42",
            department_name="Evidence reviewers",
            members=(
                YudaoReviewer(
                    user_id="reviewer-2",
                    username="reviewer.two",
                    display_name="Reviewer Two",
                    department_id="42",
                    enabled=True,
                ),
                YudaoReviewer(
                    user_id="reviewer-3",
                    username="reviewer.three",
                    display_name="Reviewer Three",
                    department_id="42",
                    enabled=True,
                ),
            ),
            response_sha256="c" * 64,
            endpoint_host="yudao.integration.invalid",
        )

        class FakeReviewerDirectoryClient:
            @staticmethod
            def fetch_department(department_id: str) -> YudaoReviewerDirectorySnapshot:
                assert department_id == "42"
                return directory_snapshot

        synced_routing = routing_repo.run_directory_sync(
            tenant_id,
            project.project_id,
            review_team_id,
            "secondary",
            "mysql-review-directory-sync-1",
            "review-admin",
            "trace-review-yudao-sync-1",
            FakeReviewerDirectoryClient(),  # type: ignore[arg-type]
        )
        assert synced_routing.external_sync_state == "verified"
        assert synced_routing.recent_sync_runs[0].status == "succeeded"
        assert synced_routing.recent_sync_runs[0].upserted_member_count == 2
        secondary_versions = {
            member.user_id: member.version
            for member in synced_routing.teams[0].members
            if member.reviewer_role == "secondary"
        }
        unchanged_routing = routing_repo.run_directory_sync(
            tenant_id,
            project.project_id,
            review_team_id,
            "secondary",
            "mysql-review-directory-sync-2",
            "review-admin",
            "trace-review-yudao-sync-2",
            FakeReviewerDirectoryClient(),  # type: ignore[arg-type]
        )
        assert unchanged_routing.recent_sync_runs[0].upserted_member_count == 0
        assert {
            member.user_id: member.version
            for member in unchanged_routing.teams[0].members
            if member.reviewer_role == "secondary"
        } == secondary_versions
        replayed_routing = routing_repo.run_directory_sync(
            tenant_id,
            project.project_id,
            review_team_id,
            "secondary",
            "mysql-review-directory-sync-2",
            "review-admin",
            "trace-review-yudao-sync-replay",
            FakeReviewerDirectoryClient(),  # type: ignore[arg-type]
        )
        assert len(replayed_routing.recent_sync_runs) == 2
        assert replayed_routing.recent_sync_runs[0].idempotent_replay is True
        directory_due_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE airank_evidence_review_team_sync_bindings "
                    "SET next_sync_at=:due_at WHERE tenant_id=:tenant_id AND id=:binding_id"
                ),
                {
                    "due_at": directory_due_at,
                    "tenant_id": tenant_id,
                    "binding_id": replayed_routing.sync_bindings[0].binding_id,
                },
            )
        directory_scheduler = MySQLReviewerDirectorySyncScheduler(
            database_url(),
            tenant_id=tenant_id,
            project_id=project.project_id,
            scheduler_id="integration-review-directory-scheduler",
        )
        assert directory_scheduler.preview().due_binding_count == 1
        scheduled_directory_jobs = directory_scheduler.dispatch_due(limit=10)
        assert len(scheduled_directory_jobs) == 1
        directory_job = scheduled_directory_jobs[0]
        directory_outcome = run_next_reviewer_directory_sync_job(
            MySQLJobLeaseStore(
                database_url(),
                tenant_id=tenant_id,
                project_id=project.project_id,
                job_id=directory_job.job_id,
            ),
            routing_repo,
            FakeReviewerDirectoryClient(),  # type: ignore[arg-type]
            worker_id="integration-review-directory-worker",
        )
        assert directory_outcome is not None
        assert directory_outcome.status == "succeeded"
        assert directory_outcome.upserted_member_count == 0
        assert routing_repo.get_routing(
            tenant_id, project.project_id
        ).recent_sync_runs[0].run_id == directory_outcome.run_id
        routing_repo.upsert_member(
            tenant_id,
            project.project_id,
            review_team_id,
            "reviewer-3",
            "adjudicator",
            ReviewerTeamMemberUpsertRequest(max_active_assignments=2),
            "review-admin",
            "trace-review-member-adjudicator",
        )
        partial_routing = routing_repo.put_route(
            tenant_id,
            project.project_id,
            "secondary",
            ReviewerRoleRoutePutRequest(team_id=review_team_id),
            "review-admin",
            "trace-review-route-secondary",
        )
        assert partial_routing.routing_mode == "blocked"
        assert partial_routing.routes[0].routing_ready is True
        routing = routing_repo.put_route(
            tenant_id,
            project.project_id,
            "adjudicator",
            ReviewerRoleRoutePutRequest(team_id=review_team_id),
            "review-admin",
            "trace-review-route-adjudicator",
        )
        assert routing.routing_mode == "team_routed"
        assert routing.external_sync_state == "verified"
        assert all(route.routing_ready for route in routing.routes)
        assert all(
            member.external_membership_verified
            for team in routing.teams
            for member in team.members
            if member.reviewer_role == "secondary"
        )
        assert all(
            not member.external_membership_verified
            for team in routing.teams
            for member in team.members
            if member.reviewer_role == "adjudicator"
        )
        with engine.connect() as conn:
            assert conn.execute(
                text(
                    "SELECT COUNT(*) FROM airank_evidence_review_team_sync_runs "
                    "WHERE tenant_id=:tenant_id AND binding_id=:binding_id"
                ),
                {
                    "tenant_id": tenant_id,
                    "binding_id": routing.sync_bindings[0].binding_id,
                },
            ).scalar_one() == 3
            assert conn.execute(
                text(
                    "SELECT COUNT(*) FROM airank_audit_events "
                    "WHERE tenant_id=:tenant_id "
                    "AND event_type='evidence_review.yudao_sync_succeeded'"
                ),
                {"tenant_id": tenant_id},
            ).scalar_one() == 3
        escalation_at = datetime.now(timezone.utc)
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_evidence_review_cases
                    SET created_at=:created_at, updated_at=:created_at
                    WHERE tenant_id=:tenant_id AND id=:case_id
                    """
                ),
                {
                    "created_at": escalation_at - timedelta(days=2),
                    "tenant_id": tenant_id,
                    "case_id": citation_case.case_id,
                },
            )
        escalation_scheduler = MySQLReviewEscalationScheduler(
            database_url(),
            tenant_id=tenant_id,
            project_id=project.project_id,
            scheduler_id="integration-review-escalation",
        )
        escalation_preview = escalation_scheduler.preview(escalation_at)
        assert escalation_preview.overdue_case_count == 1
        assert escalation_preview.pending_event_count == 0
        assert escalation_preview.dispatchable_count == 1
        escalated = escalation_scheduler.dispatch_overdue(
            now=escalation_at, limit=10
        )
        assert len(escalated) == 1
        assert escalated[0].case_id == citation_case.case_id
        assert escalated[0].reviewer_role == "secondary"
        assert escalated[0].assignment_state == "unassigned"
        assert escalated[0].routing_state == "resolved"
        assert escalated[0].routing_team_id == review_team_id
        assert escalated[0].eligible_recipient_count == 2
        assert escalation_scheduler.dispatch_overdue(now=escalation_at, limit=10) == []
        escalation_list = MySQLEvidenceReviewEscalationRepository(
            database_url()
        ).list_escalations(tenant_id, project.project_id, None, 50)
        assert escalation_list.escalation_count == 1
        assert escalation_list.pending_count == 1
        assert escalation_list.escalations[0].external_delivery_verified is False
        assert escalation_list.escalations[0].routing_state == "resolved"
        assert escalation_list.escalations[0].eligible_recipient_count == 2
        with engine.connect() as conn:
            outbox_payload = conn.execute(
                text(
                    """
                    SELECT payload_json FROM airank_outbox_events
                    WHERE tenant_id=:tenant_id AND id=:event_id
                    """
                ),
                {"tenant_id": tenant_id, "event_id": escalated[0].event_id},
            ).scalar_one()
        if isinstance(outbox_payload, str):
            outbox_payload = json.loads(outbox_payload)
        assert outbox_payload["delivery_claim"] == "outbox_pending_not_delivered"
        assert outbox_payload["routing_state"] == "resolved"
        assert outbox_payload["routing_team_id"] == review_team_id
        assert outbox_payload["eligible_recipient_count"] == 2
        assert "assigned_to" not in outbox_payload
        assert "assignment_id" not in outbox_payload

        class FakeReviewNotificationHttpClient:
            @staticmethod
            def request(method: str, url: str, *, headers=None, body=None):
                assert method == "POST"
                assert url == "https://notify.integration.invalid/review"
                assert headers["Idempotency-Key"] == escalated[0].event_id
                assert b'"case_id"' in body
                return OutboundResponse(
                    status=202,
                    headers={"x-request-id": "integration-notification-receipt"},
                    body=b'{"accepted":true}',
                    final_url=url,
                    redirect_count=0,
                    connected_ip="93.184.216.34",
                )

        notification_receipt = run_next_review_notification(
            MySQLReviewNotificationRepository(
                database_url(),
                tenant_id=tenant_id,
                project_id=project.project_id,
            ),
            ReviewNotificationWebhookClient(
                ReviewNotificationConfig(
                    webhook_url="https://notify.integration.invalid/review",
                    bearer_token="integration-secret-not-persisted",
                ),
                http_client=FakeReviewNotificationHttpClient(),
            ),
            worker_id="integration-review-notification-worker",
        )
        assert notification_receipt is not None
        assert notification_receipt.status == "succeeded"
        delivered_escalation = MySQLEvidenceReviewEscalationRepository(
            database_url()
        ).list_escalations(tenant_id, project.project_id, None, 50).escalations[0]
        assert delivered_escalation.outbox_status == "published"
        assert delivered_escalation.external_delivery_verified is True
        assert delivered_escalation.delivery_channel == "webhook"
        assert delivered_escalation.delivery_attempt_count == 1
        assert delivered_escalation.provider_receipt_id == "integration-notification-receipt"
        assert delivered_escalation.delivery_response_status == 202
        assert delivered_escalation.delivery_response_sha256
        with engine.connect() as conn:
            persisted_notification = json.dumps(
                {
                    "delivery": dict(
                        conn.execute(
                            text(
                                "SELECT * FROM airank_notification_deliveries "
                                "WHERE tenant_id=:tenant_id AND outbox_event_id=:event_id"
                            ),
                            {"tenant_id": tenant_id, "event_id": escalated[0].event_id},
                        ).mappings().one()
                    ),
                    "receipt": dict(
                        conn.execute(
                            text(
                                "SELECT * FROM airank_notification_delivery_receipts "
                                "WHERE tenant_id=:tenant_id AND outbox_event_id=:event_id"
                            ),
                            {"tenant_id": tenant_id, "event_id": escalated[0].event_id},
                        ).mappings().one()
                    ),
                },
                default=str,
            )
        assert "integration-secret-not-persisted" not in persisted_notification

        with pytest.raises(StarletteHTTPException) as self_review:
            review_repo.submit_decision(
                tenant_id,
                citation_case.case_id,
                EvidenceReviewDecisionRequest(label="supports", rationale="不能自审。", reviewed_by="reviewer-1"),
                "reviewer-1",
                "trace-review-self",
            )
        assert self_review.value.detail["code"] == "EVIDENCE_REVIEW_SELF_REVIEW_FORBIDDEN"

        assert review_repo.list_inbox(
            tenant_id, project.project_id, "reviewer-outside", 12, None
        ).actionable_count == 0
        with pytest.raises(StarletteHTTPException) as outside_route:
            review_repo.claim_assignment(
                tenant_id,
                citation_case.case_id,
                EvidenceReviewAssignmentClaimRequest(
                    expected_case_version=citation_case.version
                ),
                "reviewer-outside",
                "trace-review-outside-route",
            )
        assert outside_route.value.detail["code"] == "EVIDENCE_REVIEW_ROUTING_FORBIDDEN"

        def attempt_claim(actor: str) -> tuple[str, Any, str | None]:
            try:
                return (
                    actor,
                    review_repo.claim_assignment(
                        tenant_id,
                        citation_case.case_id,
                        EvidenceReviewAssignmentClaimRequest(
                            expected_case_version=citation_case.version
                        ),
                        actor,
                        f"trace-review-claim-{actor}",
                    ),
                    None,
                )
            except StarletteHTTPException as exc:
                return actor, None, str(exc.detail["code"])

        with ThreadPoolExecutor(max_workers=2) as executor:
            claim_outcomes = list(
                executor.map(attempt_claim, ["reviewer-2", "reviewer-3"])
            )
        successful_claims = [item for item in claim_outcomes if item[1] is not None]
        failed_claims = [item for item in claim_outcomes if item[2] is not None]
        assert len(successful_claims) == 1
        assert len(failed_claims) == 1
        assert failed_claims[0][2] == "EVIDENCE_REVIEW_ASSIGNMENT_CONFLICT"
        winner_actor, claimed, _ = successful_claims[0]
        loser_actor = failed_claims[0][0]
        assert claimed.state == "assigned_to_me"
        assert claimed.owned_by_current_actor is True
        assert claimed.assignment_id
        assert claimed.version == 1
        assert review_repo.list_inbox(
            tenant_id, project.project_id, loser_actor, 12, None
        ).actionable_count == 0
        renewed = review_repo.heartbeat_assignment(
            tenant_id,
            claimed.assignment_id,
            EvidenceReviewAssignmentHeartbeatRequest(expected_version=claimed.version),
            winner_actor,
            "trace-review-heartbeat",
        )
        assert renewed.version == 2
        assert renewed.due_at == claimed.due_at
        released = review_repo.release_assignment(
            tenant_id,
            claimed.assignment_id,
            EvidenceReviewAssignmentReleaseRequest(
                expected_version=renewed.version,
                reason="integration release before reclaim",
            ),
            winner_actor,
            "trace-review-release",
        )
        assert released.state == "released"
        expiring = review_repo.claim_assignment(
            tenant_id,
            citation_case.case_id,
            EvidenceReviewAssignmentClaimRequest(
                expected_case_version=citation_case.version
            ),
            "reviewer-3",
            "trace-review-expiring-claim",
        )
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_evidence_review_assignments
                    SET lease_expires_at=:expired_at
                    WHERE tenant_id=:tenant_id AND id=:assignment_id
                    """
                ),
                {
                    "expired_at": datetime.now(timezone.utc) - timedelta(seconds=1),
                    "tenant_id": tenant_id,
                    "assignment_id": expiring.assignment_id,
                },
            )
        with pytest.raises(StarletteHTTPException) as lease_expired:
            review_repo.heartbeat_assignment(
                tenant_id,
                expiring.assignment_id,
                EvidenceReviewAssignmentHeartbeatRequest(
                    expected_version=expiring.version
                ),
                "reviewer-3",
                "trace-review-expired-heartbeat",
            )
        assert lease_expired.value.detail["code"] == "EVIDENCE_REVIEW_ASSIGNMENT_LEASE_EXPIRED"
        reclaimed = review_repo.claim_assignment(
            tenant_id,
            citation_case.case_id,
            EvidenceReviewAssignmentClaimRequest(
                expected_case_version=citation_case.version
            ),
            "reviewer-2",
            "trace-review-reclaim",
        )
        assert reclaimed.assignment_id != claimed.assignment_id

        disputed = review_repo.submit_decision(
            tenant_id,
            citation_case.case_id,
            EvidenceReviewDecisionRequest(label="contradicts", rationale="第二审核人独立判断为矛盾。", reviewed_by="reviewer-2"),
            "reviewer-2",
            "trace-review-secondary",
        )
        assert disputed.status == "disputed"
        adjudicated = review_repo.submit_decision(
            tenant_id,
            citation_case.case_id,
            EvidenceReviewDecisionRequest(label="supports", rationale="第三审核人依据精确原文裁决支持。", reviewed_by="reviewer-3"),
            "reviewer-3",
            "trace-review-adjudicator",
        )
        assert adjudicated.status == "adjudicated"
        assert adjudicated.consensus_label == "supports"
        citation_metrics = citation_repo.get_bundle(tenant_id, snapshot_id).metrics
        assert citation_metrics.commercially_verified_review_count == 0
        assert citation_metrics.citation_support_rate is None
        assert "benchmark_reviews_excluded_from_commercial_metrics" in citation_metrics.known_limitations

        fact_source = knowledge_repo.create_source(
            tenant_id,
            project.project_id,
            KnowledgeSourceCreateRequest(
                idempotency_key="review-quality-fact-source",
                source_type="official_website",
                title="AIRank 独立复核事实",
                content_text=source_text,
                source_uri="https://airank-review-quality.example.com/facts",
                authority_level="official",
                risk_level="low",
            ),
        )
        proposed = knowledge_repo.propose_fact(
            tenant_id,
            project.project_id,
            FactProposalRequest(
                title="独立双人复核能力",
                fact_text=answer_text,
                source_ids=[fact_source.source_id],
                risk_level="low",
                disclosure="public",
                created_by="integration-fact-author",
            ),
        )
        approved = knowledge_repo.review_revision(
            tenant_id,
            project.project_id,
            proposed.revision_id,
            FactRevisionReviewRequest(action="approved", reviewed_by="integration-fact-approver"),
        )
        assert approved.status == "approved"
        fact_claim = citation_repo.create_claim(
            tenant_id,
            snapshot_id,
            CitationClaimCreateRequest(
                answer_start=0,
                answer_end=len(answer_text),
                extraction_method="manual",
                claim_kind="brand_fact",
                subject_entity_text="AIRank",
                created_by="integration-fact-claim-reviewer",
            ),
        )
        fact_case = review_repo.create_fact_case(
            tenant_id,
            project.project_id,
            FactReviewCaseCreateRequest(
                claim_id=fact_claim.claim_id,
                purpose="production",
                review=FactAccuracyReviewCreateRequest(
                    verdict="accurate",
                    fact_revision_id=approved.revision_id,
                    rationale="第一审核人核对审核事实与精确来源边界。",
                    review_method="human",
                    reviewed_by="fact-reviewer-1",
                ),
            ),
            "mysql-fact-review-case",
            "fact-reviewer-1",
            "trace-fact-primary",
        )
        routing_repo.upsert_member(
            tenant_id,
            project.project_id,
            review_team_id,
            "fact-reviewer-2",
            "secondary",
            ReviewerTeamMemberUpsertRequest(max_active_assignments=2),
            "review-admin",
            "trace-review-member-fact-secondary",
        )
        before_fact = citation_repo.get_fact_accuracy_bundle(tenant_id, snapshot_id).metrics
        assert before_fact.fact_accuracy is None
        with pytest.raises(StarletteHTTPException) as invalid_frozen_label:
            review_repo.submit_decision(
                tenant_id,
                fact_case.case_id,
                EvidenceReviewDecisionRequest(
                    label="insufficient_evidence",
                    rationale="不得在冻结事实证据仍存在时改成无证据。",
                    reviewed_by="fact-reviewer-2",
                ),
                "fact-reviewer-2",
                "trace-fact-invalid-label",
            )
        assert invalid_frozen_label.value.detail["code"] == "EVIDENCE_REVIEW_LABEL_INVALID"
        assert (
            invalid_frozen_label.value.detail["details"]["reason"]
            == "label_conflicts_with_frozen_evidence"
        )
        fact_complete = review_repo.submit_decision(
            tenant_id,
            fact_case.case_id,
            EvidenceReviewDecisionRequest(label="accurate", rationale="第二审核人独立核验后同意。", reviewed_by="fact-reviewer-2"),
            "fact-reviewer-2",
            "trace-fact-secondary",
        )
        assert fact_complete.status == "agreed"
        after_fact = citation_repo.get_fact_accuracy_bundle(tenant_id, snapshot_id).metrics
        assert after_fact.commercially_verified_claim_count == 1
        assert after_fact.fact_accuracy == 1.0

        queue = review_repo.list_cases(
            tenant_id, project.project_id, snapshot_id, "quality-auditor"
        )
        assert queue.benchmark_quality.independently_reviewed_case_count == 1
        assert queue.benchmark_quality.disagreement_count == 1
        assert queue.benchmark_quality.adjudicated_count == 1
        assert queue.benchmark_quality.benchmark_ready is False
        assert queue.production_quality.finalized_case_count == 1

        with engine.connect() as conn:
            audit_types = set(
                conn.execute(
                    text("SELECT event_type FROM airank_audit_events WHERE tenant_id=:tenant_id AND entity_type='evidence_review_case'"),
                    {"tenant_id": tenant_id},
                ).scalars().all()
            )
            case_count = conn.execute(
                text("SELECT COUNT(*) FROM airank_evidence_review_cases WHERE tenant_id=:tenant_id"),
                {"tenant_id": tenant_id},
            ).scalar_one()
            assignment_rows = conn.execute(
                text(
                    """
                    SELECT id, status, assigned_to, reviewer_role
                    FROM airank_evidence_review_assignments
                    WHERE tenant_id=:tenant_id
                    ORDER BY assigned_at, id
                    """
                ),
                {"tenant_id": tenant_id},
            ).mappings().all()
            assignment_events = conn.execute(
                text(
                    """
                    SELECT event_type
                    FROM airank_evidence_review_assignment_events
                    WHERE tenant_id=:tenant_id
                    """
                ),
                {"tenant_id": tenant_id},
            ).scalars().all()
        assert case_count == 2
        assert {"evidence_review.case_created", "evidence_review.decision_submitted"} <= audit_types
        assignment_by_id = {str(row["id"]): row for row in assignment_rows}
        assert assignment_by_id[claimed.assignment_id]["status"] == "released"
        assert assignment_by_id[expiring.assignment_id]["status"] == "expired"
        assert assignment_by_id[reclaimed.assignment_id]["status"] == "completed"
        assert assignment_by_id[reclaimed.assignment_id]["assigned_to"] == "reviewer-2"
        assert assignment_by_id[reclaimed.assignment_id]["reviewer_role"] == "secondary"
        assert any(
            row["status"] == "completed" and row["reviewer_role"] == "adjudicator"
            for row in assignment_rows
        )
        assert {"claimed", "heartbeat", "released", "completed"} <= set(assignment_events)
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_opportunity_directory_scheduler_worker_chain() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_opportunity_directory_{uuid4().hex[:10]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    project_repo = MySQLProjectRepository(database_url())
    routing_repo = MySQLOpportunityActionRoutingRepository(database_url())
    directory_repo = MySQLOpportunityActionDirectoryRepository(database_url())

    class FakeActionDirectoryClient:
        @staticmethod
        def fetch_department(department_id: str) -> YudaoReviewerDirectorySnapshot:
            assert department_id == "42"
            return YudaoReviewerDirectorySnapshot(
                department_id="42",
                department_name="Opportunity delivery",
                members=(
                    YudaoReviewer(
                        user_id="directory-owner",
                        username="directory.owner",
                        display_name="Directory Owner",
                        department_id="42",
                        enabled=True,
                    ),
                    YudaoReviewer(
                        user_id="manual-owner",
                        username="manual.owner",
                        display_name="External Manual Owner",
                        department_id="42",
                        enabled=True,
                    ),
                ),
                response_sha256="e" * 64,
                endpoint_host="yudao.integration.invalid",
            )

    try:
        project = project_repo.create_project(
            tenant_id,
            ProjectCreateRequest(
                website_url="https://opportunity-directory.example.com",
                brand_name_hint="Opportunity Directory Integration",
                industry_hint="B2B SaaS",
            ),
        )
        routing = routing_repo.create_team(
            tenant_id,
            project.project_id,
            OpportunityActionTeamCreateRequest(name="Opportunity delivery"),
            "opportunity-directory-team",
            "opportunity-admin",
        )
        team_id = routing.teams[0].team_id
        routing_repo.upsert_member(
            tenant_id,
            project.project_id,
            team_id,
            "manual-owner",
            OpportunityActionMemberUpsertRequest(
                display_name="Manual Owner",
                priority=80,
                max_active_actions=3,
            ),
            "opportunity-admin",
        )
        pending = directory_repo.put_binding(
            tenant_id,
            project.project_id,
            team_id,
            OpportunityActionDirectoryBindingPutRequest(
                external_group_id="42",
                sync_interval_minutes=60,
                default_max_active_actions=2,
            ),
            "opportunity-admin",
            "trace-opportunity-directory-binding",
        )
        binding = pending.bindings[0]
        assert binding.last_sync_state == "pending"
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE airank_opportunity_action_team_sync_bindings "
                    "SET next_sync_at=:due_at WHERE tenant_id=:tenant_id AND id=:binding_id"
                ),
                {
                    "due_at": datetime.now(timezone.utc) - timedelta(seconds=1),
                    "tenant_id": tenant_id,
                    "binding_id": binding.binding_id,
                },
            )

        scheduler = MySQLOpportunityDirectorySyncScheduler(
            database_url(),
            tenant_id=tenant_id,
            project_id=project.project_id,
            scheduler_id="integration-opportunity-directory-scheduler",
        )
        assert scheduler.preview().due_binding_count == 1
        dispatched = scheduler.dispatch_due(limit=10)
        assert len(dispatched) == 1
        outcome = run_next_opportunity_directory_sync_job(
            MySQLJobLeaseStore(
                database_url(),
                tenant_id=tenant_id,
                project_id=project.project_id,
                job_id=dispatched[0].job_id,
            ),
            directory_repo,
            FakeActionDirectoryClient(),  # type: ignore[arg-type]
            worker_id="integration-opportunity-directory-worker",
        )
        assert outcome is not None
        assert outcome.status == "succeeded"
        assert outcome.created_member_count == 1
        assert outcome.manual_conflict_count == 1
        state = directory_repo.get_state(tenant_id, project.project_id)
        assert state.verified_team_count == 1
        assert state.recent_sync_runs[0].run_id == outcome.run_id
        routing = routing_repo.get_routing(tenant_id, project.project_id)
        team = routing.teams[0]
        assert team.external_sync_state == "verified"
        members = {member.user_id: member for member in team.members}
        assert members["manual-owner"].display_name == "Manual Owner"
        assert members["manual-owner"].membership_source == "manual"
        assert members["manual-owner"].external_membership_verified is False
        assert members["directory-owner"].membership_source == "yudao"
        assert members["directory-owner"].external_membership_verified is True
        with engine.connect() as conn:
            assert conn.execute(
                text(
                    "SELECT COUNT(*) FROM airank_async_jobs "
                    "WHERE tenant_id=:tenant_id AND id=:job_id "
                    "AND job_type='opportunity.directory.sync' AND status='succeeded'"
                ),
                {"tenant_id": tenant_id, "job_id": dispatched[0].job_id},
            ).scalar_one() == 1
            event_types = set(
                conn.execute(
                    text(
                        "SELECT event_type FROM airank_audit_events "
                        "WHERE tenant_id=:tenant_id AND entity_type IN ("
                        "'opportunity_action_team_sync_binding', "
                        "'opportunity_action_team_sync_run')"
                    ),
                    {"tenant_id": tenant_id},
                ).scalars()
            )
        assert {
            "opportunity_action.directory_binding_saved",
            "opportunity_action.directory_sync_dispatched",
            "opportunity_action.directory_sync_succeeded",
        } <= event_types
    finally:
        cleanup_tenant(engine, tenant_id)


def test_real_mysql_provider_model_migration_requires_target_l3_evidence_and_approval() -> None:
    require_real_flag("AIRANK_RUN_REAL_MYSQL")
    tenant_id = f"tenant_model_migration_{uuid4().hex[:8]}"
    engine = create_engine(database_url(), pool_pre_ping=True)
    route_env = {
        "DEEPSEEK_API_KEY": "integration-not-sent",
        "DEEPSEEK_API_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "DEEPSEEK_MODEL": "deepseek-v3.2",
        "DEEPSEEK_PROVIDER_DISABLED": "false",
    }
    route_operations = MySQLProviderOperations(database_url(), env=route_env)
    route_operations.sync_manifests([PROVIDER_MANIFESTS["deepseek"]])
    repository = MySQLProviderModelLifecycle(database_url())
    audit_id = f"pra_migration_{uuid4().hex}"
    try:
        with engine.connect() as conn:
            route = conn.execute(
                text(
                    "SELECT route_id,model_name,configuration_fingerprint "
                    "FROM airank_provider_routes WHERE provider_key='deepseek' "
                    "AND route_id='deepseek:default' AND is_current=1"
                )
            ).mappings().one()
        payload = ProviderModelMigrationCreateRequest(
            provider="deepseek",
            route_id=str(route["route_id"]),
            from_model=str(route["model_name"]),
            to_model="deepseek-v4-pro",
            from_configuration_fingerprint=str(route["configuration_fingerprint"]),
            reason="prepare verified migration before provider sunset",
        )
        def create_same_plan(index: int) -> dict[str, object]:
            return repository.create(
                tenant_id,
                payload,
                actor="provider_operator",
                trace_id=f"trc_model_migration_plan_{index}",
                idempotency_key="deepseek-v32-to-v4-plan",
            )

        with ThreadPoolExecutor(max_workers=4) as pool:
            concurrent_results = list(pool.map(create_same_plan, range(4)))
        assert len({str(item["migration_id"]) for item in concurrent_results}) == 1
        planned = concurrent_results[0]
        replay = repository.create(
            tenant_id,
            payload,
            actor="provider_operator",
            trace_id="trc_model_migration_replay",
            idempotency_key="deepseek-v32-to-v4-plan",
        )
        assert replay["migration_id"] == planned["migration_id"]
        assert len(planned["events"]) == 1
        with pytest.raises(ProviderModelMigrationError) as invalid_evidence:
            repository.bind_validation(
                tenant_id,
                str(planned["migration_id"]),
                ProviderModelMigrationValidateRequest(
                    request_audit_id="missing_target_l3_audit",
                    expected_version=1,
                    reason="reject missing target L3 evidence",
                ),
                actor="provider_operator",
                trace_id="trc_model_migration_invalid",
            )
        assert invalid_evidence.value.code == "PROVIDER_MODEL_MIGRATION_VALIDATION_FAILED"
        failed = repository.get(tenant_id, str(planned["migration_id"]))
        assert failed is not None
        assert failed["status"] == "validation_failed"
        assert failed["plan_version"] == 2

        requested_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=1)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO airank_provider_request_audits "
                    "(id,tenant_id,project_id,provider_key,route_id,model_name,endpoint_host,"
                    "configuration_fingerprint,provider_request_id,prompt_sha256,outcome,"
                    "attempt_count,duration_ms,requested_at,completed_at,created_at) VALUES "
                    "(:id,:tenant_id,'project_model_migration','deepseek','deepseek:default',"
                    "'deepseek-v4-pro','dashscope.aliyuncs.com',:fingerprint,:provider_request_id,"
                    ":prompt_sha256,'success',1,12,:requested_at,:completed_at,:created_at)"
                ),
                {
                    "id": audit_id,
                    "tenant_id": tenant_id,
                    "fingerprint": "c" * 64,
                    "provider_request_id": f"provider_request_{uuid4().hex}",
                    "prompt_sha256": "d" * 64,
                    "requested_at": requested_at,
                    "completed_at": requested_at + timedelta(milliseconds=12),
                    "created_at": requested_at,
                },
            )
        validated = repository.bind_validation(
            tenant_id,
            str(planned["migration_id"]),
            ProviderModelMigrationValidateRequest(
                request_audit_id=audit_id,
                expected_version=2,
                reason="bind successful target model L3 request audit",
            ),
            actor="provider_operator",
            trace_id="trc_model_migration_valid",
        )
        assert validated["status"] == "validated"
        assert validated["validation_provider_request_id_present"] is True
        approved = repository.approve(
            tenant_id,
            str(planned["migration_id"]),
            ProviderModelMigrationApproveRequest(
                expected_version=3,
                reason="approve migration backed by real L3 audit",
            ),
            actor="release_approver",
            trace_id="trc_model_migration_approve",
        )
        assert approved["status"] == "approved"
        assert approved["plan_version"] == 4
        assert approved["event_chain_status"] == "valid"
        assert approved["validation_evidence_status"] == "valid"
        assert approved["release_eligible"] is True
        events = approved["events"]
        assert [event["event_sequence"] for event in events] == [1, 2, 3, 4]
        assert [event["event_type"] for event in events] == [
            "migration_planned",
            "validation_rejected",
            "target_l3_validated",
            "migration_approved",
        ]
        assert all(
            events[index]["previous_event_sha256"] == events[index - 1]["event_sha256"]
            for index in range(1, len(events))
        )
        assert repository.list(f"other_{tenant_id}") == []
        deepseek_gate = next(
            gate
            for gate in repository.list_release_gates(
                tenant_id,
                now=datetime(2026, 8, 9, tzinfo=timezone.utc),
                execution_window_days=30,
                release_window_days=90,
            )
            if gate["provider"] == "deepseek"
        )
        assert deepseek_gate["migration_status"] == "approved"
        assert deepseek_gate["release_gate_status"] == "pass"
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE airank_provider_request_audits SET outcome='failed' "
                    "WHERE tenant_id=:tenant_id AND id=:audit_id"
                ),
                {"tenant_id": tenant_id, "audit_id": audit_id},
            )
        invalidated = repository.get(tenant_id, str(planned["migration_id"]))
        assert invalidated is not None
        assert invalidated["validation_evidence_status"] == "invalid"
        assert invalidated["release_eligible"] is False
        invalidated_gate = next(
            gate
            for gate in repository.list_release_gates(
                tenant_id,
                now=datetime(2026, 8, 9, tzinfo=timezone.utc),
                execution_window_days=30,
                release_window_days=90,
            )
            if gate["provider"] == "deepseek"
        )
        assert invalidated_gate["release_gate_status"] == "blocked"
    finally:
        cleanup_tenant(engine, tenant_id)


def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(url, data=payload, headers=headers or {}, method=method)
    try:
        with urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return json.loads(exc.read().decode("utf-8"))


def extract_yudao_token(payload: dict[str, Any]) -> str | None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    token = data.get("accessToken") or data.get("access_token") or data.get("token")
    return token if isinstance(token, str) else None


def utc_datetime() -> datetime:
    return datetime.now(timezone.utc)
