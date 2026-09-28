from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from app.config import Settings
from app.schemas import LeadDecision, PublishedEvent


LOGGER = logging.getLogger(__name__)


def _contains(text: str, phrase: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(phrase.casefold()) + r"(?!\w)", text) is not None


class RulesClassifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.rules: dict[str, Any] = json.loads(
            Path(settings.rule_config_path).read_text(encoding="utf-8")
        )

    async def classify(self, event: PublishedEvent) -> LeadDecision:
        text = " ".join([event.group_name, event.text]).casefold()

        targets = [item.casefold() for item in self.settings.target_group_list]
        if targets and not any(item in event.group_name.casefold() for item in targets):
            return LeadDecision(
                is_lead=False,
                confidence=0.99,
                category="Other",
                urgency="low",
                reason="The event is not from a configured target group.",
                method="rules",
            )

        negative = next((p for p in self.rules["negative_phrases"] if _contains(text, p)), None)
        if negative:
            return LeadDecision(
                is_lead=False,
                confidence=0.97,
                category="Other",
                urgency="low",
                reason=f"The request appears completed or negative: {negative}.",
                method="rules",
            )

        promotion = next((p for p in self.rules["self_promotion_phrases"] if _contains(text, p)), None)
        if promotion:
            return LeadDecision(
                is_lead=False,
                confidence=0.94,
                category="Other",
                urgency="low",
                reason="The post appears to be professional self-promotion rather than a consumer request.",
                method="rules",
            )

        intent_hits = [p for p in self.rules["intent_phrases"] if _contains(text, p)]
        question_signal = "?" in event.text
        category = "Other"
        category_hits: list[str] = []
        for candidate, phrases in self.rules["categories"].items():
            hits = [phrase for phrase in phrases if _contains(text, phrase)]
            if len(hits) > len(category_hits):
                category = candidate
                category_hits = hits

        urgency_hit = next((p for p in self.rules["urgency_phrases"] if _contains(text, p)), None)
        urgency = "high" if urgency_hit else ("medium" if intent_hits else "low")
        location = next(
            (place for place in self.settings.market_location_list if _contains(text, place)),
            None,
        )

        if category_hits and (intent_hits or question_signal):
            confidence = min(0.98, 0.82 + 0.04 * min(len(category_hits), 3) + (0.03 if intent_hits else 0))
            reason = f"Detected {category} context ({category_hits[0]}) with an active request signal."
        elif category_hits:
            confidence = 0.48
            reason = f"Detected {category} context, but no clear request or recommendation intent."
        else:
            confidence = 0.10
            reason = "No configured real-estate or home-service request was detected."

        return LeadDecision(
            is_lead=bool(category_hits and (intent_hits or question_signal) and confidence >= self.settings.lead_confidence_threshold),
            category=category,
            urgency=urgency,
            confidence=confidence,
            market_location=location,
            reason=reason,
            method="rules",
        )


class OpenAIClassifier:
    def __init__(self, settings: Settings):
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI classification")
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def classify(self, event: PublishedEvent) -> LeadDecision:
        system_prompt = """
You triage authorized Facebook-group notification text for a realtor.
Identify only present or near-future consumer requests involving buying, selling,
renting, agent referrals, real-estate investing, contractors, or home services.
Reject advertisements, completed requests, news, jokes, and unrelated discussion.
Use only the supplied text. Do not infer protected or sensitive personal traits.
Confidence must represent how clearly the text shows actionable intent.
""".strip()
        response = await self.client.responses.parse(
            model=self.settings.openai_model,
            input=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Group: {event.group_name}\n"
                        f"Author: {event.author or 'Unknown'}\n"
                        f"Post: {event.text}"
                    ),
                },
            ],
            text_format=LeadDecision,
        )
        if response.output_parsed is None:
            raise RuntimeError("The model did not return a parsed classification")
        return response.output_parsed.model_copy(update={"method": "openai"})


class LeadClassifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.rules = RulesClassifier(settings)
        self.openai = None
        if settings.classifier_mode in {"openai", "hybrid"} and settings.openai_api_key:
            self.openai = OpenAIClassifier(settings)

    async def classify(self, event: PublishedEvent) -> LeadDecision:
        if self.settings.classifier_mode == "rules" or self.openai is None:
            return await self.rules.classify(event)
        try:
            decision = await self.openai.classify(event)
            if decision.confidence < self.settings.lead_confidence_threshold:
                return decision.model_copy(update={"is_lead": False})
            return decision
        except Exception:
            LOGGER.exception("OpenAI classification failed; using deterministic fallback")
            return await self.rules.classify(event)

