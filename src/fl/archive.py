"""`fl archive` — interactively move sessions to ~/.friction-log/archive/."""

from __future__ import annotations

from . import storage, ui


def cmd_archive() -> int:
    storage.ensure_root()
    sessions = storage.list_sessions()
    if not sessions:
        ui.info("· no sessions to archive")
        return 0

    selected = ui.pick_sessions(
        sessions,
        "select sessions to archive (space to toggle, enter to confirm):",
    )
    if not selected:
        ui.info("· nothing selected, aborting")
        return 0

    storage.ARCHIVE.mkdir(parents=True, exist_ok=True)
    clobbers = [s for s in selected if (storage.ARCHIVE / s.name).exists()]
    if clobbers:
        ui.error(f"! {len(clobbers)} target(s) already exist in archive:")
        for s in clobbers:
            ui.error(f"    {s.name}")
        if not ui.confirm("overwrite?"):
            ui.info("· aborted")
            return 0

    ui.info(f"→ moving {len(selected)} session(s) to {storage.ARCHIVE}")
    moved = 0
    archived_stems: set[str] = set()
    for src in selected:
        dst = storage.ARCHIVE / src.name
        try:
            src.replace(dst)
            moved += 1
            archived_stems.add(src.stem)
        except OSError as e:
            ui.error(f"! failed to move {src.name}: {e}")

    docs_moved = _archive_associated_docs(archived_stems)

    if docs_moved:
        ui.success(f"✓ archived {moved} session(s) + {docs_moved} doc(s)")
    else:
        ui.success(f"✓ archived {moved} session(s)")
    return 0


def _archive_associated_docs(archived_stems: set[str]) -> int:
    """Move any active doc that references at least one just-archived session.

    Per the archive contract: a doc follows its sessions, so the first archive
    of any referenced session pulls the doc along even if other referenced
    sessions remain active.
    """
    if not archived_stems:
        return 0
    moved = 0
    for doc in storage.list_docs(storage.ROOT):
        stems = set(storage.read_doc_sessions(doc))
        if not stems & archived_stems:
            continue
        dst = storage.ARCHIVE / doc.name
        try:
            doc.replace(dst)
            moved += 1
            ui.info(f"  · doc {doc.name} → archive")
        except OSError as e:
            ui.error(f"! failed to move {doc.name}: {e}")
    return moved
