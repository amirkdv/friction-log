"""Thin rich-based output helpers. Single style: dim for chrome, red for errors."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import questionary
from rich.console import Console

from . import storage

_stderr = Console(stderr=True, highlight=False)
_stdout = Console(highlight=False)


def info(msg: str) -> None:
    _stderr.print(msg, style="dim")


def success(msg: str) -> None:
    # Successful mutations: leading symbol already in caller, render dim.
    _stderr.print(msg, style="dim")


def error(msg: str) -> None:
    _stderr.print(msg, style="red")


def plain(msg: str) -> None:
    _stdout.print(msg)


def confirm(prompt: str, default: bool = False) -> bool:
    suffix = " [y/N]: " if not default else " [Y/n]: "
    try:
        ans = input(prompt + suffix).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print(file=sys.stderr)
        return False
    if not ans:
        return default
    return ans in ("y", "yes")


def status(msg: str):
    """Returns a context manager spinner for slow ops."""
    return _stderr.status(msg)


def pick_logs(logs: list[Path], prompt: str) -> list[Path]:
    """Multi-select picker over log files. Returns selected paths (possibly empty)."""
    choices = []
    for p in logs:
        fl_id = storage.id_from_path(p)
        started = storage.parse_id(p.name) or datetime.fromtimestamp(p.stat().st_mtime)
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
            dur = storage.fmt_duration(mtime - started)
        except OSError:
            dur = "?"
        lines = storage.line_count(p)
        note = storage.first_note(p)
        title = f"{fl_id[3:]:<22}  {dur:>6}  {lines:>5}L  {note}"
        choices.append(questionary.Choice(title=title, value=str(p)))

    answer = questionary.checkbox(prompt, choices=choices).ask()
    if not answer:
        return []
    return [Path(s) for s in answer]
