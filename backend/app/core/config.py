from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Python OTA Server"
    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./ota.db"
    artifact_storage_path: str = "./storage/artifacts"
    public_base_url: str = "http://127.0.0.1:8080"
    polling_interval_seconds: int = Field(default=60, ge=1, le=86399)
    offline_threshold_seconds: int = Field(default=180, ge=1)
    max_ddi_body_bytes: int = Field(default=65536, ge=1024, le=1048576)
    max_upload_size_mb: int = Field(default=2048, ge=1, le=65536)
    session_hours: int = Field(default=12, ge=1, le=168)
    frontend_path: str = "../frontend/dist"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    default_tenant: str = Field(default="DEFAULT", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]

    @model_validator(mode="after")
    def validate_environment(self):
        url = urlsplit(self.public_base_url)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
        ):
            raise ValueError("PUBLIC_BASE_URL must be an HTTP(S) origin without credentials")
        self.public_base_url = self.public_base_url.rstrip("/")
        if not self.allowed_hosts or "*" in self.allowed_hosts:
            raise ValueError("ALLOWED_HOSTS must list explicit trusted hostnames/IPs")
        if url.hostname not in self.allowed_hosts:
            raise ValueError("PUBLIC_BASE_URL hostname must appear in ALLOWED_HOSTS")
        if self.offline_threshold_seconds <= self.polling_interval_seconds:
            raise ValueError("OFFLINE_THRESHOLD_SECONDS must exceed POLLING_INTERVAL_SECONDS")
        if self.app_env == "production":
            if url.scheme != "https" or url.hostname in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError(
                    "Production requires an externally reachable HTTPS PUBLIC_BASE_URL"
                )
            if not self.database_url.startswith("postgresql+psycopg://"):
                raise ValueError("Production requires PostgreSQL with the psycopg driver")
        return self
