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


def _make_session(root: Path, stem: str, body: str = "body\n") -> Path:
    p = root / f"{stem}.md"
    p.write_text(body, encoding="utf-8")
    return p


def _make_doc(directory: Path, name: str, sessions: list[str]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    fm = "---\nsessions:\n" + "".join(f"  - {s}\n" for s in sessions) + "---\n\n"
    p = directory / f"fl-doc-{name}.md"
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


def _seed_doc(friction_dir, name: str, sessions: list[str], body: str = "BODY\n"):
    friction_dir.mkdir(parents=True, exist_ok=True)
    fm = "---\nsessions:\n" + "".join(f"  - {s}\n" for s in sessions) + "---\n\n"
    p = friction_dir / f"fl-doc-{name}.md"
    p.write_text(fm + body, encoding="utf-8")
    return p


def test_archive_no_sessions(run_fl):
    r = run_fl("archive")
    assert r.returncode == 0
    assert "no sessions" in r.stderr.lower()


def test_archive_excludes_archived_from_listing(run_fl, friction_dir, seed_session):
    """An already-archived file under archive/ must not appear in `fl doc`'s
    candidate set. We assert this here because archive's main contract is
    that moving a session out of the top-level dir hides it."""
    archive_dir = friction_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / "2026-05-08-T-09-00-old.md").write_text("old\n")

    seed_session("2026-05-09-T-12-00-keep", "kept\n")
    r = run_fl("doc", "--last", "10", stdin="x\nn\n")
    # `--last 10` will pick everything available; only `keep` should be available.
    # We just ensure no error and that the merge selection summary mentions 1 session.
    assert r.returncode == 0
    assert "1 session" in r.stderr


# --- in-process tests for the post-picker move logic ---


def test_archive_moves_selected_session(fl_root, monkeypatch):
    from fl import archive
    s = _make_session(fl_root, "2026-05-09-T-12-00-foo")
    _stub_picker(monkeypatch, [s])
    asked = _stub_confirm(monkeypatch, True)

    rc = archive.cmd_archive()
    assert rc == 0
    # No collision → no confirm prompt asked.
    assert asked == [], asked
    assert not s.exists()
    assert (fl_root / "archive" / s.name).exists()


def test_archive_pulls_associated_active_doc(fl_root, monkeypatch):
    from fl import archive
    s = _make_session(fl_root, "2026-05-09-T-12-00-foo")
    doc = _make_doc(fl_root, "foo-0", ["2026-05-09-T-12-00-foo"])
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
    archived_doc = _make_doc(fl_root / "archive", "foo-0", ["2026-05-09-T-12-00-foo"])
    _stub_picker(monkeypatch, [s])
    _stub_confirm(monkeypatch, True)

    rc = archive.cmd_archive()
    assert rc == 0
    assert (fl_root / "archive" / s.name).exists()
    # Pre-archived doc untouched.
    assert archived_doc.exists()
    assert archived_doc.read_text().startswith("---")


def test_archive_doc_follows_partial_session_archive(fl_root, monkeypatch):
    """Doc references two sessions; archive only one → doc is still pulled
    along (current contract per archive.py docstring)."""
    from fl import archive
    s1 = _make_session(fl_root, "2026-05-09-T-12-00-foo")
    _make_session(fl_root, "2026-05-09-T-13-00-bar")
    doc = _make_doc(fl_root, "merged-0",
                    ["2026-05-09-T-12-00-foo", "2026-05-09-T-13-00-bar"])
    _stub_picker(monkeypatch, [s1])
    _stub_confirm(monkeypatch, True)

    rc = archive.cmd_archive()
    assert rc == 0
    assert (fl_root / "archive" / doc.name).exists()
    assert not doc.exists()


def test_archive_collision_prompts_overwrite(fl_root, monkeypatch):
    from fl import archive
    s = _make_session(fl_root, "2026-05-09-T-12-00-foo", body="NEW\n")
    # Pre-existing archived copy with the same filename.
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
    # Active session still in place, archived copy untouched.
    assert s.read_text() == "NEW\n"
    assert (fl_root / "archive" / s.name).read_text() == "OLD\n"
