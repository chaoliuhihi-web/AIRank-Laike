from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import re
from typing import Any, Mapping
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from airank_provider_gateway import ProviderGatewayError


USAGE_PRECISIONS = {"exact", "estimated", "unknown"}
COST_PRECISIONS = {"exact", "estimated", "unknown"}
PRICE_SOURCE_KINDS = {
    "official_price_page",
    "provider_invoice",
    "customer_contract",
    "manual_verified",
}
MONEY_QUANTUM = Decimal("0.000000000001")
TOKENS_PER_PRICING_UNIT = Decimal("1000000")
SECRET_LIKE_PATTERN = re.compile(
    r"(?i)(?:api[_-]?key|authorization|bearer|secret|token)\s*[:=]|\bsk-[A-Za-z0-9_-]{12,}"
)


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_json(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def decimal_value(value: object | None, *, field: str) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ProviderGatewayError(
            "usage-ledger",
            "PROVIDER_PRICE_INVALID",
            f"{field} must be a decimal amount",
        ) from exc
    if not parsed.is_finite() or parsed < 0:
        raise ProviderGatewayError(
            "usage-ledger",
            "PROVIDER_PRICE_INVALID",
            f"{field} must be finite and non-negative",
        )
    return parsed


def decimal_text(value: object | None) -> str | None:
    if value is None:
        return None
    parsed = Decimal(str(value))
    return format(parsed, "f")


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def persist_provider_usage_event(
    conn: Any,
    *,
    tenant_id: str,
    project_id: str,
    request_audit_id: str,
    provider_key: str,
    model_name: str,
    usage: Mapping[str, Any],
    occurred_at: datetime | str,
) -> str:
    """Persist one immutable raw usage event and derive an auditable catalog cost.

    `cost_amount` on the raw event is reserved for an explicit Provider-billed
    amount. Catalog-calculated costs are appended to a separate derivation table.
    """

    precision = str(usage.get("precision") or "unknown")
    if precision not in USAGE_PRECISIONS:
        precision = "unknown"
    source = str(usage.get("source") or "missing")[:80]
    input_tokens = _non_negative_integer(usage.get("input_tokens"))
    output_tokens = _non_negative_integer(usage.get("output_tokens"))
    total_tokens = _non_negative_integer(usage.get("total_tokens"))
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens

    billed_cost = decimal_value(usage.get("cost_amount"), field="cost_amount")
    billed_currency = str(usage.get("cost_currency") or "").strip().upper() or None
    billed_precision = str(usage.get("cost_precision") or "unknown")
    billed_source = str(usage.get("cost_source") or "missing")[:80]
    if not (
        billed_cost is not None
        and billed_currency is not None
        and len(billed_currency) == 3
        and billed_precision == "exact"
        and billed_source == "provider_response_billed"
    ):
        billed_cost = None
        billed_currency = None
        billed_precision = "unknown"
        billed_source = "missing"

    raw_payload = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "precision": precision,
        "source": source,
        "cost_amount": decimal_text(billed_cost),
        "cost_currency": billed_currency,
        "cost_precision": billed_precision,
        "cost_source": billed_source,
    }
    event_id = f"provider_usage_{uuid4().hex[:12]}"
    conn.execute(
        text(
            """
            INSERT INTO airank_provider_usage_events (
              id, tenant_id, project_id, request_audit_id,
              provider_key, model_name, input_tokens, output_tokens,
              total_tokens, precision_status, usage_source,
              cost_amount, cost_currency, cost_precision_status, cost_source,
              raw_usage_sha256, occurred_at
            )
            VALUES (
              :id, :tenant_id, :project_id, :request_audit_id,
              :provider_key, :model_name, :input_tokens, :output_tokens,
              :total_tokens, :precision_status, :usage_source,
              :cost_amount, :cost_currency, :cost_precision_status, :cost_source,
              :raw_usage_sha256, :occurred_at
            )
            """
        ),
        {
            "id": event_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "request_audit_id": request_audit_id,
            "provider_key": provider_key,
            "model_name": model_name,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "precision_status": precision,
            "usage_source": source,
            "cost_amount": billed_cost,
            "cost_currency": billed_currency,
            "cost_precision_status": billed_precision,
            "cost_source": billed_source,
            "raw_usage_sha256": sha256_json(raw_payload),
            "occurred_at": occurred_at,
        },
    )
    if billed_cost is None:
        derive_catalog_cost(conn, event_id)
    return event_id


