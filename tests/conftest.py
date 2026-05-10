"""Hermetic test scaffolding for fl.

Each test gets:
- A throwaway HOME (so ~/.friction-log is per-test).
- A controlled PATH that includes the fakes/ dir (fake `claude`) and the
  real `bin/fl` wrapper.
- SHELL forced to /bin/bash so the PS1-capture path is deterministic.

Tests invoke `fl` as a subprocess against the real wrapper — no in-process
imports of fl.cli — so argparse, the bash dispatcher, and env handling are
all under test.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BIN_FL = REPO_ROOT / "bin" / "fl"
FAKES_DIR = Path(__file__).resolve().parent / "fakes"


@pytest.fixture
def fl_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


@pytest.fixture
def fl_env(fl_home: Path) -> dict[str, str]:
    base_path = os.environ.get("PATH", "")
    path = os.pathsep.join([str(FAKES_DIR), str(BIN_FL.parent), base_path])
    return {
        "HOME": str(fl_home),
        "PATH": path,
        "SHELL": "/bin/bash",
        "TERM": "dumb",
        "LANG": "C.UTF-8",
        # Wide console so rich-rendered tables in `fl ls` don't wrap session
        # or doc filenames across multiple lines (tests grep by full stem).
        "COLUMNS": "300",
        "UV_CACHE_DIR": str(fl_home / ".uv-cache"),
    }


@pytest.fixture
def run_fl(fl_env):
    def _run(
        *args: str,
        stdin: str = "",
        env_extra: dict[str, str] | None = None,
        timeout: float = 60,
    ) -> subprocess.CompletedProcess:
        env = dict(fl_env)
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            [str(BIN_FL), *args],
            input=stdin,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
            cwd=str(REPO_ROOT),
        )

    return _run


@pytest.fixture
def friction_dir(fl_home: Path) -> Path:
    return fl_home / ".friction-log"


@pytest.fixture
def seed_session(friction_dir: Path):
    """Create a session .md with the canonical fl-session-<TS>-<name> filename.

    Accepts either the bare `<TS>-<name>` (auto-prefixed) or a fully-qualified
    `fl-session-<TS>-<name>` stem.
    """

    def _seed(stem: str, body: str = "") -> Path:
        friction_dir.mkdir(parents=True, exist_ok=True)
        if not stem.startswith("fl-session-"):
            stem = f"fl-session-{stem}"
        p = friction_dir / f"{stem}.md"
        p.write_text(body, encoding="utf-8")
        return p

    return _seed
