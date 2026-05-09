import re
from pathlib import Path

NOTE_LINE_RE = re.compile(r"^### NOTE \[\d{2}:\d{2}:\d{2}\]: (.*)$", re.M)


def test_note_errors_when_no_session(run_fl):
    r = run_fl("note", "hello")
    assert r.returncode == 1
    assert "not recording" in r.stderr
    # Must mention how to fix it.
    assert "fl" in r.stderr


def test_note_appends_to_active_log(run_fl, friction_dir):
    fl_id = "fl-2026-05-09-1430-aaaaaa"
    friction_dir.mkdir(parents=True, exist_ok=True)
    log = friction_dir / f"{fl_id}.log"
    log.write_text("preexisting line\n", encoding="utf-8")

    r = run_fl(
        "note",
        "rate-limited",
        "again",
        env_extra={"FL_SESSION": str(log), "FL_ID": fl_id},
    )
    assert r.returncode == 0, r.stderr
    assert f"noted to {fl_id}" in r.stderr

    content = log.read_text(encoding="utf-8")
    assert "preexisting line\n" in content
    matches = NOTE_LINE_RE.findall(content)
    assert matches == ["rate-limited again"]


def test_note_via_editor_captures_body(run_fl, friction_dir):
    fl_id = "fl-2026-05-09-1430-bbbbbb"
    friction_dir.mkdir(parents=True, exist_ok=True)
    log = friction_dir / f"{fl_id}.log"
    log.write_text("", encoding="utf-8")

    r = run_fl(
        "note",
        env_extra={
            "FL_SESSION": str(log),
            "FL_ID": fl_id,
            "EDITOR": "editor",  # picked up from PATH (tests/fakes/editor)
            "FL_TEST_EDITOR_BODY": "first line\nsecond line",
        },
    )
    assert r.returncode == 0, r.stderr

    content = log.read_text(encoding="utf-8")
    notes = NOTE_LINE_RE.findall(content)
    assert notes == ["first line", "second line"]


def test_note_via_editor_empty_save_is_noop(run_fl, friction_dir):
    fl_id = "fl-2026-05-09-1430-cccccc"
    friction_dir.mkdir(parents=True, exist_ok=True)
    log = friction_dir / f"{fl_id}.log"
    log.write_text("", encoding="utf-8")

    r = run_fl(
        "note",
        env_extra={
            "FL_SESSION": str(log),
            "FL_ID": fl_id,
            "EDITOR": "editor",
            # FL_TEST_EDITOR_BODY unset → fake editor writes empty file.
        },
    )
    assert r.returncode == 0
    assert log.read_text(encoding="utf-8") == ""
    assert "empty note" in r.stderr or "nothing written" in r.stderr
