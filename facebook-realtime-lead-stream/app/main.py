from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from uuid import NAMESPACE_URL, uuid5

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse

from app import db
from app.broker import KafkaPublisher, Publisher
from app.config import get_settings
from app.schemas import AcceptedEvent, LeadEvent, PublishedEvent


LOGGER = logging.getLogger(__name__)


def _event_id(event: LeadEvent) -> str:
    stable_identity = event.source_message_id or "|".join(
        [event.group_name.casefold(), event.text.casefold(), event.post_url or ""]
    )
    return str(uuid5(NAMESPACE_URL, f"{event.source}:{stable_identity}"))


def create_app(publisher: Publisher | None = None) -> FastAPI:
    settings = get_settings()
    supplied_publisher = publisher

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(
            level=getattr(logging, settings.log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        active_publisher = supplied_publisher or KafkaPublisher(settings.kafka_bootstrap_servers)
        await active_publisher.start()
        app.state.publisher = active_publisher
        try:
            yield
        finally:
            await active_publisher.stop()

    application = FastAPI(
        title=settings.app_name,
        version="2.0.0",
        description="Receive authorized post events and publish them to the real-time lead pipeline.",
        lifespan=lifespan,
    )

    @application.get("/", response_class=HTMLResponse)
    async def home() -> str:
        return """
        <!doctype html><html><head><title>Real Time Lead Stream</title></head>
        <body style="font-family:system-ui;max-width:760px;margin:48px auto;padding:0 20px">
        <h1>Real Time Lead Stream</h1>
        <p>The event intake API is running.</p>
        <ul><li><a href="/docs">Open interactive API documentation</a></li>
        <li><a href="/health">Check health</a></li>
        <li><a href="/leads">View qualified leads</a></li></ul>
        </body></html>
        """

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "event-intake"}

    @application.post("/events", response_model=AcceptedEvent, status_code=202)
    async def receive_event(
        event: LeadEvent,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> AcceptedEvent:
        if settings.ingest_api_key and x_api_key != settings.ingest_api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
        event_id = _event_id(event)
        published = PublishedEvent(event_id=event_id, **event.model_dump())
        try:
            await application.state.publisher.publish(
                settings.kafka_incoming_topic,
                published.model_dump(mode="json"),
                event_id,
            )
        except Exception as exc:
            LOGGER.exception("Could not publish incoming event")
            raise HTTPException(status_code=503, detail="Event stream is temporarily unavailable") from exc
        return AcceptedEvent(event_id=event_id, topic=settings.kafka_incoming_topic)

    @application.get("/leads")
    async def leads(limit: int = Query(default=50, ge=1, le=200)):
        try:
            return await asyncio.to_thread(db.recent_qualified_leads, settings.database_url, limit)
        except Exception as exc:
            LOGGER.exception("Could not read qualified leads")
            raise HTTPException(status_code=503, detail="Lead database is temporarily unavailable") from exc

    return application


app = create_app()

