from pathlib import Path

import pytest

from app.classifier import LeadClassifier
from app.config import Settings
from app.schemas import PublishedEvent


ROOT = Path(__file__).resolve().parents[1]


def event(text: str, group: str = "Frisco Neighbors", event_id: str = "test-1") -> PublishedEvent:
    return PublishedEvent(
        event_id=event_id,
        source="test",
        source_message_id=event_id,
        group_name=group,
        author="Tester",
        text=text,
    )


def settings(**overrides) -> Settings:
    return Settings(
        classifier_mode="rules",
        rule_config_path=ROOT / "config" / "lead_rules.json",
        **overrides,
    )


@pytest.mark.asyncio
async def test_realtor_request_is_qualified():
    result = await LeadClassifier(settings()).classify(
        event("Can anyone recommend a realtor? We are moving to Frisco and want to buy a home.")
    )
    assert result.is_lead is True
    assert result.category in {"Buyer", "Agent Referral"}
    assert result.confidence >= 0.80


@pytest.mark.asyncio
async def test_contractor_request_is_high_urgency():
    result = await LeadClassifier(settings()).classify(
        event("Need a licensed roofer ASAP before closing. Who do you recommend?")
    )
    assert result.is_lead is True
    assert result.category == "Contractor or Home Service"
    assert result.urgency == "high"


@pytest.mark.asyncio
async def test_completed_request_is_rejected():
    result = await LeadClassifier(settings()).classify(
        event("I already found someone and am no longer looking for a contractor.")
    )
    assert result.is_lead is False


@pytest.mark.asyncio
async def test_non_target_group_is_rejected():
    result = await LeadClassifier(settings(target_groups="Frisco Neighbors")).classify(
        event("Can anyone recommend a realtor?", group="Personal Friends")
    )
    assert result.is_lead is False
    assert "target group" in result.reason

