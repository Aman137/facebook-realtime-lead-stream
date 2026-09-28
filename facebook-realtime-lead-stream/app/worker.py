from __future__ import annotations

import asyncio
import json
import logging

from aiokafka import AIOKafkaConsumer

from app import db
from app.broker import KafkaPublisher
from app.classifier import LeadClassifier
from app.config import get_settings
from app.schemas import ProcessedLead, PublishedEvent


LOGGER = logging.getLogger(__name__)


async def initialize_database(database_url: str) -> None:
    for attempt in range(1, 13):
        try:
            await asyncio.to_thread(db.init_database, database_url)
            return
        except Exception:
            if attempt == 12:
                raise
            LOGGER.warning("Database is not ready; retrying in 2 seconds")
            await asyncio.sleep(2)


async def run() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    await initialize_database(settings.database_url)

    classifier = LeadClassifier(settings)
    publisher = KafkaPublisher(settings.kafka_bootstrap_servers)
    consumer = AIOKafkaConsumer(
        settings.kafka_incoming_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="lead-classifier-v2",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
    )
    await publisher.start()
    await consumer.start()
    failures: dict[str, int] = {}
    LOGGER.info("Classifier worker is listening on %s", settings.kafka_incoming_topic)
    try:
        async for message in consumer:
            event_id = str(message.value.get("event_id", "unknown"))
            try:
                event = PublishedEvent.model_validate(message.value)
                already_processed = await asyncio.to_thread(
                    db.event_is_processed, settings.database_url, event.event_id
                )
                if already_processed:
                    LOGGER.info("Skipping duplicate processed event %s", event.event_id)
                    await consumer.commit()
                    continue

                await asyncio.to_thread(db.save_received_event, settings.database_url, event)
                decision = await classifier.classify(event)
                processed = ProcessedLead(event=event, decision=decision)
                await asyncio.to_thread(db.save_decision, settings.database_url, processed)

                payload = processed.model_dump(mode="json")
                await publisher.publish(settings.kafka_decisions_topic, payload, event.event_id)
                if decision.is_lead and decision.confidence >= settings.lead_confidence_threshold:
                    await publisher.publish(settings.kafka_qualified_topic, payload, event.event_id)
                    LOGGER.info(
                        "Qualified lead %s category=%s confidence=%.2f",
                        event.event_id,
                        decision.category,
                        decision.confidence,
                    )
                else:
                    LOGGER.info("Rejected event %s confidence=%.2f", event.event_id, decision.confidence)
                failures.pop(event_id, None)
                await consumer.commit()
            except Exception as exc:
                LOGGER.exception("Failed to process event %s", event_id)
                failures[event_id] = failures.get(event_id, 0) + 1
                if failures[event_id] >= 3:
                    await publisher.publish(
                        settings.kafka_failed_topic,
                        {"stage": "classification", "event": message.value, "error": str(exc)},
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