def _non_negative_integer(value: object | None) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    return None


def derive_catalog_cost(conn: Any, usage_event_id: str) -> str | None:
    usage = conn.execute(
        text(
            """
            SELECT u.id, u.tenant_id, u.provider_key, u.model_name,
                   u.input_tokens, u.output_tokens, u.precision_status,
                   u.cost_amount, u.cost_precision_status, u.occurred_at,
                   a.route_id
            FROM airank_provider_usage_events u
            JOIN airank_provider_request_audits a ON a.id=u.request_audit_id
            WHERE u.id=:usage_event_id
            """
        ),
        {"usage_event_id": usage_event_id},
    ).mappings().one_or_none()
    if usage is None or (
        usage["cost_amount"] is not None and str(usage["cost_precision_status"]) == "exact"
    ):
        return None
    if usage["input_tokens"] is None or usage["output_tokens"] is None:
        return None

    price = conn.execute(
        text(
            """
            SELECT id, catalog_version, currency, input_price_per_million,
                   output_price_per_million, source_kind, source_sha256
            FROM airank_provider_price_versions
            WHERE tenant_id=:tenant_id
              AND provider_key=:provider_key
              AND model_name=:model_name
              AND (route_id=:route_id OR route_id='*')
              AND effective_from <= :occurred_at
              AND (effective_until IS NULL OR effective_until > :occurred_at)
            ORDER BY (route_id=:route_id) DESC, effective_from DESC,
                     catalog_version DESC, created_at DESC
            LIMIT 1
            """
        ),
        {
            "tenant_id": usage["tenant_id"],
            "provider_key": usage["provider_key"],
            "model_name": usage["model_name"],
            "route_id": usage["route_id"] or "*",
            "occurred_at": usage["occurred_at"],
        },
    ).mappings().one_or_none()
    if price is None:
        return None

    input_rate = Decimal(str(price["input_price_per_million"]))
    output_rate = Decimal(str(price["output_price_per_million"]))
    input_cost = (
        Decimal(int(usage["input_tokens"])) * input_rate / TOKENS_PER_PRICING_UNIT
    ).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    output_cost = (
        Decimal(int(usage["output_tokens"])) * output_rate / TOKENS_PER_PRICING_UNIT
    ).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    total_cost = input_cost + output_cost
    contract = {
        "contract": "airank.provider-cost-calculation.v1",
        "usage_event_id": usage_event_id,
        "usage_precision": str(usage["precision_status"]),
        "input_tokens": int(usage["input_tokens"]),
        "output_tokens": int(usage["output_tokens"]),
        "pricing_unit": "per_1m_tokens",
        "input_price_per_million": decimal_text(input_rate),
        "output_price_per_million": decimal_text(output_rate),
        "price_version_id": str(price["id"]),
        "price_catalog_version": int(price["catalog_version"]),
        "price_source_kind": str(price["source_kind"]),
        "price_source_sha256": str(price["source_sha256"]),
        "cost_precision": "estimated",
    }
    calculation_sha256 = sha256_json(contract)
    existing = conn.execute(
        text(
            """
            SELECT id FROM airank_provider_usage_costs
            WHERE usage_event_id=:usage_event_id
              AND calculation_sha256=:calculation_sha256
            """
        ),
        {
            "usage_event_id": usage_event_id,
            "calculation_sha256": calculation_sha256,
        },
    ).scalar_one_or_none()
    if existing:
        return str(existing)

    derivation_id = f"usage_cost_{uuid4().hex[:12]}"
    conn.execute(
        text(
            """
            INSERT INTO airank_provider_usage_costs (
              id, tenant_id, usage_event_id, price_version_id,
              input_cost_amount, output_cost_amount, total_cost_amount,
              cost_currency, precision_status, cost_source,
              calculation_contract_json, calculation_sha256, created_at
            )
            VALUES (
              :id, :tenant_id, :usage_event_id, :price_version_id,
              :input_cost_amount, :output_cost_amount, :total_cost_amount,
              :cost_currency, 'estimated', 'catalog_calculated',
              :calculation_contract_json, :calculation_sha256, :created_at
            )
            """
        ),
        {
            "id": derivation_id,
            "tenant_id": usage["tenant_id"],
            "usage_event_id": usage_event_id,
            "price_version_id": price["id"],
            "input_cost_amount": input_cost,
            "output_cost_amount": output_cost,
            "total_cost_amount": total_cost,
            "cost_currency": price["currency"],
            "calculation_contract_json": canonical_json(contract),
            "calculation_sha256": calculation_sha256,
            "created_at": utc_now_naive(),
        },
    )
    return derivation_id


