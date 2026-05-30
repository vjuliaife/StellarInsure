import os
import logging
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator, model_validator
from functools import lru_cache

logger = logging.getLogger(__name__)

# Sensitive field names that should never be logged
_SENSITIVE_FIELDS = frozenset({
    "jwt_secret_key",
    "stellar_admin_secret",
    "storage_secret_key",
    "database_url",
    "redis_url",
    "webhook_secret_key",
})


class Settings(BaseSettings):
    environment: str = "development"
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    jwt_secret_key: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    stellar_network_passphrase: str = "Test SDF Network ; September 2015"
    stellar_horizon_url: str = "https://horizon-testnet.stellar.org"
    stellar_contract_id: Optional[str] = None
    stellar_admin_secret: Optional[str] = None
    stellar_admin_public: Optional[str] = None

    database_url: str = "postgresql://postgres:postgres@localhost:5432/stellarinsure"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 3600
    db_pool_pre_ping: bool = True
    db_echo: bool = False

    # Storage settings
    storage_type: str = "local"
    upload_dir: str = "uploads"
    max_upload_size: int = 10 * 1024 * 1024  # 10MB
    storage_secret_key: str = "storage-secret-key-change-in-production"
    base_url: str = "http://localhost:8000"

    # Redis settings
    redis_url: str = "redis://localhost:6379/0"
    redis_cache_ttl: int = 300
    redis_enabled: bool = True

    # Rate limiting settings
    rate_limit_default: str = "60/minute"
    rate_limit_auth: str = "10/minute"
    rate_limit_auth_bypass: bool = False

    # Webhook settings
    webhook_secret_key: str = "webhook-secret-key-change-in-production"
    webhook_max_retries: int = 3
    webhook_delivery_timeout: int = 30
    webhook_max_per_user: int = 10
    webhook_backoff_base: float = 1.0

    # Logging
    log_level: str = "INFO"

    # Feature flags
    feature_flag_oracle_v2: bool = False
    feature_flag_claim_auto_approval: bool = False
    feature_flag_pool_rebalancing: bool = False

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production", "test"}
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v = v.upper()
        if v not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if self.environment == "production":
            if self.jwt_secret_key == "your-secret-key-change-in-production":
                raise ValueError("jwt_secret_key cannot be the default placeholder in production")
            if self.storage_secret_key == "storage-secret-key-change-in-production":
                raise ValueError("storage_secret_key cannot be the default placeholder in production")
        return self

    @property
    def allowed_origins(self) -> List[str]:
        if self.environment == "production":
            origins = os.getenv("CORS_ORIGINS", "")
            return [origin.strip() for origin in origins.split(",") if origin.strip()]
        else:
            return [
                "http://localhost:3000",
                "http://localhost:5173",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
            ]

    @property
    def is_testnet(self) -> bool:
        return "testnet" in self.stellar_horizon_url.lower() or "test" in self.stellar_network_passphrase.lower()

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def feature_flags(self) -> dict:
        return {
            "oracle_v2": self.feature_flag_oracle_v2,
            "claim_auto_approval": self.feature_flag_claim_auto_approval,
            "pool_rebalancing": self.feature_flag_pool_rebalancing,
        }

    def log_settings(self) -> None:
        """Log non-sensitive settings on startup for debugging."""
        for field_name in type(self).model_fields:
            if field_name in _SENSITIVE_FIELDS:
                logger.info("  %s = ****REDACTED****", field_name)
            else:
                logger.info("  %s = %s", field_name, getattr(self, field_name))

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    logger.info("Settings loaded for environment: %s", settings.environment)
    settings.log_settings()
    return settings
