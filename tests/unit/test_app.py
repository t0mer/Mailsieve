from pathlib import Path

from starlette.testclient import TestClient

from app.auth.api_key import hash_secret
from app.config import load_settings
from app.main import create_app
from app.providers.base import ProviderHealth
from app.providers.mailboxlayer.mapping import to_schema
from app.services.validation_service import ValidationService

VALID_JSON = {
    "email": "u@e.com",
    "did_you_mean": "",
    "user": "u",
    "domain": "e.com",
    "format_valid": True,
    "mx_found": True,
    "smtp_check": True,
    "catch_all": None,
    "role": False,
    "free": False,
    "disposable": False,
    "score": 0.9,
}


class StubProvider:
    def __init__(self, reachable=True):
        self._reachable = reachable

    async def validate(self, email, email_raw):
        return to_schema(VALID_JSON, email, email_raw)

    async def health(self):
        return ProviderHealth(reachable=self._reachable, secret_ok=True, proxy_count=3, detail="")


def _write_config(tmp_path: Path, *, extra: str = "") -> Path:
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        "server:\n"
        "  host: 127.0.0.1\n"  # loopback: admin routes may serve without auth in tests
        "database:\n"
        "  type: sqlite\n"
        "  sqlite:\n"
        f"    path: {tmp_path / 'app.db'}\n"
        "redis:\n"
        "  enabled: false\n"
        "mailboxlayer:\n"
        "  proxies:\n"
        "    enabled: false\n"
        "  politeness:\n"
        "    min_interval_seconds: 0\n"
        f"{extra}"
    )
    return cfg


def _stub_client(tmp_path, monkeypatch, *, extra="", static=True):
    cfg = _write_config(tmp_path, extra=extra)
    monkeypatch.setenv("MAILSIEVE_CONFIG_FILE", str(cfg))
    static_dir = tmp_path / "static"
    if static:
        static_dir.mkdir()
        (static_dir / "index.html").write_text("<html>HELLO SPA</html>")
    settings = load_settings()
    app = create_app(settings, static_dir=static_dir)
    client = TestClient(app)
    return client, app


def _install_stub(app, provider=None):
    provider = provider or StubProvider()
    app.state.provider = provider
    app.state.validation = ValidationService(
        app.state.sessionmaker, app.state.cache, provider, 30
    )


def test_health_reports_provider_reachability(tmp_path, monkeypatch):
    client, app = _stub_client(tmp_path, monkeypatch)
    with client:
        _install_stub(app)
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["provider"]["reachable"] is True
        assert body["database"]["ok"] is True


def test_validate_and_history_clamp(tmp_path, monkeypatch):
    client, app = _stub_client(tmp_path, monkeypatch)
    with client:
        _install_stub(app)
        r = client.post("/api/v1/validate", json={"email": "u@e.com"})
        assert r.status_code == 200
        body = r.json()
        assert body["verdict"] == "deliverable"
        assert body["source"] == "provider"

        h = client.get("/api/v1/history", params={"limit": 10000})
        assert h.status_code == 200
        assert h.json()["limit"] == 250  # clamped


def test_spa_fallback_does_not_shadow_api(tmp_path, monkeypatch):
    client, app = _stub_client(tmp_path, monkeypatch)
    with client:
        _install_stub(app)
        page = client.get("/dashboard")
        assert page.status_code == 200
        assert "HELLO SPA" in page.text
        # Unknown API path is a JSON 404, not index.html.
        missing = client.get("/api/v1/does-not-exist")
        assert missing.status_code == 404
        assert "HELLO SPA" not in missing.text


def test_api_auth_gate(tmp_path, monkeypatch):
    client, app = _stub_client(
        tmp_path, monkeypatch, extra="auth:\n  api:\n    enabled: true\n"
    )
    with client:
        _install_stub(app)
        app.state.api_token_hash = hash_secret("s3cret")
        assert client.get("/api/v1/history").status_code == 401
        ok = client.get("/api/v1/history", headers={"X-API-Key": "s3cret"})
        assert ok.status_code == 200


def test_rate_limit_returns_429(tmp_path, monkeypatch):
    from app.api.ratelimit import RateLimiter

    client, app = _stub_client(tmp_path, monkeypatch)
    with client:
        _install_stub(app)
        app.state.rate_limiter = RateLimiter(limit=1)
        assert client.post("/api/v1/validate", json={"email": "a@b.com"}).status_code == 200
        assert client.post("/api/v1/validate", json={"email": "a@b.com"}).status_code == 429


def test_token_rotation_shown_once(tmp_path, monkeypatch):
    client, app = _stub_client(tmp_path, monkeypatch)
    with client:
        _install_stub(app)
        r = client.post("/api/v1/settings/token")
        assert r.status_code == 200
        token = r.json()["token"]
        assert token
        # Now a fresh GET of settings must not reveal it.
        view = client.get("/api/v1/settings")
        assert token not in view.text
        assert view.json()["auth"]["api"]["token_set"] is True
