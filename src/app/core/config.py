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

    # BSC Testnet Configuration (Chain ID: 97)
    blockchain_network: Literal["testnet", "mainnet"] = Field(
        default="testnet", description="Blockchain network selection"
    )
    bsc_testnet_rpc_url: str = Field(
        default="https://data-seed-prebsc-1-s1.binance.org:8545",
        description="BSC Testnet RPC endpoint",
    )
    bsc_testnet_backup_urls: list[str] = Field(
        default=[
            "https://data-seed-prebsc-2-s1.binance.org:8545",
            "https://data-seed-prebsc-1-s2.binance.org:8545",
        ],
        description="Backup BSC Testnet RPC endpoints",
    )
    testnet_vault_address: str = Field(
        default="0x0000000000000000000000000000000000000000",
        description="Testnet Vault contract address",
    )
    testnet_redemption_manager: str = Field(
        default="0x0000000000000000000000000000000000000000",
        description="Testnet Redemption manager address",
    )
    testnet_redemption_voucher: str = Field(
        default="0x0000000000000000000000000000000000000000",
        description="Testnet Redemption voucher NFT address",
    )
    testnet_hot_wallet_pk: str = Field(
        default="", description="Testnet hot wallet private key (NEVER use mainnet key!)"
    )

    # Mainnet Configuration - VIP Approver (链上审批执行)
    vip_approver_private_key: str = Field(
        default="",
        description="Private key for VIP_APPROVER_ROLE (mainnet only, 链上审批执行)"
    )

    # Approval Thresholds (与合约 PPTTypes.sol 保持同步)
    standard_approval_amount: int = Field(
        default=50_000 * 10**18,  # 50K USDT
        description="标准通道审批阈值"
    )
    emergency_approval_amount: int = Field(
        default=30_000 * 10**18,  # 30K USDT
        description="紧急通道审批阈值"
    )
    approval_quota_ratio: int = Field(
        default=2000,  # 20% = 2000 basis points
        description="配额比例阈值 (basis points)"
    )

    # Feature Flags - Data Source Control
    ff_fund_overview_source: Literal["mock", "real"] = Field(
        default="mock", description="Fund overview data source"
    )
    ff_asset_allocation_source: Literal["mock", "real"] = Field(
        default="mock", description="Asset allocation data source"
    )
    ff_flow_metrics_source: Literal["mock", "real"] = Field(
        default="mock", description="Flow metrics data source"
    )
    ff_nav_history_source: Literal["mock", "real"] = Field(
        default="mock", description="NAV history data source"
    )
    ff_yield_metrics_source: Literal["mock", "real"] = Field(
        default="mock", description="Yield metrics data source"
    )
    ff_tier_allocation_source: Literal["mock", "real"] = Field(
        default="mock", description="Tier allocation data source"
    )
    ff_blockchain_execution: Literal["mock", "real"] = Field(
        default="mock", description="Blockchain transaction execution mode"
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

    @computed_field
    @property
    def active_rpc_url(self) -> str:
        """Get RPC URL based on current network selection."""
        if self.blockchain_network == "testnet":
            return self.bsc_testnet_rpc_url
        return self.bsc_rpc_url

    @computed_field
    @property
    def active_backup_rpc_urls(self) -> list[str]:
        """Get backup RPC URLs based on current network selection."""
        if self.blockchain_network == "testnet":
            return self.bsc_testnet_backup_urls
        return self.bsc_rpc_backup_urls

    @computed_field
    @property
    def active_vault_address(self) -> str:
        """Get vault address based on current network selection."""
        if self.blockchain_network == "testnet":
            return self.testnet_vault_address
        return self.vault_contract_address

    @computed_field
    @property
    def active_redemption_manager(self) -> str:
        """Get redemption manager address based on current network selection."""
        if self.blockchain_network == "testnet":
            return self.testnet_redemption_manager
        return self.redemption_manager_address

    @computed_field
    @property
    def active_redemption_voucher(self) -> str:
        """Get redemption voucher address based on current network selection."""
        if self.blockchain_network == "testnet":
            return self.testnet_redemption_voucher
        return getattr(self, "redemption_voucher_address", "0x0000000000000000000000000000000000000000")

    @computed_field
    @property
    def chain_id(self) -> int:
        """Get chain ID based on current network selection."""
        return 97 if self.blockchain_network == "testnet" else 56

    @computed_field
    @property
    def active_approver_key(self) -> str:
        """获取当前网络的审批私钥.

        Returns:
            testnet: 使用 testnet_hot_wallet_pk
            mainnet: 使用 vip_approver_private_key
        """
        if self.blockchain_network == "testnet":
            return self.testnet_hot_wallet_pk
        return self.vip_approver_private_key

    @computed_field
    @property
    def is_mainnet(self) -> bool:
        """检查是否为主网环境."""
        return self.blockchain_network == "mainnet"

    def require_mainnet_protection(self) -> None:
        """主网保护检查 - 执行敏感操作前调用.

        Raises:
            ValueError: 主网环境但缺少必要的私钥配置
        """
        if self.is_mainnet:
            if not self.vip_approver_private_key:
                raise ValueError(
                    "主网环境必须配置 VIP_APPROVER_PRIVATE_KEY 才能执行链上操作"
                )
            if self.environment != "production":
                raise ValueError(
                    f"主网操作要求 environment=production，当前为 {self.environment}"
                )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
