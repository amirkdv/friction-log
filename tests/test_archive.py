"""Tests for `fl archive`.

The picker (`questionary.checkbox`) requires a TTY. End-to-end subprocess
runs can only exercise the no-selection path. For the actual move logic
(doc-following, collision confirmation), we drop to in-process tests that
monkeypatch the storage roots and the picker.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_SRC = Path(__file__).resolve().parent.parent / "src"
if str(REPO_SRC) not in sys.path:
    sys.path.insert(0, str(REPO_SRC))


@pytest.fixture
def fl_root(tmp_path, monkeypatch):
    """Redirect storage.ROOT/ARCHIVE to a per-test tmp dir."""
    from fl import storage

    root = tmp_path / "fl-store"
    archive = root / "archive"
    root.mkdir()
    monkeypatch.setattr(storage, "ROOT", root)
    monkeypatch.setattr(storage, "ARCHIVE", archive)
    return root


def _session_stem(name: str) -> str:
    return name if name.startswith("fl-session-") else f"fl-session-{name}"


def _make_session(root: Path, name: str, body: str = "body\n") -> Path:
    p = root / f"{_session_stem(name)}.md"
    p.write_text(body, encoding="utf-8")
    return p


def _make_doc(directory: Path, session_stem: str) -> Path:
    """Doc named to mirror its session, with single-session frontmatter."""
    directory.mkdir(parents=True, exist_ok=True)
    session_stem = _session_stem(session_stem)
    doc_stem = "fl-doc-" + session_stem[len("fl-session-"):]
    fm = f"---\nsession: {session_stem}\n---\n\n"
    p = directory / f"{doc_stem}.md"
    p.write_text(fm + "BODY\n", encoding="utf-8")
    return p


def _stub_picker(monkeypatch, returns: list[Path]) -> None:
    from fl import ui
    monkeypatch.setattr(ui, "pick_sessions", lambda *a, **kw: returns)


def _stub_confirm(monkeypatch, value: bool):
    """Capture every confirm prompt in a list and return the canned value."""
    from fl import ui
    asked: list[str] = []

    def _fn(prompt: str, default: bool = False) -> bool:
        asked.append(prompt)
        return value

    monkeypatch.setattr(ui, "confirm", _fn)
    return asked


def test_archive_no_sessions(run_fl):
    r = run_fl("archive")
    assert r.returncode == 0
    assert "no sessions" in r.stderr.lower()


def test_archive_help_does_not_open_picker(run_fl, seed_session):
    """`fl archive --help` must print help and exit — never open the
    interactive picker (which would block on a non-tty subprocess)."""
    # Seed a session so that, without the help short-circuit, archive
    # would otherwise try to open the picker and hang.
    seed_session("2026-05-09-T-12-00-foo", "body\n")
    r = run_fl("archive", "--help", timeout=5)
    assert r.returncode == 0
    assert "usage" in (r.stdout + r.stderr).lower()


def test_ls_help_does_not_render_table(run_fl, seed_session):
    seed_session("2026-05-09-T-12-00-foo", "body\n")
    r = run_fl("ls", "--help", timeout=5)
    assert r.returncode == 0
    assert "usage" in (r.stdout + r.stderr).lower()


def test_archive_excludes_archived_from_doc_listing(run_fl, friction_dir, seed_session):
    """An already-archived file under archive/ must not appear in `fl doc`'s
    candidate set. The active candidate `keep` is selectable via -n."""
    archive_dir = friction_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / "fl-session-2026-05-08-T-09-00-old.md").write_text("old\n")

    seed_session("2026-05-09-T-12-00-keep", "kept\n")
    r = run_fl("doc", "-n", "old")
    assert r.returncode == 1
    assert "no sessions match" in r.stderr.lower()


# --- in-process tests for the post-picker move logic ---


def test_archive_moves_selected_session(fl_root, monkeypatch):
    from fl import archive
    s = _make_session(fl_root, "2026-05-09-T-12-00-foo")
    _stub_picker(monkeypatch, [s])
    asked = _stub_confirm(monkeypatch, True)

    rc = archive.cmd_archive()
    assert rc == 0
    assert asked == [], asked
    assert not s.exists()
    assert (fl_root / "archive" / s.name).exists()


def test_archive_pulls_associated_active_doc(fl_root, monkeypatch):
    from fl import archive
    s = _make_session(fl_root, "2026-05-09-T-12-00-foo")
    doc = _make_doc(fl_root, "2026-05-09-T-12-00-foo")
    _stub_picker(monkeypatch, [s])
    _stub_confirm(monkeypatch, True)

    rc = archive.cmd_archive()
    assert rc == 0
    assert not s.exists()
    assert not doc.exists()
    assert (fl_root / "archive" / s.name).exists()
    assert (fl_root / "archive" / doc.name).exists()


def test_archive_skips_already_archived_doc(fl_root, monkeypatch):
    """Doc whose only copy is already in archive/ → archive move is a no-op
    for the doc; session still moves."""
    from fl import archive
    s = _make_session(fl_root, "2026-05-09-T-12-00-foo")
    archived_doc = _make_doc(fl_root / "archive", "2026-05-09-T-12-00-foo")
    _stub_picker(monkeypatch, [s])
    _stub_confirm(monkeypatch, True)

    rc = archive.cmd_archive()
    assert rc == 0
    assert (fl_root / "archive" / s.name).exists()
    assert archived_doc.exists()
    assert archived_doc.read_text().startswith("---")


def test_archive_unrelated_doc_stays(fl_root, monkeypatch):
    """A doc whose session isn't being archived stays put."""
    from fl import archive
    s_foo = _make_session(fl_root, "2026-05-09-T-12-00-foo")
    _make_session(fl_root, "2026-05-09-T-13-00-bar")
    bar_doc = _make_doc(fl_root, "2026-05-09-T-13-00-bar")
    _stub_picker(monkeypatch, [s_foo])
    _stub_confirm(monkeypatch, True)

    rc = archive.cmd_archive()
    assert rc == 0
    # foo got archived, bar's doc is untouched.
    assert (fl_root / "archive" / s_foo.name).exists()
    assert bar_doc.exists()
    assert not (fl_root / "archive" / bar_doc.name).exists()


def test_archive_collision_prompts_overwrite(fl_root, monkeypatch):
    from fl import archive
    s = _make_session(fl_root, "2026-05-09-T-12-00-foo", body="NEW\n")
    (fl_root / "archive").mkdir(parents=True, exist_ok=True)
    (fl_root / "archive" / s.name).write_text("OLD\n", encoding="utf-8")
    _stub_picker(monkeypatch, [s])
    asked = _stub_confirm(monkeypatch, True)

    rc = archive.cmd_archive()
    assert rc == 0
    assert any("overwrite" in q.lower() for q in asked), asked
    assert (fl_root / "archive" / s.name).read_text() == "NEW\n"


def test_archive_collision_decline_preserves_both(fl_root, monkeypatch):
    from fl import archive
    s = _make_session(fl_root, "2026-05-09-T-12-00-foo", body="NEW\n")
    (fl_root / "archive").mkdir(parents=True, exist_ok=True)
    (fl_root / "archive" / s.name).write_text("OLD\n", encoding="utf-8")
    _stub_picker(monkeypatch, [s])
    _stub_confirm(monkeypatch, False)

    rc = archive.cmd_archive()
    assert rc == 0
    assert s.read_text() == "NEW\n"
    assert (fl_root / "archive" / s.name).read_text() == "OLD\n"
