"""Application settings: YAML file overlaid by environment, with coherence checks.

Precedence is ``env > YAML > defaults``. Environment variables use the
``MAILSIEVE_`` prefix and ``__`` to descend into nested keys, e.g.
``MAILSIEVE_DATABASE__POSTGRES__HOST``. The config file path comes from
``MAILSIEVE_CONFIG_FILE`` (default ``/config/config.yaml``).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote_plus

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

DEFAULT_CONFIG_FILE = "/config/config.yaml"

# Set by load_settings() to point the YAML source at a specific file. When None,
# the source falls back to MAILSIEVE_CONFIG_FILE then DEFAULT_CONFIG_FILE.
_config_path_override: str | None = None


class ConfigError(Exception):
    """Raised when configuration is missing, malformed, or internally incoherent."""


# --------------------------------------------------------------------------- #
# Nested configuration models
# --------------------------------------------------------------------------- #
class ServerCfg(BaseModel):
    host: str = "0.0.0.0"  # noqa: S104 - binding all interfaces is intended for a container service
    port: int = 8080
    base_path: str = ""


class SqliteCfg(BaseModel):
    path: str = "/data/mailsieve.db"


class PostgresCfg(BaseModel):
    host: str = "localhost"
    port: int = 5432
    user: str = "mailsieve"
    password: str = ""
    database: str = "mailsieve"
    sslmode: str = "prefer"


class MysqlCfg(BaseModel):
    host: str = "localhost"
    port: int = 3306
    user: str = "mailsieve"
    password: str = ""
    database: str = "mailsieve"


class DatabaseCfg(BaseModel):
    type: Literal["sqlite", "postgres", "mysql"] = "sqlite"
    sqlite: SqliteCfg = SqliteCfg()
    postgres: PostgresCfg = PostgresCfg()
    mysql: MysqlCfg = MysqlCfg()
    pool_size: int = 5
    echo: bool = False


class RedisCfg(BaseModel):
    # Disabled for now: the request flow is DB -> provider with no cache layer.
    # Re-enable to put Redis back in front of the database.
    enabled: bool = False
    url: str = "redis://localhost:6379/0"
    password: str = ""
    key_prefix: str = "mailsieve:v1"


class ValidationCfg(BaseModel):
    ttl_days: int = 30


class SecretCfg(BaseModel):
    ttl_minutes: int = 30
    refresh_on_reject: bool = True


class ProxiesCfg(BaseModel):
    enabled: bool = True
    source_url: str = (
        "https://api.proxyscrape.com/v4/free-proxy-list/get"
        "?request=get_proxies&skip=0&proxy_format=protocolipport"
        "&format=json&protocol=http&limit=200"
    )
    protocol: str = "http"
    max: int = 200
    refresh_minutes: int = 10


class RequestCfg(BaseModel):
    timeout_seconds: float = 15.0
    max_retries: int = 5
    backoff_seconds: float = 0.5


class PolitenessCfg(BaseModel):
    max_concurrent: int = 4
    min_interval_seconds: float = 0.5


class MailboxlayerCfg(BaseModel):
    base_url: str = "https://mailboxlayer.com"
    secret_url: str = "https://mailboxlayer.com/"  # noqa: S105 - a URL, not a credential
    secret_input_name: str = "scl_request_secret"  # noqa: S105 - a form field name
    api_path: str = "/php_helper_scripts/email_api_n.php"
    smtp: int = 1
    secret: SecretCfg = SecretCfg()
    proxies: ProxiesCfg = ProxiesCfg()
    user_agents_file: str = ""
    request: RequestCfg = RequestCfg()
    politeness: PolitenessCfg = PolitenessCfg()


class ApiAuthCfg(BaseModel):
    enabled: bool = False


class UiAuthCfg(BaseModel):
    enabled: bool = False
    username: str = "admin"
    password: str = ""


class AuthCfg(BaseModel):
    api: ApiAuthCfg = ApiAuthCfg()
    ui: UiAuthCfg = UiAuthCfg()


class BackupCfg(BaseModel):
    directory: str = "/data/backups"
    max_upload_mb: int = 256


class LoggingCfg(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Field is aliased so YAML/env key stays "json" without shadowing BaseModel.json.
    json_logs: bool = Field(default=False, alias="json")


# --------------------------------------------------------------------------- #
# YAML settings source
# --------------------------------------------------------------------------- #
def _resolve_config_path() -> str:
    if _config_path_override is not None:
        return _config_path_override
    return os.getenv("MAILSIEVE_CONFIG_FILE", DEFAULT_CONFIG_FILE)


def _load_yaml() -> dict[str, Any]:
    path = Path(_resolve_config_path())
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - exercised via ConfigError path
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"config file {path} must contain a mapping at the top level")
    return data


class YamlConfigSource(PydanticBaseSettingsSource):
    """Reads the YAML config file and exposes it as a lower-priority source."""

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        self._data = _load_yaml()

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return self._data.get(field_name), field_name, False

    def __call__(self) -> dict[str, Any]:
        return self._data


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MAILSIEVE_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    server: ServerCfg = ServerCfg()
    database: DatabaseCfg = DatabaseCfg()
    redis: RedisCfg = RedisCfg()
    validation: ValidationCfg = ValidationCfg()
    mailboxlayer: MailboxlayerCfg = MailboxlayerCfg()
    auth: AuthCfg = AuthCfg()
    backup: BackupCfg = BackupCfg()
    logging: LoggingCfg = LoggingCfg()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Priority high -> low: explicit init, env, dotenv, YAML file.
        return (init_settings, env_settings, dotenv_settings, YamlConfigSource(settings_cls))

    @model_validator(mode="after")
    def _check_coherence(self) -> Settings:
        if self.auth.ui.enabled and not self.auth.ui.password:
            raise ValueError("auth.ui.enabled is true but auth.ui.password is empty")
        return self

    def database_url(self) -> str:
        db = self.database
        if db.type == "sqlite":
            return f"sqlite+aiosqlite:///{db.sqlite.path}"
        if db.type == "postgres":
            p = db.postgres
            return (
                f"postgresql+asyncpg://{quote_plus(p.user)}:{quote_plus(p.password)}"
                f"@{p.host}:{p.port}/{p.database}"
            )
        m = db.mysql
        return (
            f"mysql+aiomysql://{quote_plus(m.user)}:{quote_plus(m.password)}"
            f"@{m.host}:{m.port}/{m.database}"
        )


def load_settings(path: str | None = None) -> Settings:
    """Build a Settings instance, failing loudly on malformed or incoherent config."""
    global _config_path_override
    _config_path_override = path
    try:
        return Settings()
    except ValidationError as exc:
        raise ConfigError(str(exc)) from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton for dependency injection."""
    return load_settings()
