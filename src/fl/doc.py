"""`fl doc` — pick logs, merge, send to Claude Code, write a summary doc."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import questionary

from . import storage, ui

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|[\x00-\x08\x0b\x0c\x0e-\x1f]")

PICKER_LIMIT = 10
TOKEN_WARN_CHARS = 150_000 * 4  # ~150K tokens by chars/4 estimate

EXTRACTION_PROMPT = """\
Extract a friction log from these terminal transcripts. Each transcript is
prefixed with `## fl-<id>`. Inline `### NOTE` lines are human annotations.

For each thing that fought me: symptom, what I tried, what worked, rough
time spent. Group by theme, not by transcript. Skip routine successful
commands. Be terse.
"""


def cmd_doc(
    *,
    last: int | None = None,
    since: str | None = None,
    all_today: bool = False,
) -> int:
    storage.ensure_root()
    logs = storage.list_logs()
    if not logs:
        ui.error("✗ no logs found in ~/.friction-log/")
        return 1

    if shutil.which("claude") is None:
        ui.error("✗ `claude` CLI not found on PATH. install Claude Code first.")
        return 1

    selected = _select_logs(logs, last=last, since=since, all_today=all_today)
    if not selected:
        ui.info("· nothing selected, aborting")
        return 0

    total_lines = sum(_line_count(p) for p in selected)
    ui.info(
        f"→ will merge {len(selected)} log(s) ({total_lines} lines total) "
        f"and send to Claude for summarization."
    )

    name = _prompt_name()
    if not name:
        return 0
    out = storage.doc_path(name)
    ui.info(f"→ will write {out}")

    if out.exists():
        if not ui.confirm(f"overwrite existing {out.name}?"):
            ui.info("· aborted")
            return 0
    else:
        if not ui.confirm("proceed?"):
            ui.info("· aborted")
            return 0

    merged = _merge(selected)
    if len(merged) > TOKEN_WARN_CHARS:
        ui.error(
            f"! merged content is ~{len(merged)//4} tokens, may exceed Claude context."
        )
        if not ui.confirm("send anyway?"):
            return 0

    summary = _call_claude(merged)
    if summary is None:
        return 1

    out.write_text(summary, encoding="utf-8")
    ui.success(f"✓ wrote {out} ({out.stat().st_size} bytes)")
    return 0


def _select_logs(
    logs: list[Path],
    *,
    last: int | None,
    since: str | None,
    all_today: bool,
) -> list[Path]:
    if last is not None:
        return logs[:last]
    if since is not None:
        cutoff = datetime.now() - _parse_duration(since)
        return [p for p in logs if (storage.parse_id(p.name) or datetime.min) >= cutoff]
    if all_today:
        today = datetime.now().date()
        return [p for p in logs if (storage.parse_id(p.name) or datetime.min).date() == today]
    return _interactive_pick(logs[:PICKER_LIMIT])


def _interactive_pick(logs: list[Path]) -> list[Path]:
    choices = []
    for p in logs:
        fl_id = storage.id_from_path(p)
        started = storage.parse_id(p.name) or datetime.fromtimestamp(p.stat().st_mtime)
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
            dur = _fmt_duration(mtime - started)
        except OSError:
            dur = "?"
        lines = _line_count(p)
        first_note = _first_note(p)
        title = f"{fl_id[3:]:<22}  {dur:>6}  {lines:>5}L  {first_note}"
        choices.append(questionary.Choice(title=title, value=str(p)))

    answer = questionary.checkbox(
        "select logs to merge (space to toggle, enter to confirm):",
        choices=choices,
    ).ask()
    if not answer:
        return []
    return [Path(s) for s in answer]


def _prompt_name() -> str | None:
    while True:
        try:
            name = input("name this doc: ").strip()
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            return None
        if not name:
            ui.error("✗ name required")
            continue
        if "/" in name or " " in name:
            suggested = name.replace(" ", "-").replace("/", "-")
            ui.error(f"✗ no spaces or slashes. try: {suggested}")
            continue
        return name


def _merge(paths: list[Path]) -> str:
    parts = []
    for p in paths:
        fl_id = storage.id_from_path(p)
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            ui.error(f"! skipping {fl_id}: {e}")
            continue
        cleaned = ANSI_RE.sub("", content)
        parts.append(f"## {fl_id}\n\n{cleaned}\n")
    return "\n".join(parts)


def _call_claude(merged: str) -> str | None:
    cmd = ["claude", "-p", EXTRACTION_PROMPT]
    try:
        with ui.status("calling claude..."):
            proc = subprocess.run(
                cmd,
                input=merged,
                capture_output=True,
                text=True,
                check=False,
            )
    except FileNotFoundError:
        ui.error("✗ `claude` CLI not found.")
        return None
    if proc.returncode != 0:
        ui.error(f"✗ claude exited {proc.returncode}")
        if proc.stderr:
            ui.error(proc.stderr.strip())
        return None
    return proc.stdout


def _line_count(p: Path) -> int:
    try:
        with p.open("rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def _first_note(p: Path) -> str:
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("### NOTE"):
                    s = line.rstrip("\n")
                    return s[:60] + ("…" if len(s) > 60 else "")
    except OSError:
        pass
    return ""


def _fmt_duration(td: timedelta) -> str:
    secs = max(0, int(td.total_seconds()))
    h, rem = divmod(secs, 3600)
    m, _ = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m"


_DUR_RE = re.compile(r"^\s*(\d+)\s*([smhd])\s*$")


def _parse_duration(s: str) -> timedelta:
    m = _DUR_RE.match(s)
    if not m:
        raise SystemExit(f"bad --since value: {s!r} (try 30m, 2h, 1d)")
    n, unit = int(m.group(1)), m.group(2)
    return {"s": timedelta(seconds=n), "m": timedelta(minutes=n),
            "h": timedelta(hours=n), "d": timedelta(days=n)}[unit]