class MySQLProviderUsageLedger:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    def create_price_version(
        self,
        *,
        tenant_id: str,
        provider_key: str,
        route_id: str,
        model_name: str,
        currency: str,
        input_price_per_million: object,
        output_price_per_million: object,
        effective_from: datetime,
        effective_until: datetime | None,
        source_kind: str,
        source_reference: str,
        expected_previous_version: int,
        reason: str,
        created_by: str,
    ) -> dict[str, Any]:
        if source_kind not in PRICE_SOURCE_KINDS:
            raise ProviderGatewayError(
                provider_key,
                "PROVIDER_PRICE_INVALID",
                "unsupported price source kind",
            )
        if SECRET_LIKE_PATTERN.search(source_reference) or SECRET_LIKE_PATTERN.search(reason):
            raise ProviderGatewayError(
                provider_key,
                "PROVIDER_PRICE_INVALID",
                "price evidence fields must not contain credential material",
            )
        normalized_currency = currency.strip().upper()
        if len(normalized_currency) != 3 or not normalized_currency.isalpha():
            raise ProviderGatewayError(
                provider_key,
                "PROVIDER_PRICE_INVALID",
                "currency must be a three-letter code",
            )
        input_rate = decimal_value(input_price_per_million, field="input_price_per_million")
        output_rate = decimal_value(output_price_per_million, field="output_price_per_million")
        assert input_rate is not None and output_rate is not None
        start = normalize_datetime(effective_from)
        end = normalize_datetime(effective_until) if effective_until is not None else None
        if end is not None and end <= start:
            raise ProviderGatewayError(
                provider_key,
                "PROVIDER_PRICE_INVALID",
                "effective_until must be later than effective_from",
            )
        source_payload = {
            "contract": "airank.provider-price-version.v1",
            "tenant_id": tenant_id,
            "provider": provider_key,
            "route_id": route_id,
            "model": model_name,
            "currency": normalized_currency,
            "pricing_unit": "per_1m_tokens",
            "input_price_per_million": decimal_text(input_rate),
            "output_price_per_million": decimal_text(output_rate),
            "effective_from": start.isoformat(),
            "effective_until": end.isoformat() if end else None,
            "source_kind": source_kind,
            "source_reference": source_reference.strip(),
            "reason": reason.strip(),
        }
        source_sha256 = sha256_json(source_payload)
        now = utc_now_naive()
        with self.engine.begin() as conn:
            duplicate = conn.execute(
                text(
                    """
                    SELECT * FROM airank_provider_price_versions
                    WHERE tenant_id=:tenant_id AND source_sha256=:source_sha256
                    """
                ),
                {"tenant_id": tenant_id, "source_sha256": source_sha256},
            ).mappings().one_or_none()
            if duplicate is not None:
                result = self._price_record(duplicate)
                result["backfilled_usage_count"] = 0
                result["replay_status"] = "idempotent_replay"
                return result

            latest_row = conn.execute(
                text(
                    """
                    SELECT catalog_version
                    FROM airank_provider_price_versions
                    WHERE tenant_id=:tenant_id AND provider_key=:provider_key
                      AND route_id=:route_id AND model_name=:model_name
                    ORDER BY catalog_version DESC
                    LIMIT 1 FOR UPDATE
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "provider_key": provider_key,
                    "route_id": route_id,
                    "model_name": model_name,
                },
            ).scalar_one_or_none()
            latest_version = int(latest_row or 0)
            if latest_version != expected_previous_version:
                raise ProviderGatewayError(
                    provider_key,
                    "PROVIDER_PRICE_VERSION_CONFLICT",
                    f"expected previous version {expected_previous_version}, current is {latest_version}",
                )
            price_id = f"provider_price_{uuid4().hex[:12]}"
            version = latest_version + 1
            try:
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_provider_price_versions (
                          id, tenant_id, provider_key, route_id, model_name,
                          catalog_version, currency, pricing_unit,
                          input_price_per_million, output_price_per_million,
                          effective_from, effective_until, source_kind,
                          source_reference, source_sha256, reason, created_by, created_at
                        )
                        VALUES (
                          :id, :tenant_id, :provider_key, :route_id, :model_name,
                          :catalog_version, :currency, 'per_1m_tokens',
                          :input_price_per_million, :output_price_per_million,
                          :effective_from, :effective_until, :source_kind,
                          :source_reference, :source_sha256, :reason, :created_by, :created_at
                        )
                        """
                    ),
                    {
                        "id": price_id,
                        "tenant_id": tenant_id,
                        "provider_key": provider_key,
                        "route_id": route_id,
                        "model_name": model_name,
                        "catalog_version": version,
                        "currency": normalized_currency,
                        "input_price_per_million": input_rate,
                        "output_price_per_million": output_rate,
                        "effective_from": start,
                        "effective_until": end,
                        "source_kind": source_kind,
                        "source_reference": source_reference.strip(),
                        "source_sha256": source_sha256,
                        "reason": reason.strip(),
                        "created_by": created_by,
                        "created_at": now,
                    },
                )
            except IntegrityError as exc:
                raise ProviderGatewayError(
                    provider_key,
                    "PROVIDER_PRICE_VERSION_CONFLICT",
                    "price version changed concurrently; reload before appending",
                ) from exc
            usage_ids = conn.execute(
                text(
                    """
                    SELECT u.id
                    FROM airank_provider_usage_events u
                    JOIN airank_provider_request_audits a ON a.id=u.request_audit_id
                    WHERE u.tenant_id=:tenant_id
                      AND u.provider_key=:provider_key
                      AND u.model_name=:model_name
                      AND (:route_id='*' OR a.route_id=:route_id)
                      AND u.occurred_at >= :effective_from
                      AND (:effective_until IS NULL OR u.occurred_at < :effective_until)
                      AND NOT (u.cost_amount IS NOT NULL AND u.cost_precision_status='exact')
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "provider_key": provider_key,
                    "model_name": model_name,
                    "route_id": route_id,
                    "effective_from": start,
                    "effective_until": end,
                },
            ).scalars().all()
            backfilled = sum(1 for usage_id in usage_ids if derive_catalog_cost(conn, str(usage_id)))
            row = conn.execute(
                text("SELECT * FROM airank_provider_price_versions WHERE id=:id"),
                {"id": price_id},
            ).mappings().one()
            result = self._price_record(row)
            result["backfilled_usage_count"] = backfilled
            result["replay_status"] = "created"
            return result

    def list_price_versions(self, *, tenant_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM airank_provider_price_versions
                    WHERE tenant_id=:tenant_id
                    ORDER BY provider_key, route_id, model_name,
                             effective_from DESC, catalog_version DESC
                    """
                ),
                {"tenant_id": tenant_id},
            ).mappings().all()
        return [self._price_record(row) for row in rows]

    def list_usage(
        self,
        *,
        tenant_id: str,
        provider_key: str | None = None,
        project_id: str | None = None,
        usage_precision: str | None = None,
        cost_precision: str | None = None,
        occurred_from: datetime | None = None,
        occurred_until: datetime | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        clauses = ["u.tenant_id=:tenant_id"]
        params: dict[str, Any] = {"tenant_id": tenant_id, "limit": limit}
        if provider_key:
            clauses.append("u.provider_key=:provider_key")
            params["provider_key"] = provider_key
        if project_id:
            clauses.append("u.project_id=:project_id")
            params["project_id"] = project_id
        if usage_precision:
            clauses.append("u.precision_status=:usage_precision")
            params["usage_precision"] = usage_precision
        if occurred_from:
            clauses.append("u.occurred_at>=:occurred_from")
            params["occurred_from"] = normalize_datetime(occurred_from)
        if occurred_until:
            clauses.append("u.occurred_at<:occurred_until")
            params["occurred_until"] = normalize_datetime(occurred_until)

        effective_precision = (
            "CASE WHEN u.cost_amount IS NOT NULL AND u.cost_precision_status='exact' "
            "THEN 'exact' WHEN dc.id IS NOT NULL THEN dc.precision_status ELSE 'unknown' END"
        )
        if cost_precision:
            clauses.append(f"{effective_precision}=:cost_precision")
            params["cost_precision"] = cost_precision
        where_sql = " AND ".join(clauses)
        latest_cost_join = """
            LEFT JOIN airank_provider_usage_costs dc ON dc.id=(
              SELECT dc2.id FROM airank_provider_usage_costs dc2
              WHERE dc2.usage_event_id=u.id
              ORDER BY dc2.created_at DESC, dc2.id DESC LIMIT 1
            )
        """
        fields = f"""
            u.id, u.project_id, u.request_audit_id, u.provider_key, a.route_id,
            u.model_name, u.input_tokens, u.output_tokens, u.total_tokens,
            u.precision_status, u.usage_source, u.raw_usage_sha256,
            a.outcome, a.provider_request_id,
            CASE WHEN u.cost_amount IS NOT NULL AND u.cost_precision_status='exact'
                 THEN u.cost_amount ELSE dc.total_cost_amount END AS effective_cost_amount,
            CASE WHEN u.cost_amount IS NOT NULL AND u.cost_precision_status='exact'
                 THEN u.cost_currency ELSE dc.cost_currency END AS effective_cost_currency,
            {effective_precision} AS effective_cost_precision,
            CASE WHEN u.cost_amount IS NOT NULL AND u.cost_precision_status='exact'
                 THEN u.cost_source WHEN dc.id IS NOT NULL THEN dc.cost_source ELSE 'missing' END
                 AS effective_cost_source,
            dc.price_version_id, dc.calculation_sha256,
            u.occurred_at, u.created_at
        """
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT {fields}
                    FROM airank_provider_usage_events u
                    JOIN airank_provider_request_audits a ON a.id=u.request_audit_id
                    {latest_cost_join}
                    WHERE {where_sql}
                    ORDER BY u.occurred_at DESC, u.id DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
            summary_row = conn.execute(
                text(
                    f"""
                    SELECT COUNT(*) AS event_count,
                           SUM(u.precision_status='exact') AS exact_usage_count,
                           SUM(u.precision_status='estimated') AS estimated_usage_count,
                           SUM(u.precision_status='unknown') AS unknown_usage_count,
                           SUM(({effective_precision})='exact') AS exact_cost_count,
                           SUM(({effective_precision})='estimated') AS estimated_cost_count,
                           SUM(({effective_precision})='unknown') AS unknown_cost_count,
                           SUM(CASE WHEN ({effective_precision})<>'unknown' THEN 1 ELSE 0 END)
                             AS known_cost_event_count,
                           SUM(CASE WHEN u.cost_amount IS NOT NULL AND u.cost_precision_status='exact'
                                    THEN u.cost_amount ELSE dc.total_cost_amount END)
                             AS known_cost_amount,
                           COUNT(DISTINCT CASE
                             WHEN u.cost_amount IS NOT NULL AND u.cost_precision_status='exact'
                               THEN u.cost_currency ELSE dc.cost_currency END) AS cost_currency_count,
                           MAX(CASE
                             WHEN u.cost_amount IS NOT NULL AND u.cost_precision_status='exact'
                               THEN u.cost_currency ELSE dc.cost_currency END) AS known_cost_currency
                    FROM airank_provider_usage_events u
                    JOIN airank_provider_request_audits a ON a.id=u.request_audit_id
                    {latest_cost_join}
                    WHERE {where_sql}
                    """
                ),
                {key: value for key, value in params.items() if key != "limit"},
            ).mappings().one()
        event_records = [self._usage_record(row) for row in rows]
        return {
            "contract": "airank.provider-usage-ledger.v1",
            "events": event_records,
            "summary": self._usage_summary(summary_row),
            "filters": {
                "provider": provider_key,
                "project_id": project_id,
                "usage_precision": usage_precision,
                "cost_precision": cost_precision,
                "occurred_from": occurred_from.isoformat() if occurred_from else None,
                "occurred_until": occurred_until.isoformat() if occurred_until else None,
                "limit": limit,
            },
        }

    @staticmethod
    def _price_record(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "price_version_id": str(row["id"]),
            "provider": str(row["provider_key"]),
            "route_id": str(row["route_id"]),
            "model": str(row["model_name"]),
            "catalog_version": int(row["catalog_version"]),
            "currency": str(row["currency"]),
            "pricing_unit": str(row["pricing_unit"]),
            "input_price_per_million": decimal_text(row["input_price_per_million"]),
            "output_price_per_million": decimal_text(row["output_price_per_million"]),
            "effective_from": row["effective_from"].isoformat(),
            "effective_until": row["effective_until"].isoformat() if row["effective_until"] else None,
            "source_kind": str(row["source_kind"]),
            "source_reference": str(row["source_reference"]),
            "source_sha256": str(row["source_sha256"]),
            "reason": str(row["reason"]),
            "created_by": str(row["created_by"]),
            "created_at": row["created_at"].isoformat(),
        }

    @staticmethod
    def _usage_record(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "usage_event_id": str(row["id"]),
            "project_id": str(row["project_id"]),
            "request_audit_id": str(row["request_audit_id"]),
            "provider": str(row["provider_key"]),
            "route_id": str(row["route_id"] or ""),
            "model": str(row["model_name"]),
            "outcome": str(row["outcome"]),
            "provider_request_id_present": bool(row["provider_request_id"]),
            "input_tokens": int(row["input_tokens"]) if row["input_tokens"] is not None else None,
            "output_tokens": int(row["output_tokens"]) if row["output_tokens"] is not None else None,
            "total_tokens": int(row["total_tokens"]) if row["total_tokens"] is not None else None,
            "usage_precision": str(row["precision_status"]),
            "usage_source": str(row["usage_source"]),
            "raw_usage_sha256": str(row["raw_usage_sha256"] or ""),
            "cost_amount": decimal_text(row["effective_cost_amount"]),
            "cost_currency": (
                str(row["effective_cost_currency"])
                if row["effective_cost_currency"] is not None
                else None
            ),
            "cost_precision": str(row["effective_cost_precision"]),
            "cost_source": str(row["effective_cost_source"]),
            "price_version_id": (
                str(row["price_version_id"]) if row["price_version_id"] is not None else None
            ),
            "calculation_sha256": (
                str(row["calculation_sha256"])
                if row["calculation_sha256"] is not None
                else None
            ),
            "occurred_at": row["occurred_at"].isoformat(),
            "created_at": row["created_at"].isoformat(),
        }

    @staticmethod
    def _usage_summary(row: Mapping[str, Any]) -> dict[str, Any]:
        event_count = int(row["event_count"] or 0)
        exact_cost_count = int(row["exact_cost_count"] or 0)
        estimated_cost_count = int(row["estimated_cost_count"] or 0)
        unknown_cost_count = int(row["unknown_cost_count"] or 0)
        known_cost_count = int(row["known_cost_event_count"] or 0)
        one_currency = int(row["cost_currency_count"] or 0) == 1
        known_currency = str(row["known_cost_currency"]) if one_currency else None
        known_amount = decimal_text(row["known_cost_amount"]) if known_currency else None
        if event_count == 0 or unknown_cost_count > 0 or not one_currency:
            aggregate_precision = "unknown"
        elif estimated_cost_count > 0:
            aggregate_precision = "estimated"
        else:
            aggregate_precision = "exact"
        return {
            "event_count": event_count,
            "exact_usage_count": int(row["exact_usage_count"] or 0),
            "estimated_usage_count": int(row["estimated_usage_count"] or 0),
            "unknown_usage_count": int(row["unknown_usage_count"] or 0),
            "exact_cost_count": exact_cost_count,
            "estimated_cost_count": estimated_cost_count,
            "unknown_cost_count": unknown_cost_count,
            "known_cost_event_count": known_cost_count,
            "cost_coverage_rate": round(known_cost_count / event_count, 6) if event_count else 0.0,
            "known_cost_amount": known_amount,
            "known_cost_currency": known_currency,
            "aggregate_cost_precision": aggregate_precision,
        }
