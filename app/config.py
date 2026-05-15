from pathlib import Path
from typing import Literal

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DB_HOST: str
    DB_PORT: int = 5432
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    DB_CA_CERT_PATH: str
    DB_SSL_MODE: Literal["disable", "allow", "prefer", "require", "verify-ca", "verify-full"] = "verify-full"

    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 1440

    # Pepper for HMAC-SHA256 hashing of client IPs in scan_events.
    # Keep this stable — rotating it makes existing rows no longer comparable.
    IP_HASH_PEPPER: str

    AUTH_COOKIE_NAME: str = "mv_session"
    AUTH_COOKIE_SECURE: bool = True
    AUTH_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"

    DEFAULT_SUPERADMIN_EMAIL: str = "superadmin@magickvoice.com"
    DEFAULT_SUPERADMIN_PASSWORD: str = "Admin@123"

    HOSTING_ADDRESS: str = "http://localhost:3000"
    FRONTEND_ORIGIN: str = "http://localhost:3000"
    PORT: int = 8000
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"

    @computed_field  # type: ignore[misc]
    @property
    def db_ca_cert_absolute_path(self) -> Path:
        return Path(self.DB_CA_CERT_PATH).expanduser().resolve()


settings = Settings()  # type: ignore[call-arg]
