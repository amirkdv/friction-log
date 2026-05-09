def test_status_when_not_recording(run_fl):
    r = run_fl("status")
    assert r.returncode == 0, r.stderr
    out = r.stdout + r.stderr
    assert "not recording" in out
    assert "0 log(s)" in out


def test_status_reports_active_session(run_fl, friction_dir):
    fl_id = "fl-2026-05-09-1430-a3f78d"
    friction_dir.mkdir(parents=True, exist_ok=True)
    log = friction_dir / f"{fl_id}.log"
    log.write_text("body\n", encoding="utf-8")

    r = run_fl(
        "status",
        env_extra={"FL_SESSION": str(log), "FL_ID": fl_id, "COLUMNS": "500"},
    )
    assert r.returncode == 0, r.stderr
    out = r.stdout + r.stderr
    assert "▶ recording" in out
    assert fl_id in out
    assert str(log) in out
    assert "1 log(s)" in out
