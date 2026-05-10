"""Argparse dispatcher for `python -m fl`.

Bare `fl` (no args) routes to `fl note` so paste-and-go is the default
one-keystroke path. Recognized subcommands: note, doc, archive, ls.
"""

from __future__ import annotations

import argparse
import sys

from datetime import datetime
from pathlib import Path

from . import archive, doc, note, storage, ui

_KNOWN_CMDS = {"note", "doc", "archive", "ls", "help", "--help", "-h"}


def _cmd_ls() -> int:
    active = storage.list_sessions()
    archived = storage.list_archived_sessions()
    active_docs = storage.list_docs(storage.ROOT)
    archived_docs = storage.list_docs(storage.ARCHIVE)
    if not active and not archived and not active_docs and not archived_docs:
        ui.info("· no sessions")
        return 0

    # session-stem → doc Path index across both active and archived docs.
    doc_for_session: dict[str, Path] = {}
    orphan_docs: list[Path] = []
    all_session_stems = {p.stem for p in active} | {p.stem for p in archived}
    for d in (*active_docs, *archived_docs):
        stem = storage.read_doc_session(d)
        if stem and stem in all_session_stems:
            doc_for_session.setdefault(stem, d)
        else:
            orphan_docs.append(d)

    def _mtime(p: Path) -> str:
        try:
            return datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            return "?"

    # Column widths.
    W_TIME = 16
    W_LINES = 6
    W_SESSION = 48
    W_DOC = 48

    def _row(time: str, lines: str, session: str, doc_name: str, preview: str) -> str:
        return (
            f"{time:<{W_TIME}}  {lines:>{W_LINES}}  "
            f"{session:<{W_SESSION}}  {doc_name:<{W_DOC}}  {preview}"
        )

    def _session_row(p: Path, dim: bool) -> None:
        rel = p.relative_to(storage.ROOT)
        d = doc_for_session.get(p.stem)
        doc_name = str(d.relative_to(storage.ROOT)) if d is not None else "-"
        line = _row(
            _mtime(p),
            f"{storage.line_count(p)}L",
            str(rel),
            doc_name,
            storage.first_chunk_preview(p),
        )
        (ui.dim if dim else ui.plain)(line)

    if active or archived:
        header = _row("MTIME", "LINES", "SESSION", "DOC", "PREVIEW")
        ui.plain(header)
        ui.plain("-" * len(header.rstrip()))
        for p in active:
            _session_row(p, dim=False)
        for p in archived:
            _session_row(p, dim=True)
    else:
        ui.info("· no sessions")

    if orphan_docs:
        if active or archived:
            ui.plain("")
        ui.plain("orphan docs (no matching session):")
        for d in orphan_docs:
            rel = d.relative_to(storage.ROOT)
            fmt = ui.dim if d.parent == storage.ARCHIVE else ui.plain
            fmt(_row(
                _mtime(d),
                f"{storage.line_count(d)}L",
                "-",
                str(rel),
                "",
            ))
    return 0


def _doc_parser() -> argparse.ArgumentParser:
    d = argparse.ArgumentParser(prog="fl doc", add_help=True)
    d.add_argument("-n", "--name", dest="name", metavar="TERM",
                   help="session whose name matches TERM (same fuzzy rules as `fl note -n`)")
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
        return _cmd_ls()

    if cmd == "archive":
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

    _print_help()
    return 2
