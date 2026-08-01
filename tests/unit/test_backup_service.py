import io
import tarfile

import pytest

from app.db import repository as repo
from app.db.session import session_scope
from app.services.backup_service import RESTORE_CONFIRM, BackupError, BackupService

PAYLOAD = {
    "email": "a@b.com",
    "verdict": "deliverable",
    "score": 0.9,
    "format_valid": True,
    "checked_at": "t",
}


def _svc(sm, tmp_path):
    return BackupService(
        sm, directory=str(tmp_path / "backups"), max_upload_mb=256, backend="sqlite"
    )


async def _seed(sm):
    async with session_scope(sm) as s:
        row = await repo.insert_if_changed(s, "a@b.com", PAYLOAD, repo.result_hash(PAYLOAD))
        await repo.record_event(s, "a@b.com", row.id, "api", cache_hit=False)


async def test_backup_restore_roundtrip(sessionmaker_mem, sessionmaker_mem2, tmp_path):
    await _seed(sessionmaker_mem)
    src = _svc(sessionmaker_mem, tmp_path)
    archive = tmp_path / "b.tar.gz"
    archive.write_bytes(await src.make_backup())

    dst = _svc(sessionmaker_mem2, tmp_path)
    await dst.restore(str(archive), RESTORE_CONFIRM)

    async with session_scope(sessionmaker_mem2) as s:
        rows = await repo.revisions(s, "a@b.com")
        assert len(rows) == 1
        assert rows[0].result["verdict"] == "deliverable"


async def test_missing_confirm_token_rejected(sessionmaker_mem, tmp_path):
    await _seed(sessionmaker_mem)
    svc = _svc(sessionmaker_mem, tmp_path)
    archive = tmp_path / "b.tar.gz"
    archive.write_bytes(await svc.make_backup())
    with pytest.raises(BackupError):
        await svc.restore(str(archive), "")


async def test_foreign_schema_version_rejected_without_mutation(sessionmaker_mem, tmp_path):
    await _seed(sessionmaker_mem)
    svc = _svc(sessionmaker_mem, tmp_path)

    # Hand-build an archive with a bad schema_version (and matching checksum).
    import hashlib
    import json

    data_bytes = json.dumps(
        {"validation_results": [], "verification_events": [], "app_settings": []},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    manifest = {
        "schema_version": 999,
        "sha256": hashlib.sha256(data_bytes).hexdigest(),
        "row_counts": {},
    }
    archive = tmp_path / "foreign.tar.gz"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in [
            ("manifest.json", json.dumps(manifest).encode()),
            ("data.json", data_bytes),
        ]:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    archive.write_bytes(buf.getvalue())

    with pytest.raises(BackupError):
        await svc.restore(str(archive), RESTORE_CONFIRM)

    # State untouched.
    async with session_scope(sessionmaker_mem) as s:
        assert len(await repo.revisions(s, "a@b.com")) == 1


async def test_zip_slip_member_rejected(sessionmaker_mem, tmp_path):
    svc = _svc(sessionmaker_mem, tmp_path)
    archive = tmp_path / "evil.tar.gz"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        content = b"pwned"
        info = tarfile.TarInfo("../../etc/evil")
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    archive.write_bytes(buf.getvalue())
    with pytest.raises(BackupError):
        await svc.restore(str(archive), RESTORE_CONFIRM)
