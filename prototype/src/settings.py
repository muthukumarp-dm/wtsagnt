"""Typed access to environment variables. Loaded once via pydantic-settings."""
from __future__ import annotations
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    openai_api_key: str
    openai_content_model: str = "gpt-4o"
    openai_classification_model: str = "gpt-4o-mini"

    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_from: str

    supabase_url: str
    supabase_secret_key: str
    supabase_storage_bucket: str = "lesson-files"

    public_base_url: str
    signed_url_ttl_seconds: int = Field(default=604800)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
