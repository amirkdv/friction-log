"""Unit tests for storage helpers and the archive-pulls-doc integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from fl import archive, storage


@pytest.fixture
def fl_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "friction-log"
    root.mkdir()
    (root / "archive").mkdir()
    monkeypatch.setattr(storage, "ROOT", root)
    monkeypatch.setattr(storage, "ARCHIVE", root / "archive")
    return root


def _seed_doc(dir: Path, stem: str, session_stem: str) -> Path:
    fm = f"---\nsession: {session_stem}\n---\n\nBODY\n"
    p = dir / f"{stem}.md"
    p.write_text(fm, encoding="utf-8")
    return p


def test_read_doc_session_parses_frontmatter(fl_root: Path):
    doc = _seed_doc(
        fl_root,
        "fl-doc-2026-05-09-T-12-00-foo",
        "fl-session-2026-05-09-T-12-00-foo",
    )
    assert storage.read_doc_session(doc) == "fl-session-2026-05-09-T-12-00-foo"


def test_read_doc_session_no_frontmatter(fl_root: Path):
    p = fl_root / "fl-doc-handwritten.md"
    p.write_text("# just a doc\nno frontmatter here\n", encoding="utf-8")
    assert storage.read_doc_session(p) is None


def test_read_doc_session_legacy_sessions_list(fl_root: Path):
    """Legacy multi-session frontmatter still resolves to a single source."""
    p = fl_root / "fl-doc-legacy.md"
    p.write_text(
        "---\nsessions:\n  - 2026-05-09-T-12-00-foo\n  - 2026-05-09-T-13-00-bar\n---\n\nBODY\n",
        encoding="utf-8",
    )
    assert storage.read_doc_session(p) == "2026-05-09-T-12-00-foo"


def test_next_doc_path_uses_session_stem(fl_root: Path):
    p = storage.next_doc_path("fl-session-2026-05-09-T-12-00-foo")
    assert p.name == "fl-doc-2026-05-09-T-12-00-foo.md"


def test_next_doc_path_increments_on_collision(fl_root: Path):
    session = "fl-session-2026-05-09-T-12-00-foo"
    assert storage.next_doc_path(session).name == "fl-doc-2026-05-09-T-12-00-foo.md"

    (fl_root / "fl-doc-2026-05-09-T-12-00-foo.md").write_text("x")
    assert storage.next_doc_path(session).name == "fl-doc-2026-05-09-T-12-00-foo-1.md"

    (fl_root / "fl-doc-2026-05-09-T-12-00-foo-1.md").write_text("x")
    # Archived prior also reserves the name.
    (fl_root / "archive" / "fl-doc-2026-05-09-T-12-00-foo-2.md").write_text("x")
    assert storage.next_doc_path(session).name == "fl-doc-2026-05-09-T-12-00-foo-3.md"


def test_new_session_path_has_fl_session_prefix(fl_root: Path):
    from datetime import datetime
    p = storage.new_session_path("foo", now=datetime(2026, 5, 9, 12, 0))
    assert p.name == "fl-session-2026-05-09-T-12-00-foo.md"


def test_archive_pulls_doc_when_session_archived(fl_root: Path):
    _seed_doc(
        fl_root,
        "fl-doc-2026-05-09-T-12-00-foo",
        "fl-session-2026-05-09-T-12-00-foo",
    )
    moved = archive._archive_associated_docs({"fl-session-2026-05-09-T-12-00-foo"})
    assert moved == 1
    assert not (fl_root / "fl-doc-2026-05-09-T-12-00-foo.md").exists()
    assert (fl_root / "archive" / "fl-doc-2026-05-09-T-12-00-foo.md").exists()


def test_archive_leaves_unrelated_doc(fl_root: Path):
    _seed_doc(
        fl_root,
        "fl-doc-2026-05-09-T-13-00-bar",
        "fl-session-2026-05-09-T-13-00-bar",
    )
    moved = archive._archive_associated_docs({"fl-session-2026-05-09-T-12-00-foo"})
    assert moved == 0
    assert (fl_root / "fl-doc-2026-05-09-T-13-00-bar.md").exists()


def test_archive_no_op_on_empty_set(fl_root: Path):
    _seed_doc(
        fl_root,
        "fl-doc-2026-05-09-T-13-00-bar",
        "fl-session-2026-05-09-T-13-00-bar",
    )
    assert archive._archive_associated_docs(set()) == 0
    assert (fl_root / "fl-doc-2026-05-09-T-13-00-bar.md").exists()
