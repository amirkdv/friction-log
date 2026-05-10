"""`fl view` — pick a session or doc by fuzzy name and open it in $EDITOR.

Search semantics mirror `fl note -n` / `fl doc -n`: dash-token-aware,
case-insensitive substring match against the post-prefix portion of each
filename. Sessions and docs (active and archived) are all eligible.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from . import storage, ui

_SEARCHABLE_RE = re.compile(
    r"^(?:" + re.escape(storage.SESSION_PREFIX) + r"|" + re.escape(storage.DOC_PREFIX) + r")"
    r"(?:\d{4}-\d{2}-\d{2}-T-\d{2}-\d{2}-)?(.+)$"
)


def _searchable_suffix(stem: str) -> str:
    """Strip the `fl-session-<TS>-` or `fl-doc-<TS>-` prefix; return what's
    left for fuzzy matching. Falls back to the full stem if neither prefix
    is present (e.g. legacy archived files)."""
    m = _SEARCHABLE_RE.match(stem)
    return m.group(1) if m else stem


def _candidates() -> list[Path]:
    """All sessions + docs across active and archive, mtime-desc."""
    pool: list[Path] = []
    pool.extend(storage.list_sessions())
    pool.extend(storage.list_archived_sessions())
    pool.extend(storage.list_docs(storage.ROOT))
    pool.extend(storage.list_docs(storage.ARCHIVE))
    seen: set[Path] = set()
    out: list[Path] = []
    for p in sorted(pool, key=lambda p: p.stat().st_mtime, reverse=True):
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def _match(term: str, candidates: list[Path]) -> list[Path]:
    term = (term or "").strip().lower()
    if not term:
        return list(candidates)
    tokens = [t for t in term.split("-") if t]
    if not tokens:
        return list(candidates)
    out: list[Path] = []
    for p in candidates:
        hay = _searchable_suffix(p.stem).lower()
        if all(tok in hay for tok in tokens):
            out.append(p)
    return out


def cmd_view(*, name: str | None = None) -> int:
    storage.ensure_root()
    pool = _candidates()
    if not pool:
        ui.error("✗ nothing to view in ~/.friction-log/")
        return 1

    interactive = sys.stdin.isatty() and sys.stderr.isatty()

    if name is not None:
        matches = _match(name, pool)
        if not matches:
            ui.error(f"✗ no sessions or docs match '-n {name}'")
            return 1
        if len(matches) == 1:
            return _open(matches[0])
        if not interactive:
            ui.error(
                f"✗ '-n {name}' matches {len(matches)} files; "
                f"use a more specific name. matches:"
            )
            for p in matches:
                ui.error(f"    {p.name}")
            return 1
        picked = ui.pick_session(matches, prompt=f"pick one for '-n {name}':")
        return _open(picked) if picked else 0

    if not interactive:
        ui.error("✗ stdin is not a tty and -n was not provided; pass -n <name>")
        return 1
    picked = ui.pick_session(pool, prompt="pick a session or doc:")
    return _open(picked) if picked else 0


def _open(path: Path) -> int:
    editor = os.environ.get("EDITOR", "vi")
    ui.info(f"→ opening {path.name} in {editor}")
    try:
        rc = subprocess.call([editor, str(path)])
    except (FileNotFoundError, OSError) as e:
        ui.error(f"✗ failed to launch {editor}: {e}")
        return 1
    return rc
