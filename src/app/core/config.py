"""Application configuration management using pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="paimon-backend", description="Application name")
    environment: Literal["development", "testing", "staging", "production"] = Field(
        default="development", description="Runtime environment"
    )
    debug: bool = Field(default=False, description="Debug mode flag")
    secret_key: str = Field(
        default="dev-secret-key-change-in-production",
        description="Secret key for signing",
    )

    # API
    api_v1_prefix: str = Field(default="/api/v1", description="API v1 prefix")
    allowed_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="CORS allowed origins",
    )

    # Database
    db_host: str = Field(default="localhost", description="PostgreSQL host")
    db_port: int = Field(default=5432, description="PostgreSQL port")
    db_user: str = Field(default="postgres", description="PostgreSQL user")
    db_password: str = Field(default="postgres", description="PostgreSQL password")
    db_name: str = Field(default="paimon", description="PostgreSQL database name")

    # Redis
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_db: int = Field(default=0, description="Redis database number")
    redis_password: str | None = Field(default=None, description="Redis password")

    # JWT Authentication
    access_token_expire_minutes: int = Field(
        default=30, description="Access token expiration in minutes"
    )
    refresh_token_expire_days: int = Field(
        default=7, description="Refresh token expiration in days"
    )

    # Blockchain
    bsc_rpc_url: str = Field(
        default="https://bsc-dataseed.binance.org/",
        description="BSC RPC endpoint",
    )
    bsc_rpc_backup_urls: list[str] = Field(
        default=[
            "https://bsc-dataseed1.defibit.io/",
            "https://bsc-dataseed1.ninicoin.io/",
        ],
        description="Backup BSC RPC endpoints",
    )

    # Contract Addresses
    vault_contract_address: str = Field(
        default="0x0000000000000000000000000000000000000000",
        description="Vault contract address",
    )
    redemption_manager_address: str = Field(
        default="0x0000000000000000000000000000000000000000",
        description="Redemption manager contract address",
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: Literal["json", "console"] = Field(
        default="json", description="Log output format"
    )

    # Notifications - Slack
    slack_webhook_url: str | None = Field(
        default=None, description="Slack incoming webhook URL"
    )
    slack_channel: str | None = Field(
        default=None, description="Slack channel override (optional)"
    )
    slack_mention_on_critical: bool = Field(
        default=True, description="Mention @channel on critical alerts"
    )

    # Notifications - Telegram
    telegram_bot_token: str | None = Field(
        default=None, description="Telegram bot token"
    )
    telegram_chat_id: str | None = Field(
        default=None, description="Telegram chat/group ID"
    )

    # Notifications - Email (SMTP)
    smtp_host: str | None = Field(default=None, description="SMTP server host")
    smtp_port: int = Field(default=587, description="SMTP server port")
    smtp_user: str | None = Field(default=None, description="SMTP username")
    smtp_password: str | None = Field(default=None, description="SMTP password")
    smtp_from_email: str | None = Field(
        default=None, description="Email sender address"
    )
    smtp_from_name: str = Field(
        default="Paimon Alert System", description="Email sender name"
    )
    smtp_use_tls: bool = Field(default=True, description="Use TLS for SMTP")

    # Notifications - Recipients
    alert_email_recipients: list[str] = Field(
        default=[], description="Email addresses for alerts"
    )

    @computed_field
    @property
    def database_url(self) -> str:
        """Construct database URL from components."""
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @computed_field
    @property
    def database_url_sync(self) -> str:
        """Construct synchronous database URL for migrations."""
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @computed_field
    @property
    def redis_url(self) -> str:
        """Construct Redis URL from components."""
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
