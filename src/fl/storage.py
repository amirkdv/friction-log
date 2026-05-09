"""Filesystem layout for friction logs."""

from __future__ import annotations

import os
import re
import secrets
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(os.path.expanduser("~/.friction-log"))
ARCHIVE = ROOT / "archive"

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
    """All fl-*.log files in ROOT, newest first. Archive subdir is excluded
    because glob() is non-recursive — that's how archived sessions stay hidden
    from `fl doc`."""
    if not ROOT.exists():
        return []
    logs = [p for p in ROOT.glob("fl-*.log") if parse_id(p.name)]
    logs.sort(key=lambda p: p.name, reverse=True)
    return logs


def session_files(fl_id: str, base: Path = ROOT) -> list[Path]:
    """All on-disk artifacts for a session (log + timing). Used by archive."""
    return [p for p in (base / f"{fl_id}.log", base / f"{fl_id}.timing") if p.exists()]


def id_from_path(p: Path) -> str:
    return p.name[:-4] if p.name.endswith(".log") else p.name


def line_count(p: Path) -> int:
    try:
        with p.open("rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def first_note(p: Path, max_chars: int = 60) -> str:
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("### NOTE"):
                    s = line.rstrip("\n")
                    return s[:max_chars] + ("…" if len(s) > max_chars else "")
    except OSError:
        pass
    return ""


def fmt_duration(td: timedelta) -> str:
    secs = max(0, int(td.total_seconds()))
    h, rem = divmod(secs, 3600)
    m, _ = divmod(rem, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m"
