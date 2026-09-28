from __future__ import annotations

import asyncio
import json
import logging
import smtplib
from email.message import EmailMessage

import httpx
from aiokafka import AIOKafkaConsumer

from app import db
from app.broker import KafkaPublisher
from app.config import Settings, get_settings
from app.schemas import ProcessedLead
from app.worker import initialize_database


LOGGER = logging.getLogger(__name__)


def send_email(settings: Settings, lead: ProcessedLead) -> None:
    message = EmailMessage()
    message["Subject"] = f"New {lead.decision.category} lead from {lead.event.group_name}"
    message["From"] = settings.alert_email_from
    message["To"] = settings.alert_email_to
    message.set_content(
        "\n".join(
            [
                f"Category: {lead.decision.category}",
                f"Urgency: {lead.decision.urgency}",
                f"Confidence: {lead.decision.confidence:.0%}",
                f"Group: {lead.event.group_name}",
                f"Author: {lead.event.author or 'Unknown'}",
                f"Reason: {lead.decision.reason}",
                "",
                lead.event.text,
                "",
                f"Source: {lead.event.post_url or 'No URL supplied'}",
                f"Event ID: {lead.event.event_id}",
            ]
        )
    )
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password or "")
        smtp.send_message(message)


async def send_webhook(settings: Settings, lead: ProcessedLead) -> None:
    if not settings.notification_webhook_url:
        return
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            settings.notification_webhook_url,
            json=lead.model_dump(mode="json"),
            headers={"Idempotency-Key": lead.event.event_id},
        )
        response.raise_for_status()


async def deliver(settings: Settings, lead: ProcessedLead) -> None:
    if settings.alert_email_to:
        await asyncio.to_thread(send_email, settings, lead)
    await send_webhook(settings, lead)


async def run() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    await initialize_database(settings.database_url)

    publisher = KafkaPublisher(settings.kafka_bootstrap_servers)
    consumer = AIOKafkaConsumer(
        settings.kafka_qualified_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="lead-notifier-v2",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
    )
    await publisher.start()
    await consumer.start()
    failures: dict[str, int] = {}
    LOGGER.info("Notifier worker is listening on %s", settings.kafka_qualified_topic)
    try:
        async for message in consumer:
            event_id = str(message.value.get("event", {}).get("event_id", "unknown"))
            try:
                lead = ProcessedLead.model_validate(message.value)
                sent = await asyncio.to_thread(
                    db.notification_was_sent, settings.database_url, lead.event.event_id
                )
                if sent:
                    LOGGER.info("Skipping duplicate notification %s", lead.event.event_id)
                    await consumer.commit()
                    continue
                await deliver(settings, lead)
                await asyncio.to_thread(db.mark_notified, settings.database_url, lead.event.event_id)
                failures.pop(event_id, None)
                await consumer.commit()
                LOGGER.info("Notification delivered for %s", lead.event.event_id)
            except Exception as exc:
                LOGGER.exception("Failed to deliver notification for %s", event_id)
                failures[event_id] = failures.get(event_id, 0) + 1
                if failures[event_id] >= 3:
                    await publisher.publish(
                        settings.kafka_failed_topic,
                        {"stage": "notification", "lead": message.value, "error": str(exc)},
                        event_id,
                    )
                    failures.pop(event_id, None)
                    await consumer.commit()
                else:
                    await asyncio.sleep(2 ** failures[event_id])
    finally:
        await consumer.stop()
        await publisher.stop()


if __name__ == "__main__":
    asyncio.run(run())

