"""Thin rich-based output helpers. Single style: dim for chrome, red for errors."""

from __future__ import annotations

import sys

from rich.console import Console

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
