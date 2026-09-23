from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração obtida do ambiente e do arquivo .env local."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="PRM_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "PRM"
    environment: str = "development"
    database_url: str | None = Field(default=None, repr=False)
    session_cookie_name: str = "prm_session"
    csrf_cookie_name: str = "prm_csrf"
    session_cookie_secure: bool = False
    session_ttl_hours: int = Field(default=12, ge=1, le=168)
    organization_name: str = "Organização PRM"
    organization_timezone: str = "America/Sao_Paulo"
    max_upload_mib: int = Field(default=20, ge=1, le=100)
    max_import_rows: int = Field(default=50_000, ge=1, le=500_000)


@lru_cache
def get_settings() -> Settings:
    return Settings()

