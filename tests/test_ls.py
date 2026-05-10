"""End-to-end tests for `fl ls` — sessions and docs in the listing."""

from __future__ import annotations


def _seed_doc(friction_dir, name: str, sessions: list[str], body: str = "BODY\n"):
    friction_dir.mkdir(parents=True, exist_ok=True)
    fm = "---\nsessions:\n" + "".join(f"  - {s}\n" for s in sessions) + "---\n\n"
    p = friction_dir / f"fl-doc-{name}.md"
    p.write_text(fm + body, encoding="utf-8")
    return p


def test_ls_empty(run_fl):
    r = run_fl("ls")
    assert r.returncode == 0
    assert "no sessions" in r.stderr.lower()


def test_ls_lists_sessions_and_docs(run_fl, friction_dir, seed_session):
    seed_session("2026-05-09-T-12-00-foo", "body\n")
    seed_session("2026-05-09-T-13-00-bar", "body\n")
    _seed_doc(friction_dir, "bar-0", ["2026-05-09-T-13-00-bar"])

    r = run_fl("ls")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    # Both sessions appear.
    assert "2026-05-09-T-12-00-foo" in out
    assert "2026-05-09-T-13-00-bar" in out
    # Doc appears as its own row.
    assert "fl-doc-bar-0" in out
    # The session that feeds the doc is annotated with its doc name.
    bar_line = next(line for line in out.splitlines() if "2026-05-09-T-13-00-bar.md" in line)
    assert "fl-doc-bar-0" in bar_line
    # The unrelated session has no doc tag.
    foo_line = next(line for line in out.splitlines() if "2026-05-09-T-12-00-foo.md" in line)
    assert "(doc:" not in foo_line


def test_ls_shows_archived_docs(run_fl, friction_dir, seed_session):
    archive_dir = friction_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / "2026-05-08-T-09-00-old.md").write_text("body\n")
    _seed_doc(archive_dir, "old-0", ["2026-05-08-T-09-00-old"])

    r = run_fl("ls")
    assert r.returncode == 0, r.stderr
    assert "fl-doc-old-0" in r.stdout
    # Archived session row is annotated with its archived doc.
    old_line = next(line for line in r.stdout.splitlines() if "2026-05-08-T-09-00-old.md" in line)
    assert "fl-doc-old-0" in old_line


def test_ls_active_session_tagged_with_archived_doc(run_fl, friction_dir, seed_session):
    """An active session whose only doc has been archived should still get
    the [doc: …] tag — the index spans both directories."""
    seed_session("2026-05-09-T-12-00-foo", "body\n")
    archive_dir = friction_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    _seed_doc(archive_dir, "foo-0", ["2026-05-09-T-12-00-foo"])

    r = run_fl("ls")
    assert r.returncode == 0, r.stderr
    foo_line = next(line for line in r.stdout.splitlines() if "2026-05-09-T-12-00-foo.md" in line)
    assert "fl-doc-foo-0" in foo_line


def test_ls_strips_ansi_in_preview(run_fl, friction_dir):
    """Old script-era .log files in archive/ have ANSI escape codes; the
    preview column must render them without escape noise."""
    archive_dir = friction_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / "fl-2026-05-09-2300-aaaaaa.log").write_text(
        "\x1b[33m[REC 2026-05-09-2300-aaaaaa]\x1b[0m hello world\n"
    )
    r = run_fl("ls")
    assert r.returncode == 0, r.stderr
    line = next(line for line in r.stdout.splitlines() if "fl-2026-05-09-2300-aaaaaa.log" in line)
    # Escape sequences must not survive into the preview.
    assert "\x1b" not in line
    assert "[33m" not in line
    # Useful content does survive.
    assert "hello world" in line
