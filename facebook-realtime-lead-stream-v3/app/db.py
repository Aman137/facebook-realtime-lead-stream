from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.schemas import DeadLetterEvent, ProcessedLead, PublishedEvent


DDL = """
CREATE TABLE IF NOT EXISTS lead_events (
    event_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_message_id TEXT,
    group_name TEXT NOT NULL,
    author TEXT,
    post_text TEXT NOT NULL,
    post_url TEXT,
    received_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'received',
    classification JSONB,
    raw_event JSONB NOT NULL,
    processed_at TIMESTAMPTZ,
    processing_ms DOUBLE PRECISION,
    notified BOOLEAN NOT NULL DEFAULT FALSE,
    notified_at TIMESTAMPTZ,
    notification_latency_ms DOUBLE PRECISION,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT
);
ALTER TABLE lead_events ADD COLUMN IF NOT EXISTS processing_ms DOUBLE PRECISION;
ALTER TABLE lead_events ADD COLUMN IF NOT EXISTS notification_latency_ms DOUBLE PRECISION;
ALTER TABLE lead_events ADD COLUMN IF NOT EXISTS duplicate_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE lead_events ADD COLUMN IF NOT EXISTS last_error TEXT;
CREATE INDEX IF NOT EXISTS idx_lead_events_status_received
    ON lead_events (status, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_lead_events_processed_at
    ON lead_events (processed_at DESC);

CREATE TABLE IF NOT EXISTS pipeline_failures (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    attempts INTEGER NOT NULL,
    error TEXT NOT NULL,
    payload JSONB NOT NULL,
    failed_at TIMESTAMPTZ NOT NULL,
    resolved BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_pipeline_failures_failed_at
    ON pipeline_failures (failed_at DESC);

CREATE TABLE IF NOT EXISTS notification_deliveries (
    event_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    delivered_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    PRIMARY KEY (event_id, channel)
);
"""


def init_database(database_url: str) -> None:
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(DDL)


def database_is_ready(database_url: str) -> bool:
    with psycopg.connect(database_url, connect_timeout=3) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone() == (1,)


def event_is_processed(database_url: str, event_id: str) -> bool:
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT classification IS NOT NULL FROM lead_events WHERE event_id = %s",
                (event_id,),
            )
            row = cursor.fetchone()
            return bool(row and row[0])


def save_received_event(database_url: str, event: PublishedEvent) -> None:
    payload = event.model_dump(mode="json")
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO lead_events (
                    event_id, source, source_message_id, group_name, author,
                    post_text, post_url, received_at, raw_event
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                (
                    event.event_id,
                    event.source,
                    event.source_message_id,
                    event.group_name,
                    event.author,
                    event.text,
                    event.post_url,
                    event.received_at,
                    Jsonb(payload),
                ),
            )


def mark_duplicate(database_url: str, event_id: str) -> None:
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE lead_events SET duplicate_count = duplicate_count + 1 WHERE event_id = %s",
                (event_id,),
            )


def save_decision(database_url: str, processed: ProcessedLead) -> None:
    status = "qualified" if processed.decision.is_lead else "rejected"
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE lead_events
                SET status = %s,
                    classification = %s,
                    processed_at = %s,
                    processing_ms = %s,
                    last_error = NULL
                WHERE event_id = %s
                """,
                (
                    status,
                    Jsonb(processed.decision.model_dump(mode="json")),
                    processed.processed_at,
                    processed.processing_ms,
                    processed.event.event_id,
                ),
            )


def notification_was_sent(database_url: str, event_id: str) -> bool:
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT notified FROM lead_events WHERE event_id = %s", (event_id,))
            row = cursor.fetchone()
            return bool(row and row[0])


def notification_channel_was_sent(database_url: str, event_id: str, channel: str) -> bool:
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT delivered_at IS NOT NULL
                FROM notification_deliveries
                WHERE event_id = %s AND channel = %s
                """,
                (event_id, channel),
            )
            row = cursor.fetchone()
            return bool(row and row[0])


def mark_notification_channel_sent(database_url: str, event_id: str, channel: str) -> None:
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO notification_deliveries (
                    event_id, channel, delivered_at, attempts, last_error
                ) VALUES (%s, %s, NOW(), 1, NULL)
                ON CONFLICT (event_id, channel) DO UPDATE
                SET delivered_at = EXCLUDED.delivered_at,
                    attempts = notification_deliveries.attempts + 1,
                    last_error = NULL
                """,
                (event_id, channel),
            )


def mark_notification_channel_failed(
    database_url: str,
    event_id: str,
    channel: str,
    error: str,
) -> None:
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO notification_deliveries (
                    event_id, channel, delivered_at, attempts, last_error
                ) VALUES (%s, %s, NULL, 1, %s)
                ON CONFLICT (event_id, channel) DO UPDATE
                SET attempts = notification_deliveries.attempts + 1,
                    last_error = EXCLUDED.last_error
                """,
                (event_id, channel, error),
            )


