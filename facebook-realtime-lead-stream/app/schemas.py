from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


LeadCategory = Literal[
    "Buyer",
    "Seller",
    "Agent Referral",
    "Rental",
    "Contractor or Home Service",
    "Investor",
    "Other",
]


class LeadEvent(BaseModel):
    source: str = Field(default="manual", min_length=2, max_length=50)
    source_message_id: str | None = Field(default=None, max_length=200)
    group_name: str = Field(min_length=2, max_length=200)
    author: str | None = Field(default=None, max_length=200)
    text: str = Field(min_length=3, max_length=10000)
    post_url: str | None = Field(default=None, max_length=2000)
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("source", "group_name", "author", "text", "post_url", "source_message_id")
    @classmethod
    def strip_strings(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


class PublishedEvent(LeadEvent):
    event_id: str


class AcceptedEvent(BaseModel):
    status: Literal["accepted"] = "accepted"
    event_id: str
    topic: str


class LeadDecision(BaseModel):
    is_lead: bool
    category: LeadCategory = "Other"
    urgency: Literal["low", "medium", "high"] = "low"
    confidence: float = Field(ge=0.0, le=1.0)
    market_location: str | None = None
    reason: str = Field(min_length=3, max_length=500)
    method: Literal["rules", "openai"] = "rules"


class ProcessedLead(BaseModel):
    event: PublishedEvent
    decision: LeadDecision
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

