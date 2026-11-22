"""Application settings, loaded from environment variables / .env."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_files() -> tuple[str, ...]:
    here = Path(__file__).resolve()
    repo_root = here.parents[3] if len(here.parents) > 3 else here.parent
    return (str(repo_root / ".env"), ".env")


_ENV_FILES = _env_files()


class Settings(BaseSettings):
    # The repo-root .env (shared keys) is read first; gymflow-backend/.env overrides it. On hosts like Vercel
    # neither file exists and settings come from the environment.
    model_config = SettingsConfigDict(env_file=_ENV_FILES, env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "GymFlow"
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

    # AI. LLM_PROVIDER picks the text/agent model: auto (Groq if set, else Claude) | groq | claude.
    LLM_PROVIDER: str = "auto"
    GROQ_API_KEY: str | None = None
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    ANTHROPIC_API_KEY: str | None = None
    AI_MODEL: str = "claude-opus-5-5"
    # Gemini: Google/social posts, post images and live Google Search answers
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_IMAGE_MODEL: str = "gemini-3.1-flash-image"

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
    # Razorpay Subscriptions plan ids (Dashboard -> Subscriptions -> Plans) for GymFlow's own SaaS billing.
    RAZORPAY_PLAN_STARTER: str | None = None
    RAZORPAY_PLAN_GROWTH: str | None = None
    RAZORPAY_PLAN_PRO: str | None = None

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

    # Public URLs (OAuth redirects, links in messages, QR codes)
    FRONTEND_URL: str = "http://localhost:3000"
    PUBLIC_API_URL: str = "http://localhost:8000/api/v1"

    # Encrypts OAuth tokens at rest. Any string; defaults to a key derived from SECRET_KEY.
    TOKEN_ENCRYPTION_KEY: str | None = None

    # Google (Search Console + Business Profile) OAuth web client
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    # Defaults to {PUBLIC_API_URL}/integrations/google/callback
    GOOGLE_OAUTH_REDIRECT_URI: str | None = None

    # WhatsApp inbound webhooks
    WHATSAPP_VERIFY_TOKEN: str | None = None
    WHATSAPP_APP_SECRET: str | None = None  # verifies X-Hub-Signature-256

    # SEO crawler limits
    SEO_MAX_PAGES: int = 25
    SEO_REQUEST_TIMEOUT: float = 10.0
    SEO_MAX_PAGE_BYTES: int = 2_000_000
    SEO_USER_AGENT: str = "GymFlowSEOAudit/1.0 (+https://gymflow.app/bot)"

    # Optional keyword-metrics provider. Without one, keyword ideas are labelled as suggestions.
    KEYWORD_PROVIDER: str | None = None
    KEYWORD_PROVIDER_API_KEY: str | None = None

    # Email (password reset, monthly owner report): Resend, or SMTP. Neither -> emails are only logged.
    EMAIL_FROM: str = "GymFlow <hello@gymflow.app>"
    RESEND_API_KEY: str | None = None
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None

    # Shared secret for /cron/* endpoints (Vercel Cron sends it as "Authorization: Bearer <CRON_SECRET>")
    CRON_SECRET: str | None = None

    # Error monitoring (optional: pip install sentry-sdk)
    SENTRY_DSN: str | None = None

    # "See a live demo gym" button: logs visitors into the IronCore demo tenant (never a real gym)
    DEMO_LOGIN_ENABLED: bool = False

    # Public endpoint rate limits (requests per minute per IP)
    PUBLIC_RATE_LIMIT_PER_MINUTE: int = 20


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.ENVIRONMENT == "production" and (s.SECRET_KEY == "change-me-in-production" or len(s.SECRET_KEY) < 32):
        raise RuntimeError("Set a strong SECRET_KEY (32+ characters) in production")
    import os

    if os.environ.get("VERCEL") and s.DATABASE_URL.startswith("sqlite"):
        # Serverless file systems are temporary: every deploy/cold start would lose all data.
        raise RuntimeError("Set DATABASE_URL to a PostgreSQL database (e.g. Neon) when running on Vercel")
    return s


settings = get_settings()
