"""Hermetic test scaffolding for fl.

Each test gets:
- A throwaway HOME (so ~/.friction-log is per-test and rcfiles are absent).
- A controlled PATH that includes the fakes/ dir (fake `claude`) and the
  real `bin/fl` wrapper, but otherwise mirrors the host so `bash`, `script`,
  `uv`, and `python3` resolve normally.
- SHELL forced to /bin/bash so bin/fl takes a deterministic branch.

Tests invoke `fl` as a subprocess against the real wrapper — no in-process
imports of fl.cli — so argparse, the bash dispatcher, and env handling are
all under test.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BIN_FL = REPO_ROOT / "bin" / "fl"
FAKES_DIR = Path(__file__).resolve().parent / "fakes"


@pytest.fixture
def fl_home(tmp_path: Path) -> Path:
    """Empty HOME for the test. ~/.friction-log resolves under it."""
    home = tmp_path / "home"
    home.mkdir()
    return home


@pytest.fixture
def fl_env(fl_home: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Base env dict for invoking fl. Tests can override per-call via run_fl(env=...)."""
    base_path = os.environ.get("PATH", "")
    path = os.pathsep.join([str(FAKES_DIR), str(BIN_FL.parent), base_path])
    return {
        "HOME": str(fl_home),
        "PATH": path,
        "SHELL": "/bin/bash",
        "TERM": "dumb",
        "LANG": "C.UTF-8",
        # Tell uv where to put its cache so we don't write under the real $HOME.
        "UV_CACHE_DIR": str(fl_home / ".uv-cache"),
    }


@pytest.fixture
def run_fl(fl_env):
    """Invoke `fl` (the bash wrapper) and return CompletedProcess."""

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
def seed_log(friction_dir: Path):
    """Helper for tests that need pre-existing logs."""

    def _seed(fl_id: str, body: str) -> Path:
        friction_dir.mkdir(parents=True, exist_ok=True)
        p = friction_dir / f"{fl_id}.log"
        p.write_text(body, encoding="utf-8")
        return p

    return _seed


def pytest_collection_modifyitems(config, items):
    """Skip recording tests if `script(1)` is missing (shouldn't happen on macOS/Linux)."""
    if shutil.which("script") is None:
        skip_no_script = pytest.mark.skip(reason="script(1) not on PATH")
        for item in items:
            if "needs_script" in item.keywords:
                item.add_marker(skip_no_script)
