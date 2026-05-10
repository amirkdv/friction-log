"""Unit tests for storage helpers and the archive-pulls-doc integration.

In-process: hard to drive the interactive `questionary` picker via subprocess,
so we test `archive._archive_associated_docs` directly with `storage.ROOT`
patched to a tmp dir.
"""

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


def _seed_doc(dir: Path, name: str, sessions: list[str]) -> Path:
    fm = "---\nsessions:\n" + "".join(f"  - {s}\n" for s in sessions) + "---\n\nBODY\n"
    p = dir / f"fl-doc-{name}.md"
    p.write_text(fm, encoding="utf-8")
    return p


def test_read_doc_sessions_parses_frontmatter(fl_root: Path):
    doc = _seed_doc(fl_root, "x-0", ["2026-05-09-T-12-00-foo", "2026-05-09-T-13-00-bar"])
    assert storage.read_doc_sessions(doc) == [
        "2026-05-09-T-12-00-foo",
        "2026-05-09-T-13-00-bar",
    ]


def test_read_doc_sessions_no_frontmatter(fl_root: Path):
    p = fl_root / "fl-doc-handwritten.md"
    p.write_text("# just a doc\nno frontmatter here\n", encoding="utf-8")
    assert storage.read_doc_sessions(p) == []


def test_next_doc_path_increments(fl_root: Path):
    assert storage.next_doc_path("foo").name == "fl-doc-foo-0.md"
    (fl_root / "fl-doc-foo-0.md").write_text("x")
    assert storage.next_doc_path("foo").name == "fl-doc-foo-1.md"
    # Archived prior also reserves the name.
    (fl_root / "archive" / "fl-doc-foo-1.md").write_text("x")
    assert storage.next_doc_path("foo").name == "fl-doc-foo-2.md"


def test_next_doc_path_sanitizes_suffix(fl_root: Path):
    # Spaces / slashes must not produce path traversal or weird filenames.
    p = storage.next_doc_path("Some Suffix/With Slash")
    assert p.parent == fl_root
    assert p.name == "fl-doc-some-suffix-with-slash-0.md"


def test_archive_pulls_doc_when_any_session_matches(fl_root: Path):
    """Per the archive contract: a doc follows its sessions on first archive
    of any referenced session, even if siblings are still active."""
    _seed_doc(fl_root, "bar-0", ["2026-05-09-T-12-00-foo", "2026-05-09-T-13-00-bar"])
    moved = archive._archive_associated_docs({"2026-05-09-T-12-00-foo"})
    assert moved == 1
    assert not (fl_root / "fl-doc-bar-0.md").exists()
    assert (fl_root / "archive" / "fl-doc-bar-0.md").exists()


def test_archive_leaves_unrelated_doc(fl_root: Path):
    _seed_doc(fl_root, "bar-0", ["2026-05-09-T-13-00-bar"])
    moved = archive._archive_associated_docs({"2026-05-09-T-12-00-foo"})
    assert moved == 0
    assert (fl_root / "fl-doc-bar-0.md").exists()


def test_archive_no_op_on_empty_set(fl_root: Path):
    _seed_doc(fl_root, "bar-0", ["2026-05-09-T-13-00-bar"])
    assert archive._archive_associated_docs(set()) == 0
    assert (fl_root / "fl-doc-bar-0.md").exists()
