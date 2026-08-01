import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_alembic_upgrade_creates_tables(tmp_path):
    db = tmp_path / "m.db"
    env = dict(os.environ)
    env["MAILSIEVE_DATABASE__SQLITE__PATH"] = str(db)
    env.pop("MAILSIEVE_CONFIG_FILE", None)
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    con = sqlite3.connect(db)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()
    assert {"validation_results", "verification_events", "app_settings"} <= tables
