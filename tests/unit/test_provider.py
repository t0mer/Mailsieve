import hashlib

import httpx
import respx

from app.config import load_settings
from app.providers.mailboxlayer.provider import MailboxlayerProvider

HOME = "https://mb.test/home"
API = "https://mb.test/verify"
HTML_OK = (
    '<html><body><input type="hidden" '
    'name="scl_request_secret" value="SEEKRIT"></body></html>'
)
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

CONFIG = """
mailboxlayer:
  base_url: https://mb.test
  secret_url: https://mb.test/home
  api_path: /verify
  proxies:
    enabled: false
    fallback_direct: true
  request:
    max_retries: 2
    backoff_seconds: 0
    timeout_seconds: 5
  politeness:
    max_concurrent: 4
    min_interval_seconds: 0
"""


def _settings(tmp_path, monkeypatch):
    p = tmp_path / "c.yaml"
    p.write_text(CONFIG)
    monkeypatch.setenv("MAILSIEVE_CONFIG_FILE", str(p))
    return load_settings()


@respx.mock
async def test_validate_happy_path_and_md5_key(tmp_path, monkeypatch):
    respx.get(HOME).mock(return_value=httpx.Response(200, text=HTML_OK))
    api = respx.get(API).mock(return_value=httpx.Response(200, json=VALID_JSON))
    prov = MailboxlayerProvider(_settings(tmp_path, monkeypatch))

    r = await prov.validate("u@e.com", "U@E.com")
    assert r["verdict"] == "deliverable"
    assert r["did_you_mean"] is None
    assert r["email_raw"] == "U@E.com"

    expected_key = hashlib.md5(("u@e.com" + "SEEKRIT").encode()).hexdigest()  # noqa: S324
    assert api.calls.last.request.url.params["secret_key"] == expected_key


@respx.mock
async def test_bad_secret_triggers_one_refresh_and_retry(tmp_path, monkeypatch):
    home = respx.get(HOME).mock(return_value=httpx.Response(200, text=HTML_OK))
    api = respx.get(API).mock(
        side_effect=[
            httpx.Response(200, json={"success": False, "error": {"code": 101}}),
            httpx.Response(200, json=VALID_JSON),
        ]
    )
    prov = MailboxlayerProvider(_settings(tmp_path, monkeypatch))
    r = await prov.validate("u@e.com", "U@E.com")
    assert r["verdict"] == "deliverable"
    assert api.call_count == 2  # one retry
    assert home.call_count == 2  # initial + forced refresh


async def test_syntax_gate_blocks_garbage_without_network(tmp_path, monkeypatch):
    prov = MailboxlayerProvider(_settings(tmp_path, monkeypatch))
    r = await prov.validate("notanemail", "notanemail")
    assert r["verdict"] == "undeliverable"
