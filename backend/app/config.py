"""Runtime configuration, loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DRAFTFI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_path: str = "sandbox.db"

    # CORS origins for the local React dev server. Empty by default: the
    # packaged app serves its frontend same-origin and never needs this, and
    # shipping the Vite ports in the allowlist granted credentialed read access
    # to anything that happened to be listening on 5173. Set
    # DRAFTFI_CORS_ORIGINS in the dev .env instead.
    cors_origins: str = ""

    # NOTE: LLM provider/model/base-URL/API-keys are configured at runtime and
    # stored in the database (see services/llm_config.py), not via env.

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
