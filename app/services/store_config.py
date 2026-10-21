"""Backend-only credentials; exact env names plus legacy Woo aliases."""
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
COMPANIES = ("choice", "sag", "portwell")


class StoreSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")
    choice_url: str = Field("https://choicetech.com.br", validation_alias=AliasChoices("CHOICE_WC_URL", "PRM_WOO_CHOICE_URL"))
    choice_key: SecretStr = Field(default=SecretStr(""), repr=False, validation_alias=AliasChoices("CHOICE_WC_KEY", "PRM_WOO_CHOICE_KEY"))
    choice_secret: SecretStr = Field(default=SecretStr(""), repr=False, validation_alias=AliasChoices("CHOICE_WC_SECRET", "PRM_WOO_CHOICE_SECRET"))
    choice_user: SecretStr = Field(default=SecretStr(""), repr=False, validation_alias="CHOICE_WP_USER")
    choice_password: SecretStr = Field(default=SecretStr(""), repr=False, validation_alias="CHOICE_WP_APP_PASSWORD")
    sag_url: str = Field("https://sagloja.devsplcomunic.com.br", validation_alias=AliasChoices("SAG_WC_URL", "PRM_WOO_SAG_URL"))
    sag_key: SecretStr = Field(default=SecretStr(""), repr=False, validation_alias=AliasChoices("SAG_WC_KEY", "PRM_WOO_SAG_KEY"))
    sag_secret: SecretStr = Field(default=SecretStr(""), repr=False, validation_alias=AliasChoices("SAG_WC_SECRET", "PRM_WOO_SAG_SECRET"))
    sag_user: SecretStr = Field(default=SecretStr(""), repr=False, validation_alias="SAG_WP_USER")
    sag_password: SecretStr = Field(default=SecretStr(""), repr=False, validation_alias="SAG_WP_APP_PASSWORD")
    portwell_url: str = Field("https://portwell.com.br", validation_alias=AliasChoices("PORTWELL_WC_URL", "PRM_WOO_PORTWELL_URL"))
    portwell_key: SecretStr = Field(default=SecretStr(""), repr=False, validation_alias=AliasChoices("PORTWELL_WC_KEY", "PRM_WOO_PORTWELL_KEY"))
    portwell_secret: SecretStr = Field(default=SecretStr(""), repr=False, validation_alias=AliasChoices("PORTWELL_WC_SECRET", "PRM_WOO_PORTWELL_SECRET"))
    portwell_user: SecretStr = Field(default=SecretStr(""), repr=False, validation_alias="PORTWELL_WP_USER")
    portwell_password: SecretStr = Field(default=SecretStr(""), repr=False, validation_alias="PORTWELL_WP_APP_PASSWORD")
    organization_id: str = Field("", validation_alias="PRM_STORE_ORGANIZATION_ID")
    timeout: float = Field(20, ge=1, le=60, validation_alias="PRM_STORE_TIMEOUT_SECONDS")
    status_dir: str = Field("data/integrations", validation_alias="PRM_STORE_STATUS_DIR")

    def credentials(self, company, api):
        if company not in COMPANIES or api not in {"wc", "wp"}:
            raise ValueError("Empresa/API inválida.")
        url = secure_url(getattr(self, company + "_url"))
        first, second = ("key", "secret") if api == "wc" else ("user", "password")
        username = getattr(self, f"{company}_{first}").get_secret_value()
        password = getattr(self, f"{company}_{second}").get_secret_value()
        if not username.strip() or not password.strip():
            raise ValueError("Credenciais ausentes; configure as variáveis no backend.")
        return StoreCredentials(url, username, password)


def secure_url(value):
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.port not in {None, 443}):
            raise ValueError()
    except ValueError:
        raise ValueError("Configure uma URL HTTPS canônica da loja, sem usuário, senha, porta alternativa ou parâmetros.") from None
    return value.rstrip("/")


@dataclass(frozen=True)
class StoreCredentials:
    base_url: str
    username: str = field(repr=False)
    password: str = field(repr=False)
