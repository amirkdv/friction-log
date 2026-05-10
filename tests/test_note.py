"""End-to-end tests for `fl note` (and the bare `fl` shorthand).

Hermetic: subprocess invokes the real wrapper with stdin/stderr as pipes
(not TTYs), so the non-interactive code paths are exercised.
"""

from __future__ import annotations

import re

CHUNK_HEADER_RE = re.compile(r"^--- \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} ---$", re.M)


def test_note_with_inline_args_creates_new_session(run_fl, friction_dir):
    r = run_fl("note", "-n", "auth-bug", "rate-limited", "again")
    assert r.returncode == 0, r.stderr
    files = list(friction_dir.glob("*.md"))
    assert len(files) == 1, files
    f = files[0]
    assert f.name.endswith("-auth-bug.md")
    body = f.read_text(encoding="utf-8")
    assert CHUNK_HEADER_RE.search(body), body
    assert "rate-limited again" in body
    assert f"noted to {f.stem}" in r.stderr


def test_bare_fl_routes_to_note(run_fl, friction_dir):
    """Bare `fl -n foo bar` should behave identically to `fl note -n foo bar`."""
    r = run_fl("-n", "smoke", "hello-world")
    assert r.returncode == 0, r.stderr
    files = list(friction_dir.glob("*.md"))
    assert len(files) == 1
    assert files[0].name.endswith("-smoke.md")
    assert "hello-world" in files[0].read_text()


def test_note_appends_to_existing_session_via_partial_match(run_fl, seed_session, friction_dir):
    existing = seed_session("2026-05-09-T-14-30-authn-bug-fix", "preexisting\n")

    r = run_fl("note", "-n", "auth-bug", "second", "chunk")
    assert r.returncode == 0, r.stderr

    # No new file — appended to the existing one.
    files = sorted(friction_dir.glob("*.md"))
    assert files == [existing], files
    body = existing.read_text(encoding="utf-8")
    assert "preexisting\n" in body
    assert "second chunk" in body
    headers = CHUNK_HEADER_RE.findall(body)
    assert len(headers) == 1


def test_note_via_stdin_pipe(run_fl, friction_dir):
    paste = "$ ls\nfoo\nbar\n$ echo done\ndone\n"
    r = run_fl("note", "-n", "session-x", stdin=paste)
    assert r.returncode == 0, r.stderr
    files = list(friction_dir.glob("*.md"))
    assert len(files) == 1
    body = files[0].read_text(encoding="utf-8")
    # Whole paste preserved verbatim under a chunk header.
    assert "$ ls" in body
    assert "$ echo done" in body
    assert CHUNK_HEADER_RE.search(body)


def test_note_empty_stdin_is_noop(run_fl, friction_dir):
    r = run_fl("note", "-n", "ghost", stdin="")
    assert r.returncode == 0, r.stderr
    assert "empty note" in r.stderr or "nothing written" in r.stderr
    assert list(friction_dir.glob("*.md")) == []


def test_note_ambiguous_term_errors_in_non_tty(run_fl, seed_session):
    seed_session("2026-05-09-T-14-30-auth-bug")
    seed_session("2026-05-09-T-15-00-auth-rewrite")
    r = run_fl("note", "-n", "auth", "anything", stdin="")
    assert r.returncode == 1
    assert "matches 2 sessions" in r.stderr


def test_note_no_name_in_non_tty_errors(run_fl):
    r = run_fl("note", "hello", stdin="")
    # `hello` is treated as inline body but no -n provided and no tty → error.
    assert r.returncode == 1
    assert "-n" in r.stderr


def test_note_search_is_case_insensitive_and_dash_aware(run_fl, seed_session, friction_dir):
    target = seed_session("2026-05-09-T-14-30-AuthN-Bug-Fix", "")
    # Match across dash tokens, lowercase term.
    r = run_fl("note", "-n", "auth-fix", "ping")
    assert r.returncode == 0, r.stderr
    assert list(friction_dir.glob("*.md")) == [target]
    assert "ping" in target.read_text()


def test_note_echoes_existing_session_on_match(run_fl, seed_session):
    target = seed_session("2026-05-09-T-14-30-known-thing", "")
    r = run_fl("note", "-n", "known-thing", "ping")
    assert r.returncode == 0, r.stderr
    assert f"→ session: {target.stem}" in r.stderr


def test_note_echoes_new_session_on_zero_match(run_fl):
    r = run_fl("note", "-n", "fresh-thing", "ping")
    assert r.returncode == 0, r.stderr
    # Fresh session — must announce it as new and include the constructed stem.
    assert "→ new session:" in r.stderr
    assert "fresh-thing" in r.stderr


def test_note_resolves_session_before_reading_body(run_fl):
    """Without -n, in non-tty mode, fl must error on resolution before
    attempting any body capture (no editor spawn, no stdin slurp). The
    error message must name the missing flag."""
    r = run_fl("note", stdin="some-piped-content\n",
               env_extra={"EDITOR": "/usr/bin/false"})  # would fail loudly if invoked
    assert r.returncode == 1
    assert "-n" in r.stderr
    # Body-related noise must not appear — resolution failed first.
    assert "empty note" not in r.stderr
    assert "noted to" not in r.stderr
