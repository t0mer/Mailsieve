from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import (
    AppSetting,
    Base,
    EventSource,
    ValidationResult,
    VerificationEvent,
)


def test_tables_create_and_roundtrip():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        vr = ValidationResult(email="a@b.com", result={"score": 0.9}, result_hash="0" * 64)
        s.add(vr)
        s.flush()
        s.add(VerificationEvent(email="a@b.com", result_id=vr.id, source=EventSource.api))
        s.add(AppSetting(key="api_token_hash", value="bcrypt$..."))
        s.commit()

        got = s.scalar(select(ValidationResult).where(ValidationResult.email == "a@b.com"))
        assert got is not None
        assert got.result == {"score": 0.9}
        assert got.created_at is not None
        ev = s.scalar(select(VerificationEvent))
        assert ev is not None
        assert ev.source == EventSource.api
        assert ev.cache_hit is False
        setting = s.get(AppSetting, "api_token_hash")
        assert setting is not None and setting.value == "bcrypt$..."


def test_composite_index_present():
    names = {ix.name for ix in ValidationResult.__table__.indexes}
    assert "ix_vr_email_created" in names
