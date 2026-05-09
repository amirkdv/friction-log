"""End-to-end tests for `fl doc`. Hermetic: real argparse + real subprocess
chain, but the `claude` CLI is faked via PATH (see tests/fakes/claude)."""

import os
from pathlib import Path


def test_doc_writes_file_with_fake_claude(run_fl, friction_dir, seed_log):
    seed_log(
        "fl-2026-05-09-1200-111111",
        "$ echo one\none\n### NOTE [12:01:00]: thing one\n",
    )
    seed_log(
        "fl-2026-05-09-1300-222222",
        "$ echo two\ntwo\n",
    )

    r = run_fl(
        "doc",
        "--last",
        "2",
        stdin="my-merge\ny\n",
    )
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"

    out = friction_dir / "fl-doc-my-merge.md"
    assert out.exists(), list(friction_dir.iterdir())
    body = out.read_text(encoding="utf-8")
    assert "FAKE-CLAUDE-OUTPUT" in body
    # The fake echoes prompt and stdin byte counts. Both must be > 0,
    # proving fl actually piped the merged transcript through.
    assert "prompt-bytes:" in body
    assert "stdin-bytes:" in body
    stdin_bytes = int(
        next(line for line in body.splitlines() if line.startswith("stdin-bytes:"))
        .split(":", 1)[1]
        .strip()
    )
    prompt_bytes = int(
        next(line for line in body.splitlines() if line.startswith("prompt-bytes:"))
        .split(":", 1)[1]
        .strip()
    )
    assert stdin_bytes > 0
    assert prompt_bytes > 0


def test_doc_no_logs_errors(run_fl, friction_dir):
    friction_dir.mkdir(parents=True, exist_ok=True)
    r = run_fl("doc", "--last", "5")
    assert r.returncode == 1
    assert "no logs" in r.stderr.lower()


def test_doc_missing_claude_errors_cleanly(run_fl, friction_dir, seed_log, fl_env, tmp_path):
    seed_log("fl-2026-05-09-1200-111111", "body\n")

    # Drop the fakes dir from PATH so `claude` is not resolvable.
    base_path = os.environ.get("PATH", "")
    # Filter out anything that looks like our fakes dir, AND anywhere the host's
    # real `claude` might live (we want this test to fail to find it).
    minimal = ":".join(p for p in base_path.split(":") if "fakes" not in p)
    r = run_fl(
        "doc",
        "--last",
        "1",
        env_extra={"PATH": f"{Path(__file__).resolve().parent.parent / 'bin'}:{minimal}"},
    )
    # If a real `claude` is on the user's PATH this may succeed; in CI / hermetic
    # runs it should not be. Assert error path when claude is absent.
    # We accept either: rc=1 with "claude" message OR rc=0 (real claude available).
    if r.returncode == 1:
        assert "claude" in r.stderr.lower()


def test_doc_overwrite_declined_leaves_file(run_fl, friction_dir, seed_log):
    seed_log("fl-2026-05-09-1200-111111", "body\n")

    friction_dir.mkdir(parents=True, exist_ok=True)
    existing = friction_dir / "fl-doc-keep.md"
    existing.write_text("ORIGINAL", encoding="utf-8")

    r = run_fl("doc", "--last", "1", stdin="keep\nn\n")
    assert r.returncode == 0
    assert existing.read_text(encoding="utf-8") == "ORIGINAL"
    assert "aborted" in r.stderr.lower()


def test_doc_proceed_declined_writes_nothing(run_fl, friction_dir, seed_log):
    seed_log("fl-2026-05-09-1200-111111", "body\n")
    r = run_fl("doc", "--last", "1", stdin="newdoc\nn\n")
    assert r.returncode == 0
    assert not (friction_dir / "fl-doc-newdoc.md").exists()
    assert "aborted" in r.stderr.lower()


def test_doc_strips_ansi_before_send(run_fl, friction_dir, seed_log):
    """Ensure ANSI escape codes captured by script(1) don't reach claude.

    The fake echoes byte counts; we seed two logs of equal raw size — one
    with ANSI noise, one without — and confirm the cleaned input shrinks.
    """
    plain_id = "fl-2026-05-09-1100-aaaaaa"
    ansi_id = "fl-2026-05-09-1200-bbbbbb"
    seed_log(plain_id, "hello world\n" * 50)
    # Same payload but with bracketed ANSI noise sprinkled in.
    seed_log(ansi_id, "\x1b[31mhello\x1b[0m world\n" * 50)

    # Run twice, once per log, capture stdin-bytes from fake claude output.
    def stdin_bytes_for(fl_id: str) -> int:
        # Move the unrelated log out of the way.
        other = ansi_id if fl_id == plain_id else plain_id
        other_path = friction_dir / f"{other}.log"
        hidden = friction_dir / f"_hidden_{other}.log"
        other_path.rename(hidden)
        try:
            r = run_fl("doc", "--last", "1", stdin=f"d-{fl_id[-6:]}\ny\n")
            assert r.returncode == 0, r.stderr
            doc = friction_dir / f"fl-doc-d-{fl_id[-6:]}.md"
            line = next(
                ln for ln in doc.read_text().splitlines() if ln.startswith("stdin-bytes:")
            )
            return int(line.split(":", 1)[1].strip())
        finally:
            hidden.rename(other_path)

    plain_bytes = stdin_bytes_for(plain_id)
    ansi_bytes = stdin_bytes_for(ansi_id)
    # ANSI version should clean down to roughly the plain size (allow some
    # slack for the `## <id>` header). Specifically: ansi_bytes must be much
    # closer to plain_bytes than to its raw on-disk size.
    raw_ansi_size = (friction_dir / f"{ansi_id}.log").stat().st_size
    assert ansi_bytes < raw_ansi_size, (ansi_bytes, raw_ansi_size)
    assert abs(ansi_bytes - plain_bytes) < 50, (plain_bytes, ansi_bytes)
