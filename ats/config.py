from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="ATS_", extra="ignore"
    )

    db_path: Path = Path("./ats.db")
    inbox_dir: Path = Path("./inbox")

    # Defaults proven against OpenRouter; native Anthropic IDs work too via
    # ANTHROPIC_BASE_URL=https://api.anthropic.com plus ANTHROPIC_API_KEY.
    model_smart: str = "anthropic/claude-sonnet-4.5"
    model_fast: str = "anthropic/claude-haiku-4.5"

    bias_block_threshold: float = 0.20
    agent_timeout_s: float = 120.0
    agent_max_retries: int = 2
    max_cost_usd: float = 0.0  # 0 = no cap


def get_settings() -> Settings:
    return Settings()
