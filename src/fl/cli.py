"""Argparse dispatcher for `python -m fl`.

Bare `fl` (no args) routes to `fl note` so paste-and-go is the default
one-keystroke path. Recognized subcommands: note, doc, archive, ls.
"""

from __future__ import annotations

import argparse
import re
import sys

from datetime import datetime
from pathlib import Path

from rich import box
from rich.table import Table

from . import archive, doc, note, storage, ui, view

_KNOWN_CMDS = {"note", "doc", "archive", "ls", "view", "help", "--help", "-h"}


def _cmd_ls() -> int:
    active = storage.list_sessions()
    archived = storage.list_archived_sessions()
    active_docs = storage.list_docs(storage.ROOT)
    archived_docs = storage.list_docs(storage.ARCHIVE)
    if not active and not archived and not active_docs and not archived_docs:
        ui.info("· no sessions")
        return 0

    # session-stem → [doc Path, ...] across both active and archived docs.
    # Multiple docs per session arise from regen (`-N` suffix bumps).
    docs_for_session: dict[str, list[Path]] = {}
    orphan_docs: list[Path] = []
    all_session_stems = {p.stem for p in active} | {p.stem for p in archived}
    for d in (*active_docs, *archived_docs):
        stem = storage.read_doc_session(d)
        if stem and stem in all_session_stems:
            docs_for_session.setdefault(stem, []).append(d)
        else:
            orphan_docs.append(d)

    def _mtime(p: Path) -> str:
        try:
            return datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            return "?"

    if active or archived or orphan_docs:
        ui.info(f"· paths relative to {storage.ROOT}/")

    if active or archived:
        ui.table(_build_session_table(active, archived, docs_for_session, _mtime))
    else:
        ui.info("· no sessions")

    if orphan_docs:
        ui.table(_build_orphan_table(orphan_docs, _mtime))
    return 0


def _build_session_table(
    active: list[Path],
    archived: list[Path],
    docs_for_session: dict[str, list[Path]],
    mtime_fn,
) -> Table:
    t = Table(show_lines=False, box=box.SQUARE)
    t.add_column("shortname", overflow="fold")
    t.add_column("lines", justify="right", no_wrap=True)
    t.add_column("session", overflow="fold")
    t.add_column("doc", overflow="fold")
    t.add_column("mtime", no_wrap=True)

    def _add(p: Path, dim: bool) -> None:
        rel = p.relative_to(storage.ROOT)
        docs = docs_for_session.get(p.stem, [])
        if docs:
            doc_cell = "\n".join(str(d.relative_to(storage.ROOT)) for d in docs)
        else:
            doc_cell = "-"
        t.add_row(
            storage.session_suffix(p.stem),
            f"{storage.line_count(p)}L",
            str(rel),
            doc_cell,
            mtime_fn(p),
            style="bright_black" if dim else None,
        )

    for p in active:
        _add(p, dim=False)
    for p in archived:
        _add(p, dim=True)
    return t


def _build_orphan_table(orphans: list[Path], mtime_fn) -> Table:
    t = Table(show_lines=False, box=box.SQUARE,
              title="orphan docs (no matching session)",
              title_justify="left", title_style="")
    t.add_column("shortname", overflow="fold")
    t.add_column("lines", justify="right", no_wrap=True)
    t.add_column("doc", overflow="fold")
    t.add_column("mtime", no_wrap=True)
    for d in orphans:
        rel = d.relative_to(storage.ROOT)
        dim = d.parent == storage.ARCHIVE
        # Drop both the fl-doc- prefix and the TS-prefix so the shortname
        # is just the user-supplied tail.
        shortname = d.stem
        if shortname.startswith(storage.DOC_PREFIX):
            shortname = shortname[len(storage.DOC_PREFIX):]
        shortname = re.sub(r"^\d{4}-\d{2}-\d{2}-T-\d{2}-\d{2}-", "", shortname)
        t.add_row(
            shortname,
            f"{storage.line_count(d)}L",
            str(rel),
            mtime_fn(d),
            style="bright_black" if dim else None,
        )
    return t


def _doc_parser() -> argparse.ArgumentParser:
    d = argparse.ArgumentParser(prog="fl doc", add_help=True)
    d.add_argument("-n", "--name", dest="name", metavar="TERM",
                   help="session whose name matches TERM (same fuzzy rules as `fl note -n`)")
    return d


def _view_parser() -> argparse.ArgumentParser:
    d = argparse.ArgumentParser(prog="fl view", add_help=True)
    d.add_argument("-n", "--name", dest="name", metavar="TERM",
                   help="open the session or doc matching TERM in $EDITOR "
                        "(same fuzzy rules as `fl note -n`)")
    return d


def _print_help() -> None:
    sys.stderr.write(
        "fl — friction log\n"
        "\n"
        "usage:\n"
        "  fl [-n NAME] [text...]      append a note (stdin / args / $EDITOR)\n"
        "  fl note [-n NAME] [text...] same as bare fl\n"
        "  fl ls                       list all sessions and their docs\n"
        "  fl doc [-n NAME]            pick a session and summarize via Claude\n"
        "  fl view [-n NAME]           open a session or doc in $EDITOR\n"
        "  fl archive                  interactively archive sessions\n"
        "\n"
        "session names may be partial substrings of an existing session's\n"
        "post-timestamp suffix; if none match, a new session is created.\n"
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] in ("help", "--help", "-h"):
        _print_help()
        return 0

    # Default: bare invocation OR unknown leading token → route to note.
    if not args or args[0] not in _KNOWN_CMDS:
        return note.cmd_note(args)

    cmd, rest = args[0], args[1:]

    if cmd == "note":
        return note.cmd_note(rest)

    if cmd == "ls":
        argparse.ArgumentParser(
            prog="fl ls",
            description="list all sessions and their docs (active + archived).",
        ).parse_args(rest)
        return _cmd_ls()

    if cmd == "archive":
        argparse.ArgumentParser(
            prog="fl archive",
            description="interactively move sessions (and their docs) to "
                        "~/.friction-log/archive/.",
        ).parse_args(rest)
        try:
            return archive.cmd_archive()
        except KeyboardInterrupt:
            ui.info("· interrupted")
            return 130

    if cmd == "doc":
        ns = _doc_parser().parse_args(rest)
        try:
            return doc.cmd_doc(name=ns.name)
        except KeyboardInterrupt:
            ui.info("· interrupted")
            return 130

    if cmd == "view":
        ns = _view_parser().parse_args(rest)
        try:
            return view.cmd_view(name=ns.name)
        except KeyboardInterrupt:
            ui.info("· interrupted")
            return 130

    _print_help()
    return 2
