"""
Central configuration — loaded once at startup from environment variables.
All settings are validated by Pydantic v2 BaseSettings.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── App ────────────────────────────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = "development"
    app_secret_key: str = "change-me"
    log_level: str = "INFO"

    # ── Database ───────────────────────────────────────────────────────────────
    database_url: str = Field(..., description="Async SQLAlchemy DSN")
    database_url_sync: str = Field(..., description="Sync DSN for Alembic")

    # ── OpenAI ─────────────────────────────────────────────────────────────────
    openai_api_key: str = Field(..., description="OpenAI API key")
    openai_model: str = "gpt-4o"
    openai_whisper_model: str = "whisper-1"
    openai_temperature: float = 0.2
    openai_max_tokens: int = 1024

    # ── WhatsApp Cloud API ──────────────────────────────────────────────────────
    whatsapp_verify_token: str = Field(..., description="Webhook verify token")
    whatsapp_access_token: str = Field(..., description="Meta permanent access token")
    whatsapp_phone_number_id: str = Field(..., description="Sender phone number ID")
    whatsapp_api_version: str = "v19.0"
    whatsapp_api_base: str = "https://graph.facebook.com"

    @property
    def whatsapp_api_url(self) -> str:
        return f"{self.whatsapp_api_base}/{self.whatsapp_api_version}/{self.whatsapp_phone_number_id}/messages"

    # ── ChromaDB ───────────────────────────────────────────────────────────────
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_collection: str = "rtknits_knowledge"

    # ── APScheduler ────────────────────────────────────────────────────────────
    nightly_plan_hour: int = 21
    nightly_plan_minute: int = 0
    timezone: str = "Indian/Mauritius"

    # ── P0 Escalation ──────────────────────────────────────────────────────────
    p0_escalation_minutes: int = 5

    # ── Seed Data ──────────────────────────────────────────────────────────────
    seed_data_dir: str = "data/"

    @field_validator("log_level")
    @classmethod
    def upper_log_level(cls, v: str) -> str:
        return v.upper()


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — call this everywhere."""
    return Settings()
