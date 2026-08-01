import httpx
import pytest
import respx

from app.providers.mailboxlayer.secret import SecretProvider, SecretUnavailable

URL = "https://mb.test/home"
HTML_OK = (
    '<html><body><input type="hidden" '
    'name="scl_request_secret" value="SEEKRIT"></body></html>'
)
HTML_NO_INPUT = "<html><body><p>nothing here</p></body></html>"


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _make(clock=None, ttl_minutes=30.0):
    return SecretProvider(
        URL,
        "scl_request_secret",
        ttl_minutes,
        http_factory=lambda: httpx.AsyncClient(),
        clock=clock,
    )


def test_parse_secret_from_html():
    sp = _make()
    assert sp.parse_secret(HTML_OK) == "SEEKRIT"


def test_parse_secret_missing_returns_none():
    sp = _make()
    assert sp.parse_secret(HTML_NO_INPUT) is None


@respx.mock
async def test_get_fetches_once_when_fresh():
    route = respx.get(URL).mock(return_value=httpx.Response(200, text=HTML_OK))
    sp = _make()
    assert await sp.get() == "SEEKRIT"
    assert await sp.get() == "SEEKRIT"  # cached, no second fetch
    assert route.call_count == 1
    assert sp.ok is True


@respx.mock
async def test_expired_ttl_triggers_one_refetch():
    route = respx.get(URL).mock(return_value=httpx.Response(200, text=HTML_OK))
    clock = FakeClock()
    sp = _make(clock=clock, ttl_minutes=1.0)  # 60s ttl
    await sp.get()
    clock.t = 120.0  # advance past ttl
    await sp.get()
    assert route.call_count == 2


@respx.mock
async def test_single_flight_collapses_concurrent_bursts():
    import asyncio

    route = respx.get(URL).mock(return_value=httpx.Response(200, text=HTML_OK))
    sp = _make()
    results = await asyncio.gather(*(sp.get() for _ in range(10)))
    assert results == ["SEEKRIT"] * 10
    assert route.call_count == 1


@respx.mock
async def test_missing_input_raises_unavailable():
    respx.get(URL).mock(return_value=httpx.Response(200, text=HTML_NO_INPUT))
    sp = _make()
    with pytest.raises(SecretUnavailable):
        await sp.get()
    assert sp.ok is False
    assert sp.last_error is not None
