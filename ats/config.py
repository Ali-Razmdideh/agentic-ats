from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="ATS_", extra="ignore"
    )

    inbox_dir: Path = Path("./inbox")

    # Postgres
    pg_dsn: str = "postgresql+asyncpg://ats:ats@localhost:5432/ats"
    pg_pool_size: int = 10
    pg_pool_max_over: int = 20

    # MinIO / S3-compatible
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "ats-artifacts"
    minio_region: str = "us-east-1"

    # Default org slug used by the CLI until sub-project #3 lands real auth.
    default_org_slug: str = "system"

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
