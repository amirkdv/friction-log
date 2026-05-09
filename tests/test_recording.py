"""End-to-end: bare `fl` exec's real script(1), spawns bash -i with the
custom rcfile, and the inner shell can run `fl note` against the active
session. We drive the inner shell by piping commands into the wrapper."""

import re
from pathlib import Path

import pytest


@pytest.mark.needs_script
def test_bare_fl_records_and_inner_note_appends(run_fl, friction_dir, fl_home):
    # Feeding commands through the wrapper's stdin races pty buffering vs
    # bash startup — most lines get swallowed before bash is ready to read.
    # Instead, drop the commands in ~/.bashrc; the wrapper's custom rcfile
    # sources it, so they run deterministically after FL_SESSION is exported
    # and PATH is in place.
    (fl_home / ".bashrc").write_text(
        "echo HELLO_FROM_INSIDE\n"
        "fl note 'annotation from inside'\n"
        "exit\n",
        encoding="utf-8",
    )
    r = run_fl(stdin="", timeout=120)

    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    # Wrapper printed the start banner before exec'ing script.
    assert "▶ recording" in r.stderr

    logs = sorted(friction_dir.glob("fl-*.log"))
    # Filter out timing files; only one log expected.
    log_files = [p for p in logs if not p.name.endswith(".timing")]
    assert len(log_files) == 1, log_files

    log = log_files[0]
    # Pull the ID out of the wrapper's stderr to confirm round-trip.
    m = re.search(r"recording (fl-\d{4}-\d{2}-\d{2}-\d{4}-[0-9a-f]{6})", r.stderr)
    assert m, r.stderr
    fl_id = m.group(1)
    assert log.name == f"{fl_id}.log"

    body = log.read_text(encoding="utf-8", errors="replace")

    # Strip ANSI for assertions — script(1) captures terminal escapes.
    ansi = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|[\x00-\x08\x0b\x0c\x0e-\x1f]")
    clean = ansi.sub("", body)

    assert "HELLO_FROM_INSIDE" in clean
    # NOTE marker written by the *inner* `fl note` invocation.
    assert re.search(
        r"### NOTE \[\d{2}:\d{2}:\d{2}\]: annotation from inside", clean
    ), clean[:2000]


@pytest.mark.needs_script
def test_already_recording_short_circuits(run_fl, friction_dir):
    """When FL_SESSION is already exported, bare `fl` must not start a new
    session — it should just print the 'already recording' notice."""
    fl_id = "fl-2026-05-09-1430-abcdef"
    friction_dir.mkdir(parents=True, exist_ok=True)
    log = friction_dir / f"{fl_id}.log"
    log.write_text("", encoding="utf-8")

    r = run_fl(env_extra={"FL_SESSION": str(log), "FL_ID": fl_id})
    assert r.returncode == 0, r.stderr
    out = r.stdout + r.stderr
    assert "already recording" in out
    assert fl_id in out
    # No new log file should have been created.
    assert sorted(friction_dir.glob("fl-*.log")) == [log]
