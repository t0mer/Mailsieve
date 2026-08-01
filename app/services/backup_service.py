"""Portable backup and guarded restore (§10).

A backup is a gzipped tar of ``manifest.json`` + ``data.json`` (a JSON dump of
all tables), so it restores across sqlite/postgres/mysql — not a raw DB file.
Restore validates the manifest and schema version first, rejects unsafe archive
members (zip-slip), takes a pre-restore snapshot, and runs inside a transaction.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select

from app.db.models import AppSetting, EventSource, ValidationResult, VerificationEvent
from app.db.session import session_scope

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

SCHEMA_VERSION = 1
RESTORE_CONFIRM = "RESTORE"  # noqa: S105 - a confirmation sentinel, not a credential
_MANIFEST = "manifest.json"
_DATA = "data.json"


class BackupError(Exception):
    """Raised when an archive is malformed, foreign, or unsafe to restore."""


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class BackupService:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        directory: str,
        max_upload_mb: int,
        backend: str,
    ) -> None:
        self._sm = sessionmaker
        self._dir = directory
        self._max_bytes = max_upload_mb * 1024 * 1024
        self._backend = backend

    # --- backup ------------------------------------------------------------ #
    async def _dump(self, session: AsyncSession) -> dict[str, list[dict[str, Any]]]:
        vr = (await session.scalars(select(ValidationResult))).all()
        ve = (await session.scalars(select(VerificationEvent))).all()
        aps = (await session.scalars(select(AppSetting))).all()
        return {
            "validation_results": [
                {
                    "id": r.id,
                    "email": r.email,
                    "result": r.result,
                    "result_hash": r.result_hash,
                    "created_at": _dt(r.created_at),
                }
                for r in vr
            ],
            "verification_events": [
                {
                    "id": r.id,
                    "email": r.email,
                    "result_id": r.result_id,
                    "checked_at": _dt(r.checked_at),
                    "source": str(r.source),
                    "cache_hit": r.cache_hit,
                }
                for r in ve
            ],
            "app_settings": [
                {"key": r.key, "value": r.value, "updated_at": _dt(r.updated_at)} for r in aps
            ],
        }

    @staticmethod
    def _add(tar: tarfile.TarFile, name: str, content: bytes) -> None:
        info = tarfile.TarInfo(name)
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))

    async def make_backup(self) -> bytes:
        async with session_scope(self._sm) as s:
            data = await self._dump(s)
        data_bytes = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "created_at": datetime.now(UTC).isoformat(),
            "source_backend": self._backend,
            "row_counts": {k: len(v) for k, v in data.items()},
            "sha256": hashlib.sha256(data_bytes).hexdigest(),
        }
        manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            self._add(tar, _MANIFEST, manifest_bytes)
            self._add(tar, _DATA, data_bytes)
        return buf.getvalue()

    def _persist_snapshot(self, data: bytes) -> Path:
        directory = Path(self._dir)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        path = directory / f"pre-restore-{stamp}.mailsieve-backup.gz"
        path.write_bytes(data)
        return path

    async def _snapshot(self) -> Path:
        data = await self.make_backup()
        return await asyncio.to_thread(self._persist_snapshot, data)

    # --- restore ----------------------------------------------------------- #
    @staticmethod
    def _read_member(tar: tarfile.TarFile, name: str) -> bytes:
        f = tar.extractfile(name)
        if f is None:
            raise BackupError(f"archive missing {name}")
        return f.read()

    def _read_archive(self, path: str) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            with tarfile.open(path, mode="r:gz") as tar:
                for m in tar.getmembers():
                    if os.path.isabs(m.name) or ".." in Path(m.name).parts:
                        raise BackupError(f"unsafe archive member path: {m.name}")
                    if m.name not in (_MANIFEST, _DATA):
                        raise BackupError(f"unexpected archive member: {m.name}")
                    if not m.isfile():
                        raise BackupError(f"archive member is not a regular file: {m.name}")
                manifest_bytes = self._read_member(tar, _MANIFEST)
                data_bytes = self._read_member(tar, _DATA)
        except tarfile.TarError as exc:
            raise BackupError(f"not a valid backup archive: {exc}") from exc

        manifest = json.loads(manifest_bytes)
        if manifest.get("sha256") != hashlib.sha256(data_bytes).hexdigest():
            raise BackupError("archive data does not match manifest checksum")
        data = json.loads(data_bytes)
        return manifest, data

    async def restore(self, archive_path: str, confirm_token: str) -> dict[str, int]:
        if confirm_token != RESTORE_CONFIRM:
            raise BackupError("restore requires the confirmation token")
        size = await asyncio.to_thread(os.path.getsize, archive_path)
        if size > self._max_bytes:
            raise BackupError("archive exceeds the maximum upload size")

        manifest, data = await asyncio.to_thread(self._read_archive, archive_path)
        if manifest.get("schema_version") != SCHEMA_VERSION:
            raise BackupError(
                f"unsupported schema_version {manifest.get('schema_version')}; "
                f"this build restores version {SCHEMA_VERSION}"
            )

        await self._snapshot()

        async with session_scope(self._sm) as s:
            await s.execute(delete(VerificationEvent))
            await s.execute(delete(ValidationResult))
            await s.execute(delete(AppSetting))
            for r in data["validation_results"]:
                s.add(
                    ValidationResult(
                        id=r["id"],
                        email=r["email"],
                        result=r["result"],
                        result_hash=r["result_hash"],
                        created_at=_parse_dt(r["created_at"]),
                    )
                )
            await s.flush()
            for r in data["verification_events"]:
                s.add(
                    VerificationEvent(
                        id=r["id"],
                        email=r["email"],
                        result_id=r["result_id"],
                        checked_at=_parse_dt(r["checked_at"]),
                        source=EventSource(r["source"]),
                        cache_hit=r["cache_hit"],
                    )
                )
            for r in data["app_settings"]:
                s.add(
                    AppSetting(
                        key=r["key"],
                        value=r["value"],
                        updated_at=_parse_dt(r["updated_at"]),
                    )
                )

        counts: dict[str, int] = manifest["row_counts"]
        return counts
