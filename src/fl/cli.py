"""Argparse dispatcher for `python -m fl`."""

from __future__ import annotations

import argparse
import sys

from . import archive, doc, note, session, ui


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fl", description="friction log tool")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("status", help="show recording state and disk usage")
    sub.add_parser("archive", help="interactively move sessions to ~/.friction-log/archive")

    n = sub.add_parser("note", help="append a note to the active session")
    n.add_argument("words", nargs=argparse.REMAINDER, help="note text (omit to open $EDITOR)")

    d = sub.add_parser("doc", help="merge logs and summarize via Claude Code")
    g = d.add_mutually_exclusive_group()
    g.add_argument("--last", type=int, metavar="N", help="use newest N logs, skip picker")
    g.add_argument("--since", metavar="DUR", help="logs newer than DUR (e.g. 2h, 30m, 1d)")
    g.add_argument("--all-today", action="store_true", help="all logs from today")

    # Internal helpers invoked by bin/fl.
    sub.add_parser("_new-id", help=argparse.SUPPRESS)
    sub.add_parser("_already-recording", help=argparse.SUPPRESS)
    ps = sub.add_parser("_print-started", help=argparse.SUPPRESS)
    ps.add_argument("fl_id")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd is None:
        # `python -m fl` with no args is not the user-facing entrypoint; bin/fl is.
        parser.print_help(sys.stderr)
        return 2

    if args.cmd == "_new-id":
        return session.cmd_new_id()
    if args.cmd == "_already-recording":
        return session.cmd_already_recording()
    if args.cmd == "_print-started":
        return session.cmd_print_started(args.fl_id)
    if args.cmd == "status":
        return session.cmd_status()
    if args.cmd == "archive":
        try:
            return archive.cmd_archive()
        except KeyboardInterrupt:
            ui.info("· interrupted")
            return 130
    if args.cmd == "note":
        words = args.words or []
        # argparse REMAINDER may include a leading "--"; drop it.
        if words and words[0] == "--":
            words = words[1:]
        return note.cmd_note(words)
    if args.cmd == "doc":
        try:
            return doc.cmd_doc(
                last=args.last,
                since=args.since,
                all_today=args.all_today,
            )
        except KeyboardInterrupt:
            ui.info("· interrupted")
            return 130

    parser.print_help(sys.stderr)
    return 2
