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


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


class RulesClassifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.rules: dict[str, Any] = json.loads(
            Path(settings.rule_config_path).read_text(encoding="utf-8")
        )

    async def classify(self, event: PublishedEvent) -> LeadDecision:
        post_text = event.text.casefold()
        location_text = f"{event.group_name} {event.text}".casefold()

        targets = [item.casefold() for item in self.settings.target_group_list]
        if targets and not any(item in event.group_name.casefold() for item in targets):
            return LeadDecision(
                is_lead=False,
                confidence=0.99,
                category="Other",
                urgency="low",
                reason="The event is not from a configured target group.",
                method="rules",
                rejection_code="group_not_allowed",
            )

        excluded = next(
            (p for p in self.rules.get("excluded_phrases", []) if _contains(post_text, p)),
            None,
        )
        if excluded:
            return LeadDecision(
                is_lead=False,
                confidence=0.99,
                category="Other",
                urgency="low",
                reason="The post matched a configured exclusion phrase.",
                method="rules",
                matched_terms=[excluded],
                rejection_code="excluded_phrase",
            )

        negative = next(
            (p for p in self.rules.get("negative_phrases", []) if _contains(post_text, p)),
            None,
        )
        if negative:
            return LeadDecision(
                is_lead=False,
                confidence=0.98,
                category="Other",
                urgency="low",
                reason="The request appears completed, cancelled, or negative.",
                method="rules",
                matched_terms=[negative],
                rejection_code="completed_request",
            )

        promotion = next(
            (p for p in self.rules.get("self_promotion_phrases", []) if _contains(post_text, p)),
            None,
        )
        if promotion:
            return LeadDecision(
                is_lead=False,
                confidence=0.97,
                category="Other",
                urgency="low",
                reason="The post appears to be professional self-promotion, not a consumer request.",
                method="rules",
                matched_terms=[promotion],
                rejection_code="self_promotion",
            )

        intent_hits = [
            phrase for phrase in self.rules.get("intent_phrases", []) if _contains(post_text, phrase)
        ]
        question_signal = "?" in event.text
        category = "Other"
        category_hits: list[str] = []
        for candidate, phrases in self.rules.get("categories", {}).items():
            hits = [phrase for phrase in phrases if _contains(post_text, phrase)]
            if len(hits) > len(category_hits):
                category = candidate
                category_hits = hits

        urgency_hit = next(
            (p for p in self.rules.get("urgency_phrases", []) if _contains(post_text, p)),
            None,
        )
        urgency = "high" if urgency_hit else ("medium" if intent_hits or question_signal else "low")
        location = next(
            (place for place in self.settings.market_location_list if _contains(location_text, place)),
            None,
        )
        matched_terms = _unique(
            category_hits + intent_hits[:3] + ([urgency_hit] if urgency_hit else [])
        )

        allowed = {item.casefold() for item in self.settings.allowed_category_list}
        if category_hits and allowed and category.casefold() not in allowed:
            return LeadDecision(
                is_lead=False,
                confidence=0.99,
                category=category,
                urgency=urgency,
                market_location=location,
                reason=f"The detected category {category} is disabled by configuration.",
                method="rules",
                matched_terms=matched_terms,
                rejection_code="category_not_allowed",
            )

        has_request = bool(intent_hits or question_signal)
        if category_hits and has_request:
            confidence = min(
                0.99,
                0.80
                + 0.04 * min(len(category_hits), 3)
                + (0.04 if intent_hits else 0.0)
                + (0.02 if question_signal else 0.0)
                + (0.02 if urgency_hit else 0.0),
            )
            reason = f"Detected {category} context with an active consumer request signal."
        elif category_hits:
            confidence = 0.48
            reason = f"Detected {category} context, but no clear request or recommendation intent."
        elif intent_hits:
            confidence = 0.30
            reason = "Detected request language without a supported real-estate or home-service category."
        else:
            confidence = 0.08
            reason = "No configured real-estate or home-service request was detected."

        if category_hits and has_request and self.settings.require_market_location and not location:
            return LeadDecision(
                is_lead=False,
                category=category,
                urgency=urgency,
                confidence=0.96,
                reason="The post has lead intent but does not mention a configured market location.",
                method="rules",
                matched_terms=matched_terms,
                rejection_code="location_required",
            )

        is_lead = bool(
            category_hits
            and has_request
            and confidence >= self.settings.lead_confidence_threshold
        )
        return LeadDecision(
            is_lead=is_lead,
            category=category,
            urgency=urgency,
            confidence=confidence,
            market_location=location,
            reason=reason,
            method="rules",
            matched_terms=matched_terms,
            rejection_code=None if is_lead else "below_threshold",
        )


