from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Facebook Real Time Lead Stream"
    log_level: str = "INFO"
    ingest_api_key: str = "development-key"

    classifier_mode: Literal["rules", "openai", "hybrid"] = "rules"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"
    lead_confidence_threshold: float = Field(default=0.80, ge=0.0, le=1.0)
    hybrid_rules_accept_threshold: float = Field(default=0.90, ge=0.0, le=1.0)
    hybrid_rules_reject_threshold: float = Field(default=0.94, ge=0.0, le=1.0)
    rule_config_path: Path = Path("config/lead_rules.json")
    target_groups: str = ""
    market_locations: str = "Dallas,Fort Worth,Frisco,Plano,McKinney,Denton"
    allowed_categories: str = ""
    require_market_location: bool = False

    kafka_bootstrap_servers: str = "localhost:29092"
    kafka_incoming_topic: str = "incoming-posts"
    kafka_decisions_topic: str = "lead-decisions"
    kafka_qualified_topic: str = "qualified-leads"
    kafka_failed_topic: str = "failed-events"

    database_url: str = "postgresql://leadfilter:leadfilter@localhost:5432/leadfilter"
    data_retention_days: int = Field(default=30, ge=1, le=3650)
    max_processing_attempts: int = Field(default=3, ge=1, le=20)
    retry_base_seconds: float = Field(default=1.0, ge=0.0, le=60.0)

    alert_email_to: str = "realtor@example.com"
    alert_email_from: str = "lead-filter@example.com"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_starttls: bool = False
    smtp_username: str | None = None
    smtp_password: str | None = None
    notification_webhook_url: str | None = None
    notification_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)

    dashboard_api_key: str = "development-dashboard-key"
    dashboard_refresh_seconds: int = Field(default=5, ge=2, le=300)
    pii_log_redaction: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @staticmethod
    def _split_csv(value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]

    @property
    def target_group_list(self) -> list[str]:
        return self._split_csv(self.target_groups)

    @property
    def market_location_list(self) -> list[str]:
        return self._split_csv(self.market_locations)

    @property
    def allowed_category_list(self) -> list[str]:
        return self._split_csv(self.allowed_categories)


@lru_cache
def get_settings() -> Settings:
    return Settings()
