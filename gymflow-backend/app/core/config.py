"""Application settings, loaded from environment variables / .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "GymFlow AI"
    ENVIRONMENT: str = "development"
    API_PREFIX: str = "/api/v1"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # PostgreSQL in production, e.g.
    # postgresql+psycopg://gymflow:gymflow@localhost:5432/gymflow
    DATABASE_URL: str = "sqlite:///./gymflow.db"

    # Auth
    SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # AI (Claude) for diet plans
    ANTHROPIC_API_KEY: str | None = None
    AI_MODEL: str = "claude-opus-5-5"

    # WhatsApp Cloud API
    WHATSAPP_API_URL: str = "https://graph.facebook.com/v21.0"
    WHATSAPP_PHONE_NUMBER_ID: str | None = None
    WHATSAPP_ACCESS_TOKEN: str | None = None

    # AI voice-calling provider (generic HTTP API)
    VOICE_API_URL: str | None = None
    VOICE_API_KEY: str | None = None

    # Razorpay
    RAZORPAY_KEY_ID: str | None = None
    RAZORPAY_KEY_SECRET: str | None = None
    RAZORPAY_WEBHOOK_SECRET: str | None = None

    # n8n
    N8N_WEBHOOK_BASE_URL: str | None = None
    N8N_API_KEY: str | None = None  # shared secret for n8n -> GymFlow callbacks

    # Amazon Associates
    AMAZON_ASSOCIATE_TAG: str | None = None
    AMAZON_MARKETPLACE_DOMAIN: str = "www.amazon.in"

    # Background jobs (expiry, payment reminders, notification sending) run
    # in-process when enabled; otherwise run app/workers/* via cron or n8n.
    ENABLE_SCHEDULER: bool = False

    # Affiliate revenue share (percent of each commission; must sum to 100)
    PLATFORM_SHARE_PCT: float = 20.0
    GYM_SHARE_PCT: float = 30.0
    TRAINER_SHARE_PCT: float = 50.0

    # Website builder / subscriptions
    SITES_BASE_DOMAIN: str = "gymflow.app"
    TRIAL_DAYS: int = 14


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.ENVIRONMENT == "production" and (s.SECRET_KEY == "change-me-in-production" or len(s.SECRET_KEY) < 32):
        raise RuntimeError("Set a strong SECRET_KEY (32+ characters) in production")
    return s


settings = get_settings()
