import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from app.auth.api_key import verify_secret

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_set_token_stores_hash_and_prints_once(tmp_path):
    db = tmp_path / "app.db"
    env = dict(os.environ)
    env["MAILSIEVE_DATABASE__SQLITE__PATH"] = str(db)
    env.pop("MAILSIEVE_CONFIG_FILE", None)
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(REPO_ROOT / "scripts" / "set_token.py")],
        env=env,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    token = result.stdout.strip()
    assert token

    con = sqlite3.connect(db)
    try:
        row = con.execute(
            "SELECT value FROM app_settings WHERE key='api_token_hash'"
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    stored_hash = row[0]
    assert stored_hash != token  # hashed, not plaintext
    assert verify_secret(token, stored_hash) is True
