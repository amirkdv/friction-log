"""Argparse dispatcher for `python -m fl`.

Bare `fl` (no args) routes to `fl note` so paste-and-go is the default
one-keystroke path. Recognized subcommands: note, doc, archive.
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

    # Build session-stem -> [doc names] index across both active and archived
    # docs, so each session row can advertise the doc(s) it feeds.
    session_docs: dict[str, list[str]] = {}
    for d in (*active_docs, *archived_docs):
        for stem in storage.read_doc_sessions(d):
            session_docs.setdefault(stem, []).append(d.stem)

    def _fmt_session(p: Path) -> str:
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            mtime = "?"
        lines = storage.line_count(p)
        rel = p.relative_to(storage.ROOT)
        preview = storage.first_chunk_preview(p)
        docs = session_docs.get(p.stem)
        # Rich parses `[...]` as markup, so use parens for the doc tag.
        tag = f"  (doc: {', '.join(docs)})" if docs else ""
        return f"{mtime}  {lines:>5}L  {str(rel):<48}  {preview}{tag}"

    def _fmt_doc(p: Path) -> str:
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            mtime = "?"
        lines = storage.line_count(p)
        rel = p.relative_to(storage.ROOT)
        sources = storage.read_doc_sessions(p)
        meta = f"{len(sources)} session(s)" if sources else "doc"
        return f"{mtime}  {lines:>5}L  {str(rel):<48}  {meta}"

    for p in active:
        ui.plain(_fmt_session(p))
    for p in active_docs:
        ui.plain(_fmt_doc(p))
    for p in archived:
        ui.dim(_fmt_session(p))
    for p in archived_docs:
        ui.dim(_fmt_doc(p))
    return 0


def _doc_parser() -> argparse.ArgumentParser:
    d = argparse.ArgumentParser(prog="fl doc", add_help=True)
    g = d.add_mutually_exclusive_group()
    g.add_argument("--last", type=int, metavar="N", help="use newest N sessions, skip picker")
    g.add_argument("--since", metavar="DUR", help="sessions newer than DUR (e.g. 2h, 30m, 1d)")
    g.add_argument("--all-today", action="store_true", help="all sessions modified today")
    g.add_argument("-n", "--name", dest="name", metavar="TERM",
                   help="sessions whose name matches TERM (same fuzzy rules as `fl note -n`)")
    return d


def _print_help() -> None:
    sys.stderr.write(
        "fl — friction log\n"
        "\n"
        "usage:\n"
        "  fl [-n NAME] [text...]      append a note (stdin / args / $EDITOR)\n"
        "  fl note [-n NAME] [text...] same as bare fl\n"
        "  fl ls                       list all sessions, newest first\n"
        "  fl doc [--last N|--since DUR|--all-today]\n"
        "                              merge sessions and summarize via Claude\n"
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
            return doc.cmd_doc(last=ns.last, since=ns.since, all_today=ns.all_today, name=ns.name)
        except KeyboardInterrupt:
            ui.info("· interrupted")
            return 130

    _print_help()
    return 2
