from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"), env_prefix="TENDEROS_", extra="ignore"
    )

    environment: str = "development"
    database_url: str = "postgresql+psycopg://localhost:5432/tenderos"
    app_url: str = "http://localhost:3010"

    session_cookie_name: str = "tenderos_session"
    session_ttl_hours: int = 24 * 7
    cookie_secure: bool = False
    # HMAC key for signed document download links. Must be set outside development.
    signing_secret: SecretStr = SecretStr("dev-only-signing-secret-change-me")

    storage_backend: str = "local"  # local | s3
    storage_local_dir: Path = Path(__file__).resolve().parents[1] / "var" / "storage"
    s3_endpoint_url: str | None = None
    s3_bucket: str = "tenderos"
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None
    s3_region: str = "us-east-1"
    max_upload_mb: int = 20

    # WhatsApp: "simulated" unless explicitly "live" AND credentials are configured.
    whatsapp_mode: str = "simulated"
    whatsapp_api_version: str = "v21.0"
    whatsapp_phone_number_id: str | None = None
    whatsapp_waba_id: str | None = None
    whatsapp_access_token: SecretStr | None = None
    whatsapp_app_secret: SecretStr | None = None
    whatsapp_verify_token: SecretStr | None = None
    whatsapp_template_language: str = "en"

    # Optional AI-assisted extraction. Deterministic parsing always runs first.
    ai_provider: str = "none"
    ai_api_key: SecretStr | None = None

    demo_seed_password: SecretStr = SecretStr("tenderos-demo-2026")

    @field_validator("signing_secret", mode="before")
    @classmethod
    def _default_secret(cls, v: object) -> object:
        return "dev-only-signing-secret-change-me" if v in ("", None) else v

    @field_validator(
        "s3_access_key",
        "s3_secret_key",
        "whatsapp_access_token",
        "whatsapp_app_secret",
        "whatsapp_verify_token",
        "ai_api_key",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        return None if v in ("", None) else v

    @field_validator("whatsapp_phone_number_id", "whatsapp_waba_id", "s3_endpoint_url", mode="before")
    @classmethod
    def _blank_str_to_none(cls, v: object) -> object:
        return None if v in ("", None) else v

    @property
    def whatsapp_live(self) -> bool:
        return (
            self.whatsapp_mode == "live"
            and self.whatsapp_phone_number_id is not None
            and self.whatsapp_access_token is not None
        )

    def assert_production_safe(self) -> None:
        if self.environment != "development":
            secret = self.signing_secret.get_secret_value()
            if secret.startswith("dev-only") or len(secret) < 32:
                raise RuntimeError("TENDEROS_SIGNING_SECRET must be a random value of at least 32 characters outside development")
            if not self.cookie_secure:
                raise RuntimeError("TENDEROS_COOKIE_SECURE must be true outside development")


@lru_cache
def get_settings() -> Settings:
    return Settings()
