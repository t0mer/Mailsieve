from typing import Any

from app.db import repository as repo
from app.db.session import session_scope
from app.providers.mailboxlayer.mapping import to_schema
from app.services.validation_service import ValidationService, normalise

RAW_MB = {
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


def _payload(**over):
    return {**to_schema(RAW_MB, "u@e.com", "u@e.com"), **over}


class StubProvider:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    async def validate(self, email: str, email_raw: str) -> dict[str, Any]:
        self.calls += 1
        return {**self.payload}

    async def health(self):  # pragma: no cover - not used here
        raise NotImplementedError


class StubCache:
    def __init__(self):
        self.store: dict[str, dict] = {}

    async def get(self, email):
        return self.store.get(email)

    async def set(self, email, payload, ttl_seconds):
        self.store[email] = payload

    async def delete(self, email):
        self.store.pop(email, None)


def test_normalise_lowercases_domain_only():
    assert normalise("  User@Example.COM ") == "User@example.com"


async def test_cache_hit_skips_provider(sessionmaker_mem):
    provider = StubProvider(_payload())
    cache = StubCache()
    cache.store["u@e.com"] = _payload()
    svc = ValidationService(sessionmaker_mem, cache, provider, ttl_days=30)
    resp = await svc.validate("u@e.com", source="api")
    assert resp.source == "cache"
    assert resp.cached is True
    assert provider.calls == 0


async def test_db_hit_skips_provider_and_warms_cache(sessionmaker_mem):
    provider = StubProvider(_payload())
    cache = StubCache()
    # Pre-insert a fresh row, leave cache empty.
    async with session_scope(sessionmaker_mem) as s:
        p = _payload()
        await repo.insert_if_changed(s, "u@e.com", p, repo.result_hash(p))
    svc = ValidationService(sessionmaker_mem, cache, provider, ttl_days=30)
    resp = await svc.validate("u@e.com", source="api")
    assert resp.source == "db"
    assert provider.calls == 0
    assert "u@e.com" in cache.store  # warmed


async def test_miss_calls_provider_and_records(sessionmaker_mem):
    provider = StubProvider(_payload())
    cache = StubCache()
    svc = ValidationService(sessionmaker_mem, cache, provider, ttl_days=30)
    resp = await svc.validate("u@e.com", source="api")
    assert resp.source == "provider"
    assert provider.calls == 1
    async with session_scope(sessionmaker_mem) as s:
        rows = await repo.revisions(s, "u@e.com")
        assert len(rows) == 1


async def test_force_bypasses_cache_and_db(sessionmaker_mem):
    provider = StubProvider(_payload())
    cache = StubCache()
    cache.store["u@e.com"] = _payload()  # would be a hit without force
    svc = ValidationService(sessionmaker_mem, cache, provider, ttl_days=30)
    resp = await svc.validate("u@e.com", source="api", force=True)
    assert resp.source == "provider"
    assert provider.calls == 1


async def test_unchanged_revalidation_adds_no_row(sessionmaker_mem):
    provider = StubProvider(_payload())
    cache = StubCache()
    svc = ValidationService(sessionmaker_mem, cache, provider, ttl_days=30)
    await svc.validate("u@e.com", source="api", force=True)
    await svc.validate("u@e.com", source="api", force=True)  # identical result
    async with session_scope(sessionmaker_mem) as s:
        rows = await repo.revisions(s, "u@e.com")
        assert len(rows) == 1
