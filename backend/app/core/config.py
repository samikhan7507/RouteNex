"""Typed, fail-closed application settings.

Development/demo defaults are intentionally usable on a laptop. Production
requires explicit secrets and provider credentials; demo shortcuts are refused.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "staging", "production"] = "development"
    app_name: str = "RouteNex"
    base_url: str = "http://localhost:8000"
    database_url: str = "postgresql+psycopg://routenex:routenex@localhost:5432/routenex"
    database_pool_size: int = Field(10, ge=1, le=100)
    database_max_overflow: int = Field(20, ge=0, le=200)
    secret_key: str = ""
    session_hours: int = Field(12, ge=1, le=168)
    session_idle_minutes: int = Field(60, ge=5, le=1440)
    cookie_name: str = "routenex_session"
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173,http://127.0.0.1:5173"
    trusted_hosts: str = "localhost,127.0.0.1,*.e2b.app"
    demo_mode: bool = True
    demo_autopilot: bool = True
    admin_name: str = "Sami Khan"
    admin_email: str = "samikhan@gmail.com"
    admin_password: str = ""
    seed_demo_data: bool = True

    payment_provider: Literal["demo", "razorpay"] = "demo"
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    razorpay_api_url: str = "https://api.razorpay.com/v1"
    reservation_minutes: int = Field(15, ge=5, le=60)

    location_provider: Literal["local", "photon", "geoapify"] = "local"
    photon_url: str = ""
    geoapify_api_key: str = ""
    routing_url: str = "https://router.project-osrm.org"
    tile_url: str = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
    tile_attribution: str = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    weather_enabled: bool = True

    otp_provider: Literal["console", "twilio"] = "console"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    google_client_id: str = ""
    llm_provider: Literal["offline", "ollama", "gemini", "auto"] = "offline"
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:3b"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"
    ml_artifact_dir: str = str(ROOT / "ml" / "artifacts")
    ml_autotrain: bool = False
    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.app_env in ("production", "staging")

    @property
    def secure_cookies(self) -> bool:
        return self.is_production

    @property
    def origins(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def hosts(self) -> list[str]:
        return [x.strip() for x in self.trusted_hosts.split(",") if x.strip()]

    @model_validator(mode="after")
    def validate_production(self):
        if not self.secret_key:
            if self.is_production:
                raise ValueError("SECRET_KEY is required in production/staging")
            object.__setattr__(self, "secret_key", "development-only-change-me-before-deploying")
        if self.is_production:
            if len(self.secret_key) < 32:
                raise ValueError("SECRET_KEY must contain at least 32 characters")
            if self.demo_mode or self.demo_autopilot or self.seed_demo_data:
                raise ValueError("DEMO_MODE, DEMO_AUTOPILOT and SEED_DEMO_DATA must be false in production/staging")
            if self.payment_provider != "razorpay" or not all((self.razorpay_key_id, self.razorpay_key_secret, self.razorpay_webhook_secret)):
                raise ValueError("Production requires PAYMENT_PROVIDER=razorpay and all Razorpay credentials")
            if self.otp_provider == "console":
                raise ValueError("Production requires a real OTP_PROVIDER (twilio)")
            if not self.base_url.startswith("https://"):
                raise ValueError("BASE_URL must use HTTPS in production/staging")
            if not self.admin_password or len(self.admin_password) < 12 or self.admin_password.lower() in {"sami@123", "demo@123", "password123"}:
                raise ValueError("Production requires a unique ADMIN_PASSWORD of at least 12 characters")
        if self.payment_provider == "razorpay" and not all((self.razorpay_key_id, self.razorpay_key_secret, self.razorpay_webhook_secret)):
            raise ValueError("Razorpay requires key id, key secret and webhook secret")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
