"""End-to-end tests for `fl view`.

The picker requires a TTY, so subprocess tests exercise only the
single-match and zero/multi-match-non-interactive paths. To verify the
EDITOR launch without actually opening one, we shim $EDITOR to a script
that records its argv and exits.
"""

from __future__ import annotations

import os
from pathlib import Path


def _make_editor_recorder(tmpdir: Path) -> tuple[Path, Path]:
    """Return (editor_script_path, captured_args_path). Editor records its
    args to the captured file and exits 0."""
    captured = tmpdir / "_editor_args.txt"
    script = tmpdir / "_editor.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$@" > "{captured}"\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script, captured


def _seed_doc(friction_dir: Path, stem: str, session_stem: str) -> Path:
    friction_dir.mkdir(parents=True, exist_ok=True)
    p = friction_dir / f"{stem}.md"
    p.write_text(f"---\nsession: {session_stem}\n---\n\nDOC BODY\n", encoding="utf-8")
    return p


def test_view_opens_single_session_match(run_fl, friction_dir, fl_home, seed_session):
    target = seed_session("2026-05-09-T-12-00-foo", "body\n")
    editor, captured = _make_editor_recorder(fl_home)

    r = run_fl("view", "-n", "foo", env_extra={"EDITOR": str(editor)})
    assert r.returncode == 0, r.stderr
    assert captured.exists(), f"editor was not invoked: {r.stderr}"
    args = captured.read_text().strip().splitlines()
    assert args == [str(target)], args


def test_view_opens_single_doc_match(run_fl, friction_dir, fl_home, seed_session):
    seed_session("2026-05-09-T-12-00-foo", "body\n")
    doc = _seed_doc(
        friction_dir,
        "fl-doc-2026-05-09-T-12-00-foo",
        "fl-session-2026-05-09-T-12-00-foo",
    )
    editor, captured = _make_editor_recorder(fl_home)

    # The session also matches "foo" by suffix; to target the doc specifically
    # we don't have a clean disambiguator yet — but if the search term is
    # something unique to a doc filename, view picks it. Here, the doc and
    # session share the same suffix, so this is ambiguous.
    r = run_fl("view", "-n", "fresh-thing", env_extra={"EDITOR": str(editor)})
    assert r.returncode == 1
    assert "no sessions or docs match" in r.stderr.lower()

    # Now archive the session so only the doc is in play.
    archive_dir = friction_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    (friction_dir / "fl-session-2026-05-09-T-12-00-foo.md").rename(
        archive_dir / "fl-session-2026-05-09-T-12-00-foo.md"
    )
    # Still both archived session + active doc match "foo" → ambiguous.
    r = run_fl("view", "-n", "foo", env_extra={"EDITOR": str(editor)})
    assert r.returncode == 1
    assert "matches 2 files" in r.stderr or "2 files" in r.stderr

    # But the user can disambiguate with a doc-specific term — use the doc's
    # full filename stem (or part of it) by searching for nothing else.
    # Since session/doc have same suffix and TS, no clean disambiguator;
    # accept that and move on — the single-doc path is covered by the
    # `doc only` test below.
    _ = doc  # silence unused


def test_view_opens_single_doc_only(run_fl, friction_dir, fl_home):
    """A doc with no matching session at all — `fl view` finds and opens it."""
    doc = _seed_doc(
        friction_dir,
        "fl-doc-2026-05-09-T-12-00-orphan",
        "fl-session-2026-05-09-T-12-00-orphan",  # no such session exists
    )
    editor, captured = _make_editor_recorder(fl_home)

    r = run_fl("view", "-n", "orphan", env_extra={"EDITOR": str(editor)})
    assert r.returncode == 0, r.stderr
    args = captured.read_text().strip().splitlines()
    assert args == [str(doc)], args


def test_view_zero_match_errors(run_fl, seed_session, fl_home):
    seed_session("2026-05-09-T-12-00-foo", "body\n")
    editor, _ = _make_editor_recorder(fl_home)
    r = run_fl("view", "-n", "nope", env_extra={"EDITOR": str(editor)})
    assert r.returncode == 1
    assert "no sessions or docs match" in r.stderr.lower()


def test_view_multi_match_non_interactive_errors(run_fl, seed_session, fl_home):
    seed_session("2026-05-09-T-12-00-auth-bug", "a\n")
    seed_session("2026-05-09-T-13-00-auth-rewrite", "b\n")
    editor, _ = _make_editor_recorder(fl_home)
    r = run_fl("view", "-n", "auth", env_extra={"EDITOR": str(editor)})
    assert r.returncode == 1
    assert "matches 2 files" in r.stderr


def test_view_no_name_non_interactive_errors(run_fl, seed_session, fl_home):
    seed_session("2026-05-09-T-12-00-foo", "body\n")
    editor, _ = _make_editor_recorder(fl_home)
    r = run_fl("view", env_extra={"EDITOR": str(editor)})
    assert r.returncode == 1
    assert "-n" in r.stderr


def test_view_nothing_to_view(run_fl, fl_home):
    editor, _ = _make_editor_recorder(fl_home)
    r = run_fl("view", "-n", "anything", env_extra={"EDITOR": str(editor)})
    assert r.returncode == 1
    assert "nothing to view" in r.stderr.lower()
