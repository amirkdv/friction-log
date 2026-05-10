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
    # Header row: shortname, lines, session, doc, mtime (no preview).
    assert "shortname" in out
    assert "lines" in out
    assert "session" in out
    assert "doc" in out
    assert "mtime" in out
    assert "preview" not in out
    # No decorative divider line.
    assert "----" not in out
    # User is told the listing paths are relative to the storage root.
    assert "relative to" in r.stderr
    assert ".friction-log" in r.stderr


def test_ls_shortname_column_strips_timestamp(run_fl, seed_session):
    """The shortname column shows the post-TS suffix only (e.g. 'test'),
    distinct from the session column which carries the full filename."""
    seed_session("2026-05-09-T-12-00-test", "body\n")
    seed_session("2026-05-09-T-13-00-test-archive", "body\n")

    r = run_fl("ls")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    # Find each session's row and confirm the shortname appears on it.
    test_row = next(
        line for line in out.splitlines()
        if "fl-session-2026-05-09-T-12-00-test.md" in line
    )
    archive_row = next(
        line for line in out.splitlines()
        if "fl-session-2026-05-09-T-13-00-test-archive.md" in line
    )
    # Shortname is present (and is the leftmost identifying token).
    assert " test " in test_row or test_row.lstrip("│ ").startswith("test ")
    assert "test-archive" in archive_row


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


def test_ls_multiple_docs_per_session_each_on_own_line(run_fl, friction_dir, seed_session):
    """A session regenerated twice has two docs (`-1`, `-2`). Both must be
    listed under that session, each on its own line within the doc cell."""
    seed_session("2026-05-09-T-13-00-bar", "body\n")
    _seed_doc(
        friction_dir,
        "fl-doc-2026-05-09-T-13-00-bar",
        "fl-session-2026-05-09-T-13-00-bar",
    )
    _seed_doc(
        friction_dir,
        "fl-doc-2026-05-09-T-13-00-bar-1",
        "fl-session-2026-05-09-T-13-00-bar",
    )

    r = run_fl("ls")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    # Both doc filenames render.
    assert "fl-doc-2026-05-09-T-13-00-bar.md" in out
    assert "fl-doc-2026-05-09-T-13-00-bar-1.md" in out
    # They land on different output lines (own-line-per-doc inside the cell).
    doc_lines = [
        line for line in out.splitlines()
        if "fl-doc-2026-05-09-T-13-00-bar" in line
    ]
    assert len(doc_lines) >= 2, doc_lines


def test_ls_renders_bounding_box(run_fl, seed_session):
    """The session listing is rendered as a bordered table."""
    seed_session("2026-05-09-T-12-00-foo", "body\n")
    r = run_fl("ls")
    assert r.returncode == 0, r.stderr
    # Rich's default box uses heavy/light box-drawing characters. Any of these
    # being present confirms a bounding-box was drawn.
    assert any(ch in r.stdout for ch in "┏┌╭━─│┃"), r.stdout


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
    # No main session table — the "preview" column is session-only.
    assert "preview" not in r.stdout
    # Orphan section still renders.
    assert "orphan docs" in r.stdout.lower()
    assert "fl-doc-2026-05-01-T-09-00-gone" in r.stdout


def test_ls_lists_legacy_archived_log(run_fl, friction_dir):
    """Old script-era .log files in archive/ still appear in the listing
    (under a dimmed row). The preview column was dropped, so we just confirm
    the filename shows up."""
    archive_dir = friction_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / "fl-2026-05-09-2300-aaaaaa.log").write_text(
        "\x1b[33m[REC 2026-05-09-2300-aaaaaa]\x1b[0m hello world\n"
    )
    r = run_fl("ls")
    assert r.returncode == 0, r.stderr
    line = next(line for line in r.stdout.splitlines() if "fl-2026-05-09-2300-aaaaaa.log" in line)
    # ANSI escape codes must not leak into rendered output.
    assert "\x1b" not in line
    assert "[33m" not in line
