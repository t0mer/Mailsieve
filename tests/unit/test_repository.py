from app.db.repository import (
    MAX_PAGE,
    clamp_limit,
    insert_if_changed,
    latest,
    paginate,
    record_event,
    result_hash,
    revisions,
)

BASE = {
    "email": "a@b.com",
    "format_valid": True,
    "mx_found": True,
    "smtp_check": True,
    "catch_all": None,
    "score": 0.9,
}


# --- pure hashing ---------------------------------------------------------- #
def test_hash_ignores_volatile_fields():
    a = {**BASE, "checked_at": "t1", "cached": False, "source": "provider"}
    b = {**BASE, "checked_at": "t2", "cached": True, "source": "cache"}
    assert result_hash(a) == result_hash(b)


def test_hash_changes_on_real_field():
    a = {**BASE, "checked_at": "t1"}
    b = {**BASE, "score": 0.1, "checked_at": "t1"}
    assert result_hash(a) != result_hash(b)


def test_clamp_limit():
    assert clamp_limit(10000) == MAX_PAGE
    assert clamp_limit(0) == 1
    assert clamp_limit(-5) == 1
    assert clamp_limit(50) == 50


# --- change detection ------------------------------------------------------ #
async def test_insert_if_changed_no_dupe(session):
    p1 = {**BASE, "checked_at": "t1"}
    p2 = {**BASE, "checked_at": "t2"}  # only volatile field differs
    await insert_if_changed(session, "a@b.com", p1, result_hash(p1))
    await insert_if_changed(session, "a@b.com", p2, result_hash(p2))
    rows = await revisions(session, "a@b.com")
    assert len(rows) == 1


async def test_insert_if_changed_appends_on_change(session):
    p1 = {**BASE, "checked_at": "t1"}
    p2 = {**BASE, "score": 0.1, "checked_at": "t2"}
    await insert_if_changed(session, "a@b.com", p1, result_hash(p1))
    await insert_if_changed(session, "a@b.com", p2, result_hash(p2))
    rows = await revisions(session, "a@b.com")
    assert len(rows) == 2


async def test_record_event_and_latest(session):
    p = {**BASE, "checked_at": "t1"}
    row = await insert_if_changed(session, "a@b.com", p, result_hash(p))
    await record_event(session, "a@b.com", row.id, "api", cache_hit=False)
    got = await latest(session, "a@b.com")
    assert got is not None and got.id == row.id


# --- pagination ------------------------------------------------------------ #
async def test_paginate_clamp_and_search(session):
    for addr in ["alice@x.com", "bob@x.com", "alice@y.com"]:
        p = {**BASE, "email": addr, "checked_at": "t"}
        await insert_if_changed(session, addr, p, result_hash(p))
    # Oversized limit must not error and must not exceed clamp.
    rows, total = await paginate(
        session, limit=10000, offset=0, sort="created_at", order="desc", search=None
    )
    assert total == 3
    assert len(rows) <= MAX_PAGE
    # Case-insensitive search on email.
    rows, total = await paginate(
        session, limit=50, offset=0, sort="email", order="asc", search="ALICE"
    )
    assert total == 2
    assert [r.email for r in rows] == ["alice@x.com", "alice@y.com"]
