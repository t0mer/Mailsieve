import httpx
import respx

from app.providers.mailboxlayer.proxies import ProxyPool

SRC = "https://proxies.test/list"
PAYLOAD = {
    "proxies": [
        {"ip": "1.1.1.1", "port": 8080, "protocol": "http"},
        {"ip": "2.2.2.2", "port": 3128, "protocol": "http"},
        {"ip": "3.3.3.3", "port": 9999, "protocol": "socks5"},  # filtered out
    ]
}


def _make(max_proxies=200):
    return ProxyPool(
        SRC,
        "http",
        max_proxies,
        http_factory=lambda: httpx.AsyncClient(),
    )


@respx.mock
async def test_refresh_parses_and_filters_by_protocol():
    respx.get(SRC).mock(return_value=httpx.Response(200, json=PAYLOAD))
    pool = _make()
    await pool.refresh()
    assert pool.count() == 2  # socks5 dropped
    assert pool.pick() in {"http://1.1.1.1:8080", "http://2.2.2.2:3128"}


@respx.mock
async def test_refresh_caps_at_max():
    respx.get(SRC).mock(return_value=httpx.Response(200, json=PAYLOAD))
    pool = _make(max_proxies=1)
    await pool.refresh()
    assert pool.count() == 1


@respx.mock
async def test_mark_bad_removes_from_rotation():
    respx.get(SRC).mock(return_value=httpx.Response(200, json=PAYLOAD))
    pool = _make()
    await pool.refresh()
    first = pool.pick()
    assert first is not None
    pool.mark_bad(first)
    assert pool.count() == 1
    for _ in range(10):
        assert pool.pick() != first


async def test_empty_pool_pick_is_none():
    pool = _make()
    assert pool.pick() is None
    assert pool.count() == 0


async def test_disabled_pool_never_fetches():
    pool = ProxyPool(SRC, "http", 200, enabled=False, http_factory=lambda: httpx.AsyncClient())
    await pool.ensure_fresh()  # no network call, no error
    assert pool.count() == 0
    assert pool.pick() is None
