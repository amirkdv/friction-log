"""Session helpers. Most start logic lives in bin/fl since it must mutate the parent shell."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from . import storage, ui


def cmd_new_id() -> int:
    """Print a fresh ID and create empty log + timing files. Used by bin/fl."""
    storage.ensure_root()
    fl_id = storage.new_id()
    # Touch the files so the bash wrapper can rely on their presence.
    storage.log_path(fl_id).touch()
    storage.timing_path(fl_id).touch()
    print(fl_id)
    return 0


def cmd_status() -> int:
    sess = os.environ.get("FL_SESSION")
    fl_id = os.environ.get("FL_ID")
    if sess and fl_id:
        ui.info(f"▶ recording {fl_id}")
        ui.info(f"  → {sess}")
    else:
        ui.info("· not recording in this shell")

    logs = storage.list_logs()
    total_bytes = 0
    if storage.ROOT.exists():
        for p in storage.ROOT.iterdir():
            if p.is_file():
                try:
                    total_bytes += p.stat().st_size
                except OSError:
                    pass
    ui.info(f"  {len(logs)} log(s), {_human_bytes(total_bytes)} on disk in {storage.ROOT}")
    return 0


def _human_bytes(n: int) -> str:
    for unit in ("B", "K", "M", "G"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}T"


def cmd_print_started(fl_id: str) -> int:
    """Called by bin/fl right before exec'ing script(1) so the user sees what's happening."""
    p = storage.log_path(fl_id)
    ui.info(f"▶ recording {fl_id}")
    ui.info(f"  → {p}")
    return 0


def cmd_already_recording() -> int:
    fl_id = os.environ.get("FL_ID", "?")
    sess = os.environ.get("FL_SESSION", "?")
    started = storage.parse_id(Path(sess).name) if sess and sess != "?" else None
    if started:
        elapsed = datetime.now() - started
        mins = int(elapsed.total_seconds() // 60)
        ui.info(
            f"▶ already recording {fl_id} "
            f"(started {started:%H:%M}, {mins}m elapsed)"
        )
    else:
        ui.info(f"▶ already recording {fl_id}")
    return 0
