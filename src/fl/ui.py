"""Thin rich-based output helpers + questionary pickers."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import questionary
from rich.console import Console

from . import storage

_stderr = Console(stderr=True, highlight=False)
_stdout = Console(highlight=False)

_CREATE_SENTINEL = "__create__"


def info(msg: str) -> None:
    _stderr.print(msg, style="dim")


def success(msg: str) -> None:
    _stderr.print(msg, style="dim")


def error(msg: str) -> None:
    _stderr.print(msg, style="red")


def plain(msg: str) -> None:
    _stdout.print(msg, soft_wrap=True, overflow="ignore", crop=False)


def dim(msg: str) -> None:
    _stdout.print(msg, style="bright_black", soft_wrap=True, overflow="ignore", crop=False)


def confirm(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
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


def _session_choice_title(p: Path) -> str:
    suffix = storage.session_suffix(p.stem)
    try:
        mtime = datetime.fromtimestamp(p.stat().st_mtime)
        when = mtime.strftime("%m-%d %H:%M")
    except OSError:
        when = "?"
    lines = storage.line_count(p)
    preview = storage.first_chunk_preview(p)
    return f"{suffix:<28}  {when:<11}  {lines:>5}L  {preview}"


def pick_sessions(sessions: list[Path], prompt: str) -> list[Path]:
    """Multi-select picker over sessions. Returns selected paths (possibly empty)."""
    choices = [
        questionary.Choice(title=_session_choice_title(p), value=str(p))
        for p in sessions
    ]
    answer = questionary.checkbox(prompt, choices=choices).ask()
    if not answer:
        return []
    return [Path(s) for s in answer]


def pick_session(sessions: list[Path], prompt: str) -> Path | None:
    """Single-select picker. Returns the chosen session or None on cancel."""
    choices = [
        questionary.Choice(title=_session_choice_title(p), value=str(p))
        for p in sessions
    ]
    answer = questionary.select(prompt, choices=choices).ask()
    return Path(answer) if answer else None


def pick_or_create_session(sessions: list[Path]) -> Path | None:
    """Single-select picker including a '+ create new…' option. Returns the
    chosen path (existing or freshly-built) or None on cancel."""
    choices = [
        questionary.Choice(title=_session_choice_title(p), value=str(p))
        for p in sessions
    ]
    choices.append(questionary.Choice(title="+ create new…", value=_CREATE_SENTINEL))
    answer = questionary.select("pick a session:", choices=choices).ask()
    if answer is None:
        return None
    if answer == _CREATE_SENTINEL:
        try:
            suffix = input("new session name: ").strip()
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            return None
        if not suffix:
            error("✗ name required")
            return None
        return storage.new_session_path(suffix)
    return Path(answer)
