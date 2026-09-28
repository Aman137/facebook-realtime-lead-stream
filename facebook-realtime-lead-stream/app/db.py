from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.schemas import LeadDecision, ProcessedLead, PublishedEvent


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
    notified BOOLEAN NOT NULL DEFAULT FALSE,
    notified_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_lead_events_status_received
    ON lead_events (status, received_at DESC);
"""


def init_database(database_url: str) -> None:
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(DDL)


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


def save_decision(database_url: str, processed: ProcessedLead) -> None:
    status = "qualified" if processed.decision.is_lead else "rejected"
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE lead_events
                SET status = %s, classification = %s, processed_at = %s
                WHERE event_id = %s
                """,
                (
                    status,
                    Jsonb(processed.decision.model_dump(mode="json")),
                    processed.processed_at,
                    processed.event.event_id,
                ),
            )


def notification_was_sent(database_url: str, event_id: str) -> bool:
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT notified FROM lead_events WHERE event_id = %s", (event_id,))
            row = cursor.fetchone()
            return bool(row and row[0])


def mark_notified(database_url: str, event_id: str) -> None:
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE lead_events
                SET notified = TRUE, notified_at = NOW()
                WHERE event_id = %s
                """,
                (event_id,),
            )


def recent_qualified_leads(database_url: str, limit: int = 50) -> list[dict[str, Any]]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT event_id, group_name, author, post_text, post_url,
                       received_at, classification, notified, notified_at
                FROM lead_events
                WHERE status = 'qualified'
                ORDER BY received_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return list(cursor.fetchall())

