"""End-to-end tests for `fl doc`. Hermetic: real argparse + real subprocess
chain, but the `claude` CLI is faked via PATH (see tests/fakes/claude)."""

from __future__ import annotations

import os
from pathlib import Path


def test_doc_writes_file_with_fake_claude(run_fl, friction_dir, seed_session):
    seed_session("2026-05-09-T-12-00-foo", "--- 2026-05-09 12:01:00 ---\nthing one\n")
    seed_session("2026-05-09-T-13-00-bar", "--- 2026-05-09 13:00:00 ---\nthing two\n")

    r = run_fl("doc", "--last", "2")
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"

    # Doc name is derived from the most-recent session's suffix (`bar`),
    # auto-incremented from -0.
    out = friction_dir / "fl-doc-bar-0.md"
    assert out.exists(), list(friction_dir.iterdir())
    body = out.read_text(encoding="utf-8")
    assert "FAKE-CLAUDE-OUTPUT" in body
    # Frontmatter records both source sessions.
    assert "sessions:" in body
    assert "2026-05-09-T-12-00-foo" in body
    assert "2026-05-09-T-13-00-bar" in body
    assert "prompt-bytes:" in body
    assert "stdin-bytes:" in body
    stdin_bytes = int(
        next(line for line in body.splitlines() if line.startswith("stdin-bytes:"))
        .split(":", 1)[1].strip()
    )
    prompt_bytes = int(
        next(line for line in body.splitlines() if line.startswith("prompt-bytes:"))
        .split(":", 1)[1].strip()
    )
    assert stdin_bytes > 0
    assert prompt_bytes > 0


def test_doc_no_sessions_errors(run_fl, friction_dir):
    friction_dir.mkdir(parents=True, exist_ok=True)
    r = run_fl("doc", "--last", "5")
    assert r.returncode == 1
    assert "no sessions" in r.stderr.lower()


def test_doc_missing_claude_errors_cleanly(run_fl, friction_dir, seed_session, fl_env):
    seed_session("2026-05-09-T-12-00-foo", "body\n")

    base_path = os.environ.get("PATH", "")
    minimal = ":".join(p for p in base_path.split(":") if "fakes" not in p)
    r = run_fl(
        "doc", "--last", "1",
        env_extra={"PATH": f"{Path(__file__).resolve().parent.parent / 'bin'}:{minimal}"},
    )
    if r.returncode == 1:
        assert "claude" in r.stderr.lower()


def test_doc_name_auto_increments(run_fl, friction_dir, seed_session):
    """Regenerating a doc for the same session bumps the -N suffix instead of
    clobbering the previous output. Also: an archived doc's name is reserved."""
    seed_session("2026-05-09-T-12-00-foo", "body\n")
    archive_dir = friction_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / "fl-doc-foo-0.md").write_text("ARCHIVED-PRIOR", encoding="utf-8")

    r1 = run_fl("doc", "--last", "1")
    assert r1.returncode == 0, r1.stderr
    assert (friction_dir / "fl-doc-foo-1.md").exists()

    r2 = run_fl("doc", "--last", "1")
    assert r2.returncode == 0, r2.stderr
    assert (friction_dir / "fl-doc-foo-2.md").exists()

    # Archived prior is untouched.
    assert (archive_dir / "fl-doc-foo-0.md").read_text() == "ARCHIVED-PRIOR"


def test_doc_prompt_explains_chunk_delimiter(run_fl, friction_dir, seed_session):
    """The prompt sent to claude must teach it about the `--- ts ---`
    delimiter — that's the contract the new format relies on."""
    seed_session("2026-05-09-T-12-00-foo", "--- 2026-05-09 12:00:00 ---\nbody\n")

    # Replace the fake claude with one that captures the prompt arg verbatim.
    fakes = Path(__file__).resolve().parent / "fakes"
    capture = fakes / "claude_capture"
    captured_path = friction_dir / "_captured_prompt.txt"
    capture.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = "-p" ]; then printf "%s" "$2" > "' + str(captured_path) + '"; fi\n'
        'cat >/dev/null\n'
        'echo OK\n',
        encoding="utf-8",
    )
    capture.chmod(0o755)
    try:
        # Put a directory containing only `claude` -> claude_capture, ahead of fakes.
        shim_dir = friction_dir / "_shim"
        shim_dir.mkdir(parents=True, exist_ok=True)
        (shim_dir / "claude").symlink_to(capture)
        base_path = os.environ.get("PATH", "")
        new_path = f"{shim_dir}:{base_path}"
        r = run_fl("doc", "--last", "1", env_extra={"PATH": new_path})
        assert r.returncode == 0, r.stderr
        prompt = captured_path.read_text(encoding="utf-8")
        assert "--- YYYY-MM-DD HH:MM:SS ---" in prompt
        assert "PS1" in prompt
    finally:
        capture.unlink(missing_ok=True)


