from sqlalchemy import text

from app.config import load_settings
from app.db.session import make_engine, make_sessionmaker, session_scope


async def test_engine_and_session_select_one(tmp_path, monkeypatch):
    monkeypatch.delenv("MAILSIEVE_CONFIG_FILE", raising=False)
    monkeypatch.setenv("MAILSIEVE_DATABASE__SQLITE__PATH", str(tmp_path / "t.db"))
    settings = load_settings()
    engine = make_engine(settings)
    sm = make_sessionmaker(engine)
    try:
        async with session_scope(sm) as s:
            val = await s.scalar(text("SELECT 1"))
            assert val == 1
    finally:
        await engine.dispose()
