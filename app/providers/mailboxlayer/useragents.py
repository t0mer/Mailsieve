"""User-agent pool. Loads a bundled list or a configured override file."""

from __future__ import annotations

import secrets
from importlib.resources import files
from pathlib import Path


def _parse(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            out.append(stripped)
    return out


class UserAgents:
    """A pool of user-agent strings with a random ``pick()``."""

    def __init__(self, path: str = "") -> None:
        if path:
            text = Path(path).read_text(encoding="utf-8")
        else:
            text = (files("app") / "data" / "user_agents.txt").read_text(encoding="utf-8")
        self._agents = _parse(text)
        if not self._agents:
            raise ValueError("no user agents loaded")

    def pick(self) -> str:
        return secrets.choice(self._agents)

    def __len__(self) -> int:
        return len(self._agents)
