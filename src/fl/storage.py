"""Filesystem layout for friction logs.

One file per named session: ~/.friction-log/<TS>-<name>.md, where
<TS> = YYYY-MM-DD-T-HH-MM. The full filename stem is the canonical session
id; users can refer to a session by a substring of the post-timestamp suffix.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(os.path.expanduser("~/.friction-log"))
ARCHIVE = ROOT / "archive"

# <TS>-<suffix>.md where TS = YYYY-MM-DD-T-HH-MM. Suffix may contain
# anything except path separators and itself starts with a non-digit so we
# can split cleanly. We just anchor on the timestamp shape.
TS_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}-T-\d{2}-\d{2})-(.+)$")

DOC_PREFIX = "fl-doc-"


def ensure_root() -> Path:
    ROOT.mkdir(parents=True, exist_ok=True)
    return ROOT


def now_ts(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return now.strftime("%Y-%m-%d-T-%H-%M")


def session_path(stem: str) -> Path:
    return ROOT / f"{stem}.md"


def next_doc_path(suffix: str) -> Path:
    """Pick the next free `fl-doc-<suffix>-N.md` filename in ROOT.

    N starts at 0 and bumps past any colliding name in ROOT or ARCHIVE so an
    archived doc never gets clobbered by a regenerated one.
    """
    cleaned = sanitize_suffix(suffix)
    n = 0
    while True:
        candidate = ROOT / f"{DOC_PREFIX}{cleaned}-{n}.md"
        archived = ARCHIVE / candidate.name
        if not candidate.exists() and not archived.exists():
            return candidate
        n += 1


def list_docs(directory: Path) -> list[Path]:
    """All `fl-doc-*.md` files in `directory`, mtime-desc."""
    if not directory.exists():
        return []
    out = [p for p in directory.glob(f"{DOC_PREFIX}*.md") if p.is_file()]
    out.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return out


def format_doc_frontmatter(session_stems: list[str]) -> str:
    """Render the YAML frontmatter block that lists a doc's source sessions."""
    lines = ["---", "sessions:"]
    for s in session_stems:
        lines.append(f"  - {s}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines) + "\n"


def read_doc_sessions(path: Path) -> list[str]:
    """Parse the frontmatter and return the list of source session stems.

    Returns [] if the file has no recognizable frontmatter — pre-frontmatter
    docs and hand-written ones simply have no linkage.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if not text.startswith("---\n"):
        return []
    end = text.find("\n---", 4)
    if end < 0:
        return []
    block = text[4:end]
    stems: list[str] = []
    in_sessions = False
    for line in block.splitlines():
        if line.startswith("sessions:"):
            in_sessions = True
            continue
        if in_sessions:
            m = re.match(r"\s+-\s+(\S+)", line)
            if m:
                stems.append(m.group(1))
            elif line.strip() and not line.startswith(" "):
                in_sessions = False
    return stems


def split_stem(stem: str) -> tuple[str, str] | None:
    """Return (timestamp, suffix) if stem has the canonical shape, else None."""
    m = TS_PREFIX_RE.match(stem)
    if not m:
        return None
    return m.group(1), m.group(2)


def session_suffix(stem: str) -> str:
    parts = split_stem(stem)
    return parts[1] if parts else stem


def list_sessions() -> list[Path]:
    """All session .md files at top-level (archive/ excluded), mtime-desc.

    Excludes fl-doc-*.md (summary outputs) by requiring the canonical
    <TS>-<name> filename shape.
    """
    return _scan(ROOT)


def list_archived_sessions() -> list[Path]:
    """Anything session-like under ARCHIVE/, mtime-desc.

    Permissive on purpose: archive can hold mixed-format leftovers (old
    `.log` files from the pre-paste-flow era). `fl ls` should reflect what
    is actually on disk, not just the canonical format.
    """
    if not ARCHIVE.exists():
        return []
    out: list[Path] = []
    for p in ARCHIVE.iterdir():
        if not p.is_file():
            continue
        if p.suffix not in (".md", ".log"):
            continue
        if p.name.startswith("fl-doc-"):
            continue
        out.append(p)
    out.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return out


def _scan(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    out: list[Path] = []
    for p in directory.glob("*.md"):
        if not p.is_file():
            continue
        if split_stem(p.stem) is None:
            continue
        out.append(p)
    out.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return out


def match_sessions(term: str, candidates: list[Path]) -> list[Path]:
    """Filter candidates whose suffix contains every dash-token of `term`
    (case-insensitive). Empty term matches all."""
    term = (term or "").strip().lower()
    if not term:
        return list(candidates)
    tokens = [t for t in term.split("-") if t]
    if not tokens:
        return list(candidates)
    out = []
    for p in candidates:
        suffix = session_suffix(p.stem).lower()
        if all(tok in suffix for tok in tokens):
            out.append(p)
    return out


def new_session_path(suffix: str, now: datetime | None = None) -> Path:
    """Build the path for a brand-new session with the given user-suffix."""
    cleaned = sanitize_suffix(suffix)
    return ROOT / f"{now_ts(now)}-{cleaned}.md"


def sanitize_suffix(suffix: str) -> str:
    """Normalize a user-supplied suffix: strip whitespace, replace path
    separators and spaces with dashes, collapse repeats."""
    s = suffix.strip().lower()
    s = re.sub(r"[\s/\\]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "session"


def line_count(p: Path) -> int:
    try:
        with p.open("rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|[\x00-\x08\x0b\x0c\x0e-\x1f]")


def first_chunk_preview(p: Path, max_chars: int = 60) -> str:
    """First non-empty, non-delimiter line of the session, for picker display.
    Strips ANSI/control codes so old script-era .log files render readably."""
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                s = _ANSI_RE.sub("", line).strip()
                if not s or s.startswith("---"):
                    continue
                return s[:max_chars] + ("…" if len(s) > max_chars else "")
    except OSError:
        pass
    return ""


def fmt_duration(td: timedelta) -> str:
    secs = max(0, int(td.total_seconds()))
    h, rem = divmod(secs, 3600)
    m, _ = divmod(rem, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m"
