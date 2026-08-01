import pytest

from app.config import ConfigError, load_settings


def test_env_overrides_yaml(tmp_path, monkeypatch):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("database:\n  type: sqlite\nserver:\n  port: 8080\n")
    monkeypatch.setenv("MAILSIEVE_CONFIG_FILE", str(cfg))
    monkeypatch.setenv("MAILSIEVE_SERVER__PORT", "9999")
    s = load_settings()
    assert s.server.port == 9999  # env wins
    assert s.database.type == "sqlite"  # yaml provides


def test_yaml_deep_merge_preserves_siblings(tmp_path, monkeypatch):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        "database:\n"
        "  type: postgres\n"
        "  postgres:\n"
        "    host: db.internal\n"
        "    database: mydb\n"
    )
    monkeypatch.setenv("MAILSIEVE_CONFIG_FILE", str(cfg))
    # Override only one nested field via env; siblings from yaml must survive.
    monkeypatch.setenv("MAILSIEVE_DATABASE__POSTGRES__PASSWORD", "secretpw")
    s = load_settings()
    assert s.database.postgres.host == "db.internal"  # yaml preserved
    assert s.database.postgres.database == "mydb"  # yaml preserved
    assert s.database.postgres.password == "secretpw"  # env applied


def test_sqlite_url(monkeypatch, tmp_path):
    monkeypatch.delenv("MAILSIEVE_CONFIG_FILE", raising=False)
    s = load_settings(str(tmp_path / "none.yaml"))
    assert s.database_url().startswith("sqlite+aiosqlite:///")


def test_postgres_url(monkeypatch, tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        "database:\n"
        "  type: postgres\n"
        "  postgres:\n"
        "    host: h\n"
        "    port: 5432\n"
        "    user: u\n"
        "    password: 'p@ss word'\n"
        "    database: d\n"
    )
    monkeypatch.setenv("MAILSIEVE_CONFIG_FILE", str(cfg))
    url = load_settings().database_url()
    assert url.startswith("postgresql+asyncpg://u:")
    assert "@h:5432/d" in url
    assert "p%40ss" in url  # password url-encoded


def test_incoherent_proxies_raises(tmp_path, monkeypatch):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        "mailboxlayer:\n  proxies:\n    enabled: false\n    fallback_direct: false\n"
    )
    monkeypatch.setenv("MAILSIEVE_CONFIG_FILE", str(cfg))
    with pytest.raises(ConfigError):
        load_settings()


def test_ui_auth_without_password_raises(tmp_path, monkeypatch):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("auth:\n  ui:\n    enabled: true\n    password: ''\n")
    monkeypatch.setenv("MAILSIEVE_CONFIG_FILE", str(cfg))
    with pytest.raises(ConfigError):
        load_settings()


def test_unknown_database_type_raises(tmp_path, monkeypatch):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("database:\n  type: mongodb\n")
    monkeypatch.setenv("MAILSIEVE_CONFIG_FILE", str(cfg))
    with pytest.raises(ConfigError):
        load_settings()


def test_defaults_when_no_file(monkeypatch, tmp_path):
    monkeypatch.delenv("MAILSIEVE_CONFIG_FILE", raising=False)
    s = load_settings(str(tmp_path / "absent.yaml"))
    assert s.server.host == "0.0.0.0"  # noqa: S104 - asserting the documented default
    assert s.mailboxlayer.politeness.max_concurrent == 4
    assert s.validation.ttl_days == 30
