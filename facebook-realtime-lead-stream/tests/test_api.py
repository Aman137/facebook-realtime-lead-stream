from pathlib import Path

from fastapi.testclient import TestClient

from app.broker import InMemoryPublisher
from app.config import get_settings
from app.main import create_app


def test_event_is_published_with_stable_id(monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")
    monkeypatch.setenv("RULE_CONFIG_PATH", str(Path(__file__).resolve().parents[1] / "config" / "lead_rules.json"))
    get_settings.cache_clear()
    publisher = InMemoryPublisher()
    app = create_app(publisher)
    payload = {
        "source": "test",
        "source_message_id": "message-123",
        "group_name": "Frisco Neighbors",
        "text": "Looking for a realtor in Frisco."
    }
    with TestClient(app) as client:
        first = client.post("/events", json=payload, headers={"X-API-Key": "test-key"})
        second = client.post("/events", json=payload, headers={"X-API-Key": "test-key"})
    assert first.status_code == 202
    assert first.json()["event_id"] == second.json()["event_id"]
    assert len(publisher.messages) == 2
    assert publisher.messages[0][0] == "incoming-posts"
    get_settings.cache_clear()


def test_missing_api_key_is_rejected(monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")
    get_settings.cache_clear()
    publisher = InMemoryPublisher()
    app = create_app(publisher)
    with TestClient(app) as client:
        response = client.post(
            "/events",
            json={"group_name": "Frisco Neighbors", "text": "Looking for a realtor"},
        )
    assert response.status_code == 401
    get_settings.cache_clear()

