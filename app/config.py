from functools import lru_cache

from pydantic import Field, SecretStr
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
    meeting_storage_dir: str = "data/meetings"
    meeting_text_max_bytes: int = Field(default=2097152, ge=1024)
    meeting_ai_provider: str = "anthropic"
    meeting_ai_model: str = ""
    meeting_ai_timeout_seconds: int = Field(default=120, ge=10, le=600)
    meeting_ai_max_retries: int = Field(default=1, ge=0, le=3)
    meeting_ai_max_output_tokens: int = Field(default=16000, ge=1024, le=64000)
    meeting_ai_max_input_tokens: int = Field(default=100000, ge=1000, le=1000000)
    meeting_enable_fixture: bool = False
    audio_max_bytes: int = Field(default=262144000, ge=1024)
    audio_max_duration_seconds: int = Field(default=14400, ge=1, le=86400)
    asr_python: str = ""
    asr_model: str = "small"
    asr_model_cache_dir: str = "data/meetings/models"
    asr_language: str = "pt"
    asr_timeout_seconds: int = Field(default=14400, ge=30)
    asr_memory_mib: int = Field(default=4096, ge=512, le=32768)
    meeting_retention_days: int = Field(default=365, ge=1)
    batch_storage_dir: str = "data/datasheet_batches"
    batch_upload_mib: int = Field(default=100, ge=1, le=1024)
    batch_expanded_mib: int = Field(default=500, ge=1, le=4096)
    batch_max_files: int = Field(default=1000, ge=2, le=10000)
    batch_max_products: int = Field(default=500, ge=1, le=5000)
    batch_max_ratio: int = Field(default=200, ge=1, le=1000)
    batch_concurrency: int = Field(default=1, ge=1, le=8)
    batch_timeout_seconds: int = Field(default=900, ge=30, le=7200)
    batch_max_attempts: int = Field(default=3, ge=1, le=5)
    batch_retention_days: int = Field(default=90, ge=1, le=3650)
    # Pauta Semanal: read-only GitHub metadata (token stays in the backend; fine-grained, read-only scopes).
    github_token: SecretStr = Field(default=SecretStr(""), repr=False)
    github_repository: str = "Arthur-A-C/PRM"
    github_api_url: str = "https://api.github.com"
    github_timeout_seconds: int = Field(default=20, ge=5, le=120)
    # Commit running in production, set at deployment. Only this proves "implantado".
    deployed_commit: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()

