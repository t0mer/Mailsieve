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
    if entries:
        pool._live = list(entries)  # test seam
    return pool


async def _nosleep(_d):  # keep tests fast
    return None


def _client(pool, *, max_retries=3, fallback_direct=False):
    return UpstreamClient(
        pool,
        _agents(),
        timeout_seconds=5,
        max_retries=max_retries,
        backoff_seconds=0,
        politeness=Politeness(4, 0),
        fallback_direct=fallback_direct,
        sleep=_nosleep,
    )


@respx.mock
async def test_plus_addressing_reaches_endpoint_unfiltered():
    route = respx.get(URL).mock(return_value=httpx.Response(200, json={"format_valid": True}))
    client = _client(_pool(), fallback_direct=True)  # empty pool -> direct
    data = await client.get_json(URL, {"email_address": "user+tag@example.com", "secret_key": "k"})
    assert data == {"format_valid": True}
    req = route.calls.last.request
    assert req.url.params["email_address"] == "user+tag@example.com"


@respx.mock
async def test_failing_proxy_is_dropped_and_next_attempt_differs():
    route = respx.get(URL).mock(
        side_effect=[httpx.ConnectError("boom"), httpx.Response(200, json={"ok": True})]
    )
    pool = _pool(["http://1.1.1.1:80", "http://2.2.2.2:80"])
    client = _client(pool, max_retries=3)
    data = await client.get_json(URL, {"secret_key": "k"})
    assert data == {"ok": True}
    assert route.call_count == 2
    assert pool.count() == 1  # one proxy marked bad


def test_proxy_attempts_get_a_shorter_bounded_timeout():
    client = UpstreamClient(
        _pool(),
        _agents(),
        timeout_seconds=15,
        max_retries=1,
        backoff_seconds=0,
        politeness=Politeness(4, 0),
        fallback_direct=True,
        sleep=_nosleep,
    )
    assert client._attempt_timeout(None) == 15  # direct keeps full timeout
    proxy_t = client._attempt_timeout("http://1.1.1.1:80")
    assert proxy_t <= 6  # proxy attempts fail fast
    assert proxy_t < client._attempt_timeout(None)


@respx.mock
async def test_dead_proxies_fall_back_to_direct():
    # A populated pool of dead proxies must not hang forever: after a proxy
    # failure, with fallback_direct the client issues a DIRECT request.
    route = respx.get(URL).mock(
        side_effect=[httpx.ConnectError("dead proxy"), httpx.Response(200, json={"ok": True})]
    )
    proxies_used: list[str | None] = []

    def factory(proxy):
        proxies_used.append(proxy)
        return httpx.AsyncClient()

    pool = _pool(["http://1.1.1.1:80", "http://2.2.2.2:80", "http://3.3.3.3:80"])
    client = UpstreamClient(
        pool,
        _agents(),
        timeout_seconds=5,
        max_retries=5,
        backoff_seconds=0,
        politeness=Politeness(4, 0),
        fallback_direct=True,
        client_factory=factory,
        sleep=_nosleep,
    )
    data = await client.get_json(URL, {"secret_key": "k"})
    assert data == {"ok": True}
    assert route.call_count == 2
    assert proxies_used[0] is not None  # first attempt used a proxy
    assert proxies_used[1] is None  # second attempt went direct (the fix)


@respx.mock
async def test_non_json_body_is_a_failure():
    respx.get(URL).mock(return_value=httpx.Response(200, text="<html>not json</html>"))
    client = _client(_pool(), max_retries=2, fallback_direct=True)
    with pytest.raises(UpstreamError):
        await client.get_json(URL, {"secret_key": "k"})


async def test_empty_pool_without_fallback_fails_cleanly():
    # No respx route needed: the request is never issued.
    pool = _pool()  # empty

    async def empty_refresh():
        return None

    pool.refresh = empty_refresh  # type: ignore[method-assign]
    client = _client(pool, max_retries=2, fallback_direct=False)
    with pytest.raises(UpstreamError):
        await client.get_json(URL, {"secret_key": "k"})
