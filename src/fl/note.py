"""`fl note` — append a chunk of pasted/typed content to a named session.

Body sources, in priority order:
  1. Inline args after the flags (short notes).
  2. Stdin, if not a TTY (heredoc, `cmd | fl note`, `pbpaste | fl note`).
  3. $EDITOR fallback (interactive, when no args and stdin is a TTY).

Session is resolved via `-n <term>`:
  - exactly 1 match → silent
  - 0 matches → confirm-create (interactive) or auto-create (non-interactive)
  - ≥2 matches → picker filtered to matches (interactive) or error (non-interactive)
If `-n` is omitted, the user gets a picker over all sessions plus a
"create new…" option (interactive only).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from . import storage, ui


def cmd_note(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="fl note", add_help=True)
    parser.add_argument("-n", "--name", dest="name", default=None,
                        help="session name (substring matches an existing session; new otherwise)")
    parser.add_argument("words", nargs=argparse.REMAINDER,
                        help="inline note text (omit to read stdin or open $EDITOR)")
    args = parser.parse_args(argv)

    words = args.words or []
    if words and words[0] == "--":
        words = words[1:]

    session = _resolve_session(args.name)
    if session is None:
        return 1

    if session.exists():
        ui.info(f"→ session: {session.stem}")
    else:
        ui.info(f"→ new session: {session.stem}")

    body = _read_body(words)
    if not body:
        ui.info("· empty note, nothing written")
        return 0

    _append_chunk(session, body)
    ui.success(f"✎ noted to {session.stem}")
    return 0


def _read_body(words: list[str]) -> str:
    if words:
        return " ".join(words).strip()
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    return _capture_via_editor()


def _capture_via_editor() -> str:
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile(
        mode="w+", suffix=".fl-note.md", delete=False, encoding="utf-8"
    ) as tf:
        path = tf.name
    try:
        rc = subprocess.call([editor, path])
        if rc != 0:
            print(f"editor exited with {rc}", file=sys.stderr)
            return ""
        return Path(path).read_text(encoding="utf-8").strip()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _resolve_session(term: str | None) -> Path | None:
    storage.ensure_root()
    candidates = storage.list_sessions()
    interactive = sys.stdin.isatty() and sys.stderr.isatty()

    if term:
        matches = storage.match_sessions(term, candidates)
        if len(matches) == 1:
            return matches[0]
        if len(matches) == 0:
            return storage.new_session_path(term)
        # multiple matches
        if not interactive:
            ui.error(
                f"✗ '-n {term}' matches {len(matches)} sessions; "
                f"use a more specific name. matches:"
            )
            for p in matches:
                ui.error(f"    {p.stem}")
            return None
        return ui.pick_session(matches, prompt=f"multiple sessions match '{term}'; pick one:")

    # no -n given
    if not interactive:
        ui.error("✗ stdin is not a tty and -n was not provided; pass -n <name>")
        return None
    return ui.pick_or_create_session(candidates)


def _append_chunk(path: Path, body: str) -> None:
    storage.ensure_root()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not body.endswith("\n"):
        body = body + "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n--- {ts} ---\n{body}")
