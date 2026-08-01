from app.db import repository as repo
from app.db.session import session_scope
from app.services.history_service import HistoryService

BASE = {
    "email": "a@b.com",
    "verdict": "deliverable",
    "score": 0.9,
    "format_valid": True,
    "mx_found": True,
    "smtp_check": True,
    "catch_all": None,
    "checked_at": "t",
}


async def _seed(sm, email, payload):
    async with session_scope(sm) as s:
        await repo.insert_if_changed(s, email, payload, repo.result_hash(payload))


async def test_list_history_paginates_and_counts_revisions(sessionmaker_mem):
    await _seed(sessionmaker_mem, "a@b.com", {**BASE, "checked_at": "t1"})
    await _seed(sessionmaker_mem, "a@b.com", {**BASE, "score": 0.1, "checked_at": "t2"})
    await _seed(sessionmaker_mem, "c@d.com", {**BASE, "email": "c@d.com"})

    svc = HistoryService(sessionmaker_mem)
    page = await svc.list_history(
        limit=10000, offset=0, sort="created_at", order="desc", search=None
    )
    assert page["total"] == 3
    assert page["limit"] == 250  # clamped
    a_items = [it for it in page["items"] if it["email"] == "a@b.com"]
    assert all(it["revision_count"] == 2 for it in a_items)


async def test_diff_highlights_changed_fields(sessionmaker_mem):
    await _seed(sessionmaker_mem, "a@b.com", {**BASE, "score": 0.9, "checked_at": "t1"})
    await _seed(sessionmaker_mem, "a@b.com", {**BASE, "score": 0.1, "checked_at": "t2"})
    svc = HistoryService(sessionmaker_mem)
    revs = await svc.history_for("a@b.com")
    assert len(revs) == 2
    ids = sorted(r["id"] for r in revs)
    diff = await svc.diff("a@b.com", ids[0], ids[1])
    assert "score" in diff["changed"]
    assert diff["changed"]["score"] == {"from": 0.9, "to": 0.1}
    assert "checked_at" not in diff["changed"]  # volatile ignored
    assert len(diff["timeline"]) == 2
