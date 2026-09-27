from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Csv = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"  # local | staging | production
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/mangatranslate"
    auth_secret: str = "dev-only-change-me"
    web_url: str = "http://localhost:3000"  # used in e-mails and payment return URLs
    cors_origins: Csv = ["http://localhost:3000"]
    session_days: int = 30

    # S3-compatible object storage (Cloudflare R2 in production, MinIO locally)
    s3_endpoint: str = "http://localhost:9000"
    s3_public_endpoint: str = ""  # endpoint the browser can reach, if different (docker)
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "mangatranslate"
    s3_region: str = "auto"

    max_upload_mb: int = 200
    max_image_pixels: int = 40_000_000

    # E-mail: "console" logs messages (local only), "smtp" sends them
    email_provider: str = "console"
    email_from: str = "MangaTranslate AI <no-reply@example.com>"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # Payments: comma-separated enabled providers ("payos", "dev" outside production)
    payment_providers: Csv = ["dev"]
    payos_client_id: str = ""
    payos_api_key: str = ""
    payos_checksum_key: str = ""
    payos_base_url: str = "https://api-merchant.payos.vn"
    dev_payment_secret: str = "dev-payment-secret"

    @field_validator("cors_origins", "payment_providers", mode="before")
    @classmethod
    def _split(cls, v):
        return [s.strip() for s in v.split(",") if s.strip()] if isinstance(v, str) else v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def check(self) -> None:
        """Refuse to boot production with development defaults."""
        if not self.is_production:
            return
        problems = []
        if self.auth_secret == "dev-only-change-me" or len(self.auth_secret) < 32:
            problems.append("AUTH_SECRET must be a random string of 32+ characters")
        if "dev" in self.payment_providers:
            problems.append("the dev payment provider cannot be enabled in production")
        if self.email_provider == "console":
            problems.append("EMAIL_PROVIDER=console is not allowed in production")
        if not self.web_url.startswith("https://"):
            problems.append("WEB_URL must be https in production")
        if problems:
            raise RuntimeError("Invalid production configuration: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()
