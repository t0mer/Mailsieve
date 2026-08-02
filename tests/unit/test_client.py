import httpx
import pytest
import respx

from app.providers.mailboxlayer.client import UpstreamClient, UpstreamError
from app.providers.mailboxlayer.politeness import Politeness
from app.providers.mailboxlayer.proxies import ProxyPool
from app.providers.mailboxlayer.useragents import UserAgents

URL = "https://api.test/verify"


def _agents():
    return UserAgents()  # bundled pool


def _pool(entries=None):
    pool = ProxyPool("https://p.test/list", "http", 200, http_factory=lambda: httpx.AsyncClient())
    pool._refreshed_at = float("inf")  # never stale -> ensure_fresh() is a no-op in tests
    if entries:
        pool._live = list(entries)  # test seam
    return pool


async def _nosleep(_d):  # keep tests fast
    return None


def _client(pool, *, max_retries=3, client_factory=None):
    return UpstreamClient(
        pool,
        _agents(),
        timeout_seconds=5,
        max_retries=max_retries,
        backoff_seconds=0,
        politeness=Politeness(4, 0),
        sleep=_nosleep,
        client_factory=client_factory,
    )


@respx.mock
async def test_direct_is_the_primary_path():
    # With proxies available, the first attempt is still DIRECT (fast path); the
    # proxy pool is not touched when the direct request succeeds.
    respx.get(URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    used: list[str | None] = []

    def factory(proxy):
        used.append(proxy)
        return httpx.AsyncClient()

    pool = _pool(["http://1.1.1.1:80"])
    client = _client(pool, client_factory=factory)
    data = await client.get_json(URL, {"email_address": "a@b.com"})
    assert data == {"ok": True}
    assert used == [None]  # direct only
    assert pool.count() == 1  # proxy pool untouched


@respx.mock
async def test_plus_addressing_reaches_endpoint_unfiltered():
    route = respx.get(URL).mock(return_value=httpx.Response(200, json={"format_valid": True}))
    client = _client(_pool())
    data = await client.get_json(URL, {"email_address": "user+tag@example.com", "secret_key": "k"})
    assert data == {"format_valid": True}
    req = route.calls.last.request
    assert req.url.params["email_address"] == "user+tag@example.com"


@respx.mock
async def test_direct_failure_falls_back_to_a_proxy():
    # If the direct request fails (e.g. the IP is blocked), rotate to proxies.
    route = respx.get(URL).mock(
        side_effect=[httpx.ConnectError("blocked"), httpx.Response(200, json={"ok": True})]
    )
    used: list[str | None] = []

    def factory(proxy):
        used.append(proxy)
        return httpx.AsyncClient()

    pool = _pool(["http://1.1.1.1:80", "http://2.2.2.2:80"])
    client = _client(pool, max_retries=2, client_factory=factory)  # attempt0 direct, attempt1 proxy
    data = await client.get_json(URL, {"secret_key": "k"})
    assert data == {"ok": True}
    assert used[0] is None  # direct first
    assert used[1] is not None  # then a proxy
    assert route.call_count == 2
    assert pool.count() == 2  # direct failed, the proxy succeeded — none marked bad


def test_proxy_attempts_get_a_shorter_bounded_timeout():
    client = UpstreamClient(
        _pool(),
        _agents(),
        timeout_seconds=15,
        max_retries=1,
        backoff_seconds=0,
        politeness=Politeness(4, 0),
        sleep=_nosleep,
    )
    assert client._attempt_timeout(None) == 15  # direct keeps full timeout
    proxy_t = client._attempt_timeout("http://1.1.1.1:80")
    assert proxy_t <= 6  # proxy attempts fail fast
    assert proxy_t < client._attempt_timeout(None)


@respx.mock
async def test_non_json_body_is_a_failure():
    respx.get(URL).mock(return_value=httpx.Response(200, text="<html>not json</html>"))
    client = _client(_pool(), max_retries=2)
    with pytest.raises(UpstreamError):
        await client.get_json(URL, {"secret_key": "k"})
