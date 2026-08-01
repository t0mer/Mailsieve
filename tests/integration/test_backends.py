"""Cross-backend integration suite (§11).

Runs the append-only invariants against sqlite, postgres, and mysql. Backends
that are not reachable (e.g. locally without Postgres/MySQL running) are skipped;
CI provides all three as services.
"""

import os

import pytest
import pytest_asyncio
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.cache.redis_cache import Cache
from app.config import RedisCfg
from app.db import repository as repo
from app.db.models import Base
from app.db.session import session_scope
from app.providers.mailboxlayer.mapping import to_schema
from app.services.validation_service import ValidationService

pytestmark = pytest.mark.integration

_PG = os.getenv(
    "MAILSIEVE_IT_POSTGRES_URL",
    "postgresql+asyncpg://mailsieve:mailsieve@localhost:5432/mailsieve",
)
_MYSQL = os.getenv(
    "MAILSIEVE_IT_MYSQL_URL",
    "mysql+aiomysql://mailsieve:mailsieve@localhost:3306/mailsieve",
)

RAW = {
    "email": "a@b.com",
    "did_you_mean": "",
    "user": "a",
    "domain": "b.com",
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
    return {**to_schema(RAW, "a@b.com", "a@b.com"), **over}


class RaisingRedis:
    async def get(self, key):
        raise RedisConnectionError("redis down")

    async def set(self, key, value, ex=None):
        raise RedisConnectionError("redis down")


class StubProvider:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    async def validate(self, email, email_raw):
        self.calls += 1
        return {**self.payload}

    async def health(self):  # pragma: no cover
        raise NotImplementedError


@pytest_asyncio.fixture(params=["sqlite", "postgres", "mysql"])
async def backend_sm(request, tmp_path):
    name = request.param
    url = f"sqlite+aiosqlite:///{tmp_path / 'it.db'}" if name == "sqlite" else (
        _PG if name == "postgres" else _MYSQL
    )
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:  # noqa: BLE001 - unreachable backend => skip
        await engine.dispose()
        pytest.skip(f"{name} backend not available: {exc}")
    sm = async_sessionmaker(engine, expire_on_commit=False)
    yield sm
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_change_detection_across_backends(backend_sm):
    p1 = _payload(checked_at="t1")
    p2 = _payload(checked_at="t2")  # only volatile differs
    p3 = _payload(score=0.1, checked_at="t3")
    async with session_scope(backend_sm) as s:
        await repo.insert_if_changed(s, "a@b.com", p1, repo.result_hash(p1))
        await repo.insert_if_changed(s, "a@b.com", p2, repo.result_hash(p2))
    async with session_scope(backend_sm) as s:
        assert len(await repo.revisions(s, "a@b.com")) == 1  # unchanged: no new row
        await repo.insert_if_changed(s, "a@b.com", p3, repo.result_hash(p3))
    async with session_scope(backend_sm) as s:
        assert len(await repo.revisions(s, "a@b.com")) == 2  # changed: appended


async def test_pagination_clamped_across_backends(backend_sm):
    async with session_scope(backend_sm) as s:
        for i in range(3):
            p = _payload(email=f"u{i}@x.com")
            await repo.insert_if_changed(s, f"u{i}@x.com", p, repo.result_hash(p))
    async with session_scope(backend_sm) as s:
        rows, total = await repo.paginate(
            s, limit=10000, offset=0, sort="created_at", order="desc", search=None
        )
    assert total == 3
    assert len(rows) <= repo.MAX_PAGE


async def test_redis_down_still_serves_from_db(backend_sm):
    provider = StubProvider(_payload())
    cache = Cache(RedisCfg(enabled=True), client=RaisingRedis())
    svc = ValidationService(backend_sm, cache, provider, ttl_days=30)
    r1 = await svc.validate("a@b.com", source="api")
    assert r1.source == "provider"  # first call: cache miss (redis down) -> provider
    r2 = await svc.validate("a@b.com", source="api")
    assert r2.source == "db"  # second: redis still down, served from DB, provider not re-called
    assert provider.calls == 1
