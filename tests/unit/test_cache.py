from redis.exceptions import ConnectionError as RedisConnectionError

from app.cache.redis_cache import Cache
from app.config import RedisCfg


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def delete(self, key):
        self.store.pop(key, None)


class RaisingRedis:
    async def get(self, key):
        raise RedisConnectionError("down")

    async def set(self, key, value, ex=None):
        raise RedisConnectionError("down")

    async def delete(self, key):
        raise RedisConnectionError("down")


async def test_set_get_roundtrip():
    c = Cache(RedisCfg(enabled=True), client=FakeRedis())
    await c.set("a@b.com", {"x": 1}, 60)
    assert await c.get("a@b.com") == {"x": 1}


async def test_redis_error_degrades_gracefully():
    c = Cache(RedisCfg(enabled=True), client=RaisingRedis())
    assert await c.get("a@b.com") is None  # no raise
    await c.set("a@b.com", {"x": 1}, 60)  # no raise
    await c.delete("a@b.com")  # no raise


async def test_disabled_is_noop():
    c = Cache(RedisCfg(enabled=False))
    assert await c.get("x@y.com") is None
    await c.set("x@y.com", {"a": 1}, 60)
    assert await c.get("x@y.com") is None


def test_key_includes_prefix_and_hashes_email():
    c = Cache(RedisCfg(enabled=False, key_prefix="pfx"))
    key = c.key_for("a@b.com")
    assert key.startswith("pfx:result:")
    assert "a@b.com" not in key  # email is hashed, not embedded
