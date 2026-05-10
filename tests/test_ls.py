"""End-to-end tests for `fl ls` — sessions and docs in the listing."""

from __future__ import annotations


def _seed_doc(friction_dir, stem: str, session_stem: str, body: str = "BODY\n"):
    friction_dir.mkdir(parents=True, exist_ok=True)
    fm = f"---\nsession: {session_stem}\n---\n\n"
    p = friction_dir / f"{stem}.md"
    p.write_text(fm + body, encoding="utf-8")
    return p


def test_ls_empty(run_fl):
    r = run_fl("ls")
    assert r.returncode == 0
    assert "no sessions" in r.stderr.lower()


def test_ls_has_headers(run_fl, seed_session):
    seed_session("2026-05-09-T-12-00-foo", "body\n")
    r = run_fl("ls")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    # Header row with column titles.
    assert "MTIME" in out
    assert "LINES" in out
    assert "SESSION" in out
    assert "DOC" in out
    assert "PREVIEW" in out


def test_ls_coalesces_sessions_and_docs(run_fl, friction_dir, seed_session):
    seed_session("2026-05-09-T-12-00-foo", "body\n")
    seed_session("2026-05-09-T-13-00-bar", "body\n")
    _seed_doc(
        friction_dir,
        "fl-doc-2026-05-09-T-13-00-bar",
        "fl-session-2026-05-09-T-13-00-bar",
    )

    r = run_fl("ls")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    # Both sessions appear.
    assert "fl-session-2026-05-09-T-12-00-foo" in out
    assert "fl-session-2026-05-09-T-13-00-bar" in out
    # The bar session row also shows its doc — coalesced into the same line.
    bar_line = next(
        line for line in out.splitlines()
        if "fl-session-2026-05-09-T-13-00-bar.md" in line
    )
    assert "fl-doc-2026-05-09-T-13-00-bar" in bar_line
    # The unrelated session has no doc; column shows "-".
    foo_line = next(
        line for line in out.splitlines()
        if "fl-session-2026-05-09-T-12-00-foo.md" in line
    )
    assert "fl-doc-" not in foo_line
    # Doc does NOT appear as its own row.
    doc_only_lines = [
        line for line in out.splitlines()
        if "fl-doc-2026-05-09-T-13-00-bar" in line and "fl-session-" not in line
    ]
    assert doc_only_lines == [], "doc should be coalesced, not its own row"


def test_ls_shows_archived_docs(run_fl, friction_dir, seed_session):
    archive_dir = friction_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / "fl-session-2026-05-08-T-09-00-old.md").write_text("body\n")
    _seed_doc(
        archive_dir,
        "fl-doc-2026-05-08-T-09-00-old",
        "fl-session-2026-05-08-T-09-00-old",
    )

    r = run_fl("ls")
    assert r.returncode == 0, r.stderr
    # Archived session row is annotated with its archived doc on the same line.
    old_line = next(
        line for line in r.stdout.splitlines()
        if "fl-session-2026-05-08-T-09-00-old.md" in line
    )
    assert "fl-doc-2026-05-08-T-09-00-old" in old_line


def test_ls_active_session_tagged_with_archived_doc(run_fl, friction_dir, seed_session):
    """An active session whose only doc has been archived should still get
    the doc column populated — the index spans both directories."""
    seed_session("2026-05-09-T-12-00-foo", "body\n")
    archive_dir = friction_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    _seed_doc(
        archive_dir,
        "fl-doc-2026-05-09-T-12-00-foo",
        "fl-session-2026-05-09-T-12-00-foo",
    )

    r = run_fl("ls")
    assert r.returncode == 0, r.stderr
    foo_line = next(
        line for line in r.stdout.splitlines()
        if "fl-session-2026-05-09-T-12-00-foo.md" in line
    )
    assert "fl-doc-2026-05-09-T-12-00-foo" in foo_line


def test_ls_orphan_docs_listed_at_bottom(run_fl, friction_dir, seed_session):
    """A doc whose source session no longer exists is shown in its own
    section at the bottom of the listing."""
    seed_session("2026-05-09-T-12-00-foo", "body\n")
    _seed_doc(
        friction_dir,
        "fl-doc-2026-05-01-T-09-00-gone",
        "fl-session-2026-05-01-T-09-00-gone",  # session not on disk
    )

    r = run_fl("ls")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "orphan docs" in out.lower()
    assert "fl-doc-2026-05-01-T-09-00-gone" in out
    # Orphan section appears AFTER the session rows.
    foo_idx = out.index("fl-session-2026-05-09-T-12-00-foo")
    orphan_idx = out.index("fl-doc-2026-05-01-T-09-00-gone")
    assert orphan_idx > foo_idx


def test_ls_no_session_table_when_only_orphan_docs(run_fl, friction_dir):
    """With zero sessions on disk, don't print the header+divider table.
    Just say 'no sessions' and list the orphan docs."""
    _seed_doc(
        friction_dir,
        "fl-doc-2026-05-01-T-09-00-gone",
        "fl-session-2026-05-01-T-09-00-gone",
    )

    r = run_fl("ls")
    assert r.returncode == 0, r.stderr
    assert "no sessions" in r.stderr.lower()
    # No empty table header when nothing populates it.
    assert "MTIME" not in r.stdout
    assert "SESSION" not in r.stdout
    assert "----" not in r.stdout
    # Orphan section still renders.
    assert "orphan docs" in r.stdout.lower()
    assert "fl-doc-2026-05-01-T-09-00-gone" in r.stdout


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
    assert "\x1b" not in line
    assert "[33m" not in line
    assert "hello world" in line
