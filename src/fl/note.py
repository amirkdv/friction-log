"""`fl note` — append a NOTE marker to the active session's log."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from . import storage, ui


def cmd_note(args: list[str]) -> int:
    sess = os.environ.get("FL_SESSION")
    if not sess:
        ui.error("✗ not recording. run `fl` first.")
        return 1

    log = Path(sess)
    if args:
        text = " ".join(args).strip()
    else:
        text = _capture_via_editor()
        if not text:
            ui.info("· empty note, nothing written")
            return 0

    ts = datetime.now().strftime("%H:%M:%S")
    # Prefix every line in the body so multiline editor input stays attributed.
    first, *rest = text.splitlines() or [""]
    body = f"### NOTE [{ts}]: {first}\n"
    for line in rest:
        body += f"### NOTE [{ts}]: {line}\n"

    with log.open("a", encoding="utf-8") as f:
        f.write(body)

    fl_id = os.environ.get("FL_ID") or storage.id_from_path(log)
    ui.success(f"✎ noted to {fl_id}")
    return 0


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