def mark_notified(database_url: str, event_id: str) -> None:
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE lead_events
                SET notified = TRUE,
                    notified_at = NOW(),
                    notification_latency_ms = EXTRACT(EPOCH FROM (NOW() - received_at)) * 1000,
                    last_error = NULL
                WHERE event_id = %s
                """,
                (event_id,),
            )


def record_failure(database_url: str, failure: DeadLetterEvent) -> None:
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO pipeline_failures (
                    event_id, stage, attempts, error, payload, failed_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    failure.event_id,
                    failure.stage,
                    failure.attempts,
                    failure.error,
                    Jsonb(failure.payload),
                    failure.failed_at,
                ),
            )
            if failure.stage == "classification":
                cursor.execute(
                    """
                    UPDATE lead_events
                    SET status = 'failed', last_error = %s
                    WHERE event_id = %s
                    """,
                    (failure.error, failure.event_id),
                )
            else:
                cursor.execute(
                    "UPDATE lead_events SET last_error = %s WHERE event_id = %s",
                    (failure.error, failure.event_id),
                )


def recent_qualified_leads(database_url: str, limit: int = 50) -> list[dict[str, Any]]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT event_id, group_name, author, post_text, post_url,
                       received_at, processed_at, processing_ms, classification,
                       notified, notified_at, notification_latency_ms, duplicate_count
                FROM lead_events
                WHERE status = 'qualified'
                ORDER BY received_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return list(cursor.fetchall())


def recent_events(database_url: str, limit: int = 50) -> list[dict[str, Any]]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT event_id, group_name, author, post_text, post_url, received_at,
                       status, processed_at, processing_ms, classification, notified,
                       notified_at, notification_latency_ms, duplicate_count, last_error
                FROM lead_events
                ORDER BY received_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return list(cursor.fetchall())


def recent_failures(database_url: str, limit: int = 50) -> list[dict[str, Any]]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, event_id, stage, attempts, error, failed_at, resolved
                FROM pipeline_failures
                ORDER BY failed_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return list(cursor.fetchall())


def pipeline_stats(database_url: str) -> dict[str, Any]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(*)::INTEGER AS total_events,
                    COUNT(*) FILTER (WHERE status = 'qualified')::INTEGER AS qualified,
                    COUNT(*) FILTER (WHERE status = 'rejected')::INTEGER AS rejected,
                    COUNT(*) FILTER (WHERE status = 'received')::INTEGER AS pending,
                    COUNT(*) FILTER (WHERE status = 'failed')::INTEGER AS failed_events,
                    COUNT(*) FILTER (WHERE notified)::INTEGER AS notified,
                    COALESCE(SUM(duplicate_count), 0)::INTEGER AS duplicates_suppressed,
                    COALESCE(AVG(processing_ms), 0)::DOUBLE PRECISION AS avg_processing_ms,
                    COALESCE(AVG(notification_latency_ms), 0)::DOUBLE PRECISION
                        AS avg_notification_latency_ms
                FROM lead_events
                """
            )
            totals = dict(cursor.fetchone() or {})
            cursor.execute(
                """
                SELECT COALESCE(classification->>'category', 'Unknown') AS category,
                       COUNT(*)::INTEGER AS count
                FROM lead_events
                WHERE status = 'qualified'
                GROUP BY category
                ORDER BY count DESC, category
                """
            )
            categories = list(cursor.fetchall())
            cursor.execute(
                "SELECT COUNT(*)::INTEGER AS count FROM pipeline_failures WHERE NOT resolved"
            )
            failures = cursor.fetchone()

    totals["unresolved_failures"] = int(failures["count"] if failures else 0)
    totals["qualified_by_category"] = categories
    return totals


def cleanup_old_records(database_url: str, retention_days: int) -> dict[str, int]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM pipeline_failures WHERE failed_at < %s", (cutoff,))
            failures_deleted = cursor.rowcount
            cursor.execute(
                """
                DELETE FROM notification_deliveries
                WHERE event_id IN (
                    SELECT event_id FROM lead_events WHERE received_at < %s
                )
                """,
                (cutoff,),
            )
            deliveries_deleted = cursor.rowcount
            cursor.execute("DELETE FROM lead_events WHERE received_at < %s", (cutoff,))
            events_deleted = cursor.rowcount
    return {
        "events_deleted": events_deleted,
        "failures_deleted": failures_deleted,
        "deliveries_deleted": deliveries_deleted,
    }