def test_doc_dash_n_single_match(run_fl, friction_dir, seed_session):
    seed_session("2026-05-09-T-12-00-foo", "body-foo\n")
    seed_session("2026-05-09-T-13-00-bar", "body-bar\n")
    r = run_fl("doc", "-n", "bar")
    assert r.returncode == 0, r.stderr
    out = friction_dir / "fl-doc-bar-0.md"
    assert out.exists()
    body = out.read_text(encoding="utf-8")
    # Only `bar` was merged — `foo` not in frontmatter.
    assert "2026-05-09-T-13-00-bar" in body
    assert "2026-05-09-T-12-00-foo" not in body
    # Resolution echo is on stderr.
    assert "matched 1 session(s) for '-n bar'" in r.stderr
    assert "2026-05-09-T-13-00-bar" in r.stderr


def test_doc_dash_n_multi_match(run_fl, friction_dir, seed_session):
    seed_session("2026-05-09-T-12-00-auth-bug", "a\n")
    seed_session("2026-05-09-T-13-00-auth-rewrite", "b\n")
    seed_session("2026-05-09-T-14-00-unrelated", "c\n")
    r = run_fl("doc", "-n", "auth")
    assert r.returncode == 0, r.stderr
    assert "matched 2 session(s) for '-n auth'" in r.stderr
    # Doc is auto-named after the most-recent matching session (auth-rewrite).
    out = friction_dir / "fl-doc-auth-rewrite-0.md"
    assert out.exists()
    body = out.read_text(encoding="utf-8")
    assert "auth-bug" in body
    assert "auth-rewrite" in body
    assert "unrelated" not in body


def test_doc_dash_n_zero_match(run_fl, seed_session):
    seed_session("2026-05-09-T-12-00-foo", "body\n")
    r = run_fl("doc", "-n", "nope")
    assert r.returncode == 1
    assert "no sessions match" in r.stderr.lower()


def test_doc_no_proceed_prompt_for_new_target(run_fl, friction_dir, seed_session):
    """Brand-new doc target: no confirmation prompt. Empty stdin → still writes."""
    seed_session("2026-05-09-T-12-00-foo", "body\n")
    r = run_fl("doc", "--last", "1", stdin="")
    assert r.returncode == 0, r.stderr
    docs = list(friction_dir.glob("fl-doc-*.md"))
    assert len(docs) == 1, docs


def test_doc_prompt_includes_format_directives(run_fl, friction_dir, seed_session):
    """The prompt must instruct claude on the strict output format (H1 title,
    no preamble) — these are what stop the docs from rendering as nested
    fragments inside whatever consumes them."""
    seed_session("2026-05-09-T-12-00-foo", "--- 2026-05-09 12:00:00 ---\nbody\n")
    fakes = Path(__file__).resolve().parent / "fakes"
    capture = fakes / "claude_capture_fmt"
    captured_path = friction_dir / "_captured_fmt.txt"
    capture.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = "-p" ]; then printf "%s" "$2" > "' + str(captured_path) + '"; fi\n'
        'cat >/dev/null\n'
        'echo OK\n',
        encoding="utf-8",
    )
    capture.chmod(0o755)
    try:
        shim_dir = friction_dir / "_shim_fmt"
        shim_dir.mkdir(parents=True, exist_ok=True)
        (shim_dir / "claude").symlink_to(capture)
        base_path = os.environ.get("PATH", "")
        r = run_fl("doc", "--last", "1",
                   env_extra={"PATH": f"{shim_dir}:{base_path}"})
        assert r.returncode == 0, r.stderr
        prompt = captured_path.read_text(encoding="utf-8")
        # Strict-format directives present.
        assert "Start with a single `# `" in prompt
        assert "Do not preface or postscript" in prompt
    finally:
        capture.unlink(missing_ok=True)


def test_doc_archived_session_excluded(run_fl, friction_dir, seed_session):
    seed_session("2026-05-09-T-12-00-keep", "body\n")
    archive_dir = friction_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / "2026-05-08-T-09-00-old.md").write_text("ARCHIVED\n")

    r = run_fl("doc", "--last", "10")
    assert r.returncode == 0, r.stderr
    out = friction_dir / "fl-doc-keep-0.md"
    body = out.read_text(encoding="utf-8")
    # The archived session must not have been merged in. The fake echoes the
    # stdin byte count; the keep-only run must be small.
    stdin_bytes = int(
        next(line for line in body.splitlines() if line.startswith("stdin-bytes:"))
        .split(":", 1)[1].strip()
    )
    # Just "## <id>\n\nbody\n\n" merged content — well under 100 bytes.
    assert stdin_bytes < 200
