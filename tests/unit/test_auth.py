import base64

from app.auth.api_key import extract_api_token, hash_secret, verify_secret
from app.auth.basic import verify_basic
from app.auth.exposure import admin_exposure_ok, is_loopback
from app.config import load_settings


def test_hash_and_verify_secret():
    h = hash_secret("s3cret-token")
    assert verify_secret("s3cret-token", h) is True
    assert verify_secret("wrong", h) is False
    assert verify_secret("", h) is False


def test_extract_api_token_bearer_and_apikey():
    assert extract_api_token({"Authorization": "Bearer abc123"}) == "abc123"
    assert extract_api_token({"X-API-Key": "xyz"}) == "xyz"
    assert extract_api_token({"Authorization": "Basic zzz"}) is None
    assert extract_api_token({}) is None


def test_verify_basic():
    pw_hash = hash_secret("hunter2")
    header = "Basic " + base64.b64encode(b"admin:hunter2").decode()
    assert verify_basic(header, "admin", pw_hash) is True
    bad = "Basic " + base64.b64encode(b"admin:nope").decode()
    assert verify_basic(bad, "admin", pw_hash) is False
    assert verify_basic(None, "admin", pw_hash) is False


def test_is_loopback():
    assert is_loopback("127.0.0.1") is True
    assert is_loopback("::1") is True
    assert is_loopback("localhost") is True
    assert is_loopback("0.0.0.0") is False  # noqa: S104
    assert is_loopback("10.0.0.5") is False


def test_admin_exposure_ok(tmp_path, monkeypatch):
    monkeypatch.delenv("MAILSIEVE_CONFIG_FILE", raising=False)
    # Both auth off + bind 0.0.0.0 -> not ok.
    s = load_settings(str(tmp_path / "none.yaml"))
    assert admin_exposure_ok(s) is False

    cfg = tmp_path / "loop.yaml"
    cfg.write_text("server:\n  host: 127.0.0.1\n")
    monkeypatch.setenv("MAILSIEVE_CONFIG_FILE", str(cfg))
    assert admin_exposure_ok(load_settings()) is True

    cfg2 = tmp_path / "api.yaml"
    cfg2.write_text("auth:\n  api:\n    enabled: true\n")
    monkeypatch.setenv("MAILSIEVE_CONFIG_FILE", str(cfg2))
    assert admin_exposure_ok(load_settings()) is True
