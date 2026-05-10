"""`fl doc` — pick session files, merge, send to Claude Code, write a summary."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from . import storage, ui

PICKER_LIMIT = 20
TOKEN_WARN_CHARS = 150_000 * 4  # ~150K tokens by chars/4 estimate

_BASE_PROMPT = """\
Extract a friction log from these terminal session pastes.

# Input format

Each session in the input is prefixed with `## <session-id>` (this is just
a delimiter inside the input — do NOT mirror these levels in your output).
Within a session, every chunk of pasted content is preceded by:

    --- YYYY-MM-DD HH:MM:SS ---

That timestamp is the wall-clock time when the user pasted the chunk into
`fl note` (NOT when the commands ran). Use it as a coarse anchor for
ordering and elapsed-time estimates between pastes.

Pasted bodies are raw terminal output. Most users keep a timestamped prompt
in their PS1 — those embedded prompt timestamps are the precise per-command
clock. Use them when present to pinpoint when individual commands ran inside
a chunk.{ps1_hint}

# Output format (strict)

- Start with a single `# ` (H1) title that names the friction theme.
- Use `## ` for each distinct issue/theme. Do not number them.
- Use bullet lists under each `## ` for symptom/tried/worked/time.
- No level-3 headings unless truly needed for sub-issues.
- Output is rendered as a standalone GitHub-flavored markdown file; assume
  no surrounding context. Do not wrap the response in code fences.
- Do not preface or postscript the doc (no "Here is…", no closing remarks).

# Content

For each thing that fought the user: symptom, what they tried, what worked,
rough time spent. Group by theme, not by session. Skip routine successful
commands. Be terse. Always include exact commands and a redacted subset of
outputs that highlight what happened.
"""


def cmd_doc(
    *,
    last: int | None = None,
    since: str | None = None,
    all_today: bool = False,
    name: str | None = None,
) -> int:
    storage.ensure_root()
    sessions = storage.list_sessions()
    if not sessions:
        ui.error("✗ no sessions found in ~/.friction-log/")
        return 1

    if shutil.which("claude") is None:
        ui.error("✗ `claude` CLI not found on PATH. install Claude Code first.")
        return 1

    selected = _select_sessions(sessions, last=last, since=since, all_today=all_today, name=name)
    if name and not selected:
        ui.error(f"✗ no sessions match '-n {name}'")
        return 1
    if name and selected:
        ui.info(f"→ matched {len(selected)} session(s) for '-n {name}':")
        for p in selected:
            ui.info(f"    {p.stem}")
    if not selected:
        ui.info("· nothing selected, aborting")
        return 0

    total_lines = sum(storage.line_count(p) for p in selected)
    ui.info(
        f"→ will merge {len(selected)} session(s) ({total_lines} lines total) "
        f"and send to Claude for summarization."
    )

    # Doc name is derived from the most-recent selected session's suffix,
    # auto-incremented past any prior doc for the same session.
    doc_suffix = storage.session_suffix(selected[0].stem)
    out = storage.next_doc_path(doc_suffix)
    ui.info(f"→ will write {out}")

    merged = _merge(selected)
    if len(merged) > TOKEN_WARN_CHARS:
        ui.error(
            f"! merged content is ~{len(merged)//4} tokens, may exceed Claude context."
        )
        if not ui.confirm("send anyway?"):
            return 0

    prompt = _build_prompt()
    summary = _call_claude(merged, prompt)
    if summary is None:
        return 1

    frontmatter = storage.format_doc_frontmatter([p.stem for p in selected])
    out.write_text(frontmatter + summary, encoding="utf-8")
    ui.success(f"✓ wrote {out} ({out.stat().st_size} bytes)")
    return 0


def _select_sessions(
    sessions: list[Path],
    *,
    last: int | None,
    since: str | None,
    all_today: bool,
    name: str | None,
) -> list[Path]:
    if name is not None:
        return storage.match_sessions(name, sessions)
    if last is not None:
        return sessions[:last]
    if since is not None:
        cutoff = (datetime.now() - _parse_duration(since)).timestamp()
        return [p for p in sessions if p.stat().st_mtime >= cutoff]
    if all_today:
        today = datetime.now().date()
        return [
            p for p in sessions
            if datetime.fromtimestamp(p.stat().st_mtime).date() == today
        ]
    return ui.pick_sessions(
        sessions[:PICKER_LIMIT],
        "select sessions to merge (space to toggle, enter to confirm):",
    )


def _merge(paths: list[Path]) -> str:
    parts = []
    for p in paths:
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            ui.error(f"! skipping {p.stem}: {e}")
            continue
        parts.append(f"## {p.stem}\n\n{content}\n")
    return "\n".join(parts)


def _build_prompt() -> str:
    ps1 = _capture_ps1()
    if ps1:
        # Embed verbatim so the LLM can match the user's actual prompt shape.
        ps1_hint = (
            "\n\nFor reference, the running user's PS1 looks like this "
            "(unrendered):\n\n    " + ps1.replace("\n", " ").strip()
        )
    else:
        ps1_hint = ""
    return _BASE_PROMPT.format(ps1_hint=ps1_hint)


def _capture_ps1() -> str:
    """Best-effort: ask the user's interactive shell to print its prompt.

    Failure is silent — the prompt just omits the example. We never block on
    this; cap the subprocess at 2s.
    """
    shell = os.environ.get("SHELL", "")
    try:
        if shell.endswith("zsh"):
            cmd = [shell, "-i", "-c", "print -P -- $PS1"]
        else:
            cmd = [shell or "/bin/bash", "-i", "-c", 'printf "%s" "$PS1"']
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=2, check=False
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return ""


def _call_claude(merged: str, prompt: str) -> str | None:
    cmd = ["claude", "-p", prompt]
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


_DUR_RE = re.compile(r"^\s*(\d+)\s*([smhd])\s*$")


def _parse_duration(s: str) -> timedelta:
    m = _DUR_RE.match(s)
    if not m:
        raise SystemExit(f"bad --since value: {s!r} (try 30m, 2h, 1d)")
    n, unit = int(m.group(1)), m.group(2)
    return {"s": timedelta(seconds=n), "m": timedelta(minutes=n),
            "h": timedelta(hours=n), "d": timedelta(days=n)}[unit]
