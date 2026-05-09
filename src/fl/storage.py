"""Filesystem layout for friction logs."""

from __future__ import annotations

import os
import re
import secrets
from datetime import datetime
from pathlib import Path

ROOT = Path(os.path.expanduser("~/.friction-log"))

ID_RE = re.compile(r"^fl-(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})-([0-9a-f]{6})$")


def ensure_root() -> Path:
    ROOT.mkdir(parents=True, exist_ok=True)
    return ROOT


def new_id(now: datetime | None = None) -> str:
    now = now or datetime.now()
    suffix = secrets.token_hex(3)
    return f"fl-{now:%Y-%m-%d-%H%M}-{suffix}"


def short_id(fl_id: str) -> str:
    # strip the "fl-" prefix for compact PS1 display
    return fl_id[3:] if fl_id.startswith("fl-") else fl_id


def log_path(fl_id: str) -> Path:
    return ROOT / f"{fl_id}.log"


def timing_path(fl_id: str) -> Path:
    return ROOT / f"{fl_id}.timing"


def doc_path(name: str) -> Path:
    return ROOT / f"fl-doc-{name}.md"


def parse_id(filename: str) -> datetime | None:
    """Parse the start time embedded in a log filename. Returns None if invalid."""
    stem = filename
    if stem.endswith(".log"):
        stem = stem[:-4]
    m = ID_RE.match(stem)
    if not m:
        return None
    y, mo, d, h, mi, _ = m.groups()
    try:
        return datetime(int(y), int(mo), int(d), int(h), int(mi))
    except ValueError:
        return None


def list_logs() -> list[Path]:
    """All fl-*.log files, newest first by filename (which sorts chronologically)."""
    if not ROOT.exists():
        return []
    logs = [p for p in ROOT.glob("fl-*.log") if parse_id(p.name)]
    logs.sort(key=lambda p: p.name, reverse=True)
    return logs


def id_from_path(p: Path) -> str:
    return p.name[:-4] if p.name.endswith(".log") else p.name