class OpenAIClassifier:
    def __init__(self, settings: Settings):
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI classification")
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def classify(self, event: PublishedEvent) -> LeadDecision:
        allowed_categories = ", ".join(self.settings.allowed_category_list) or "all supported categories"
        market_locations = ", ".join(self.settings.market_location_list) or "not restricted"
        system_prompt = f"""
You triage authorized Facebook-group notification text for a realtor.
Identify only present or near-future consumer requests involving buying, selling,
renting, agent referrals, real-estate investing, contractors, or home services.
Reject advertisements, completed requests, news, jokes, and unrelated discussion.
Enabled categories: {allowed_categories}.
Configured market locations: {market_locations}.
Location is required: {self.settings.require_market_location}.
Use only the supplied group name and post. Do not infer protected or sensitive traits.
Confidence must represent how clearly the text shows actionable intent. matched_terms
must contain only short phrases that appear in the supplied post.
""".strip()
        response = await self.client.responses.parse(
            model=self.settings.openai_model,
            input=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Group: {event.group_name}\nPost: {event.text}",
                },
            ],
            text_format=LeadDecision,
        )
        if response.output_parsed is None:
            raise RuntimeError("The model did not return a parsed classification")
        return response.output_parsed.model_copy(
            update={"method": "openai", "model_name": self.settings.openai_model}
        )


class LeadClassifier:
    HARD_RULE_REJECTIONS = {
        "group_not_allowed",
        "excluded_phrase",
        "completed_request",
        "self_promotion",
        "category_not_allowed",
        "location_required",
    }

    def __init__(self, settings: Settings):
        self.settings = settings
        self.rules = RulesClassifier(settings)
        self.openai = None
        if settings.classifier_mode in {"openai", "hybrid"} and settings.openai_api_key:
            self.openai = OpenAIClassifier(settings)

    def _apply_policy(self, event: PublishedEvent, decision: LeadDecision) -> LeadDecision:
        targets = [item.casefold() for item in self.settings.target_group_list]
        if targets and not any(item in event.group_name.casefold() for item in targets):
            return decision.model_copy(
                update={
                    "is_lead": False,
                    "confidence": 0.99,
                    "rejection_code": "group_not_allowed",
                    "reason": "The event is not from a configured target group.",
                }
            )

        allowed = {item.casefold() for item in self.settings.allowed_category_list}
        if allowed and decision.category.casefold() not in allowed:
            return decision.model_copy(
                update={
                    "is_lead": False,
                    "confidence": 0.99,
                    "rejection_code": "category_not_allowed",
                    "reason": f"The detected category {decision.category} is disabled by configuration.",
                }
            )

        if decision.is_lead and self.settings.require_market_location and not decision.market_location:
            return decision.model_copy(
                update={
                    "is_lead": False,
                    "rejection_code": "location_required",
                    "reason": "The post has lead intent but no configured market location was identified.",
                }
            )

        if decision.confidence < self.settings.lead_confidence_threshold:
            return decision.model_copy(
                update={"is_lead": False, "rejection_code": "below_threshold"}
            )
        return decision

    async def _classify_with_openai(self, event: PublishedEvent, fallback: LeadDecision) -> LeadDecision:
        if self.openai is None:
            return fallback
        try:
            return self._apply_policy(event, await self.openai.classify(event))
        except Exception as error:
            LOGGER.warning(
                "OpenAI classification failed (%s); using deterministic fallback",
                type(error).__name__,
            )
            return fallback

    async def classify(self, event: PublishedEvent) -> LeadDecision:
        rule_decision = await self.rules.classify(event)
        if self.settings.classifier_mode == "rules" or self.openai is None:
            return rule_decision

        if self.settings.classifier_mode == "openai":
            return await self._classify_with_openai(event, rule_decision)

        if rule_decision.rejection_code in self.HARD_RULE_REJECTIONS:
            return rule_decision
        if rule_decision.is_lead and (
            rule_decision.confidence >= self.settings.hybrid_rules_accept_threshold
        ):
            return rule_decision
        if not rule_decision.is_lead and (
            rule_decision.confidence >= self.settings.hybrid_rules_reject_threshold
        ):
            return rule_decision
        return await self._classify_with_openai(event, rule_decision)
