"""`fl doc` — pick a session, send it to Claude Code, write a summary.

One session in, one doc out. The doc filename mirrors the session stem
(`fl-doc-<TS>-<suffix>.md`), with a `-N` bump on collision.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import storage, ui

PICKER_LIMIT = 20
TOKEN_WARN_CHARS = 150_000 * 4  # ~150K tokens by chars/4 estimate

_BASE_PROMPT = """\
Extract a friction log from this terminal session paste.

# Input format

The input is the raw body of one `fl` session. Every chunk of pasted content
is preceded by:

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
rough time spent. Group by theme. Skip routine successful commands. Be
terse. Always include exact commands and a redacted subset of outputs that
highlight what happened.
"""


def cmd_doc(*, name: str | None = None) -> int:
    storage.ensure_root()
    sessions = storage.list_sessions()
    if not sessions:
        ui.error("✗ no sessions found in ~/.friction-log/")
        return 1

    if shutil.which("claude") is None:
        ui.error("✗ `claude` CLI not found on PATH. install Claude Code first.")
        return 1

    selected = _select_session(sessions, name=name)
    if selected is None:
        return 1

    ui.info(f"→ session: {selected.stem} ({storage.line_count(selected)} lines)")

    out = storage.next_doc_path(selected.stem)
    ui.info(f"→ will write {out}")

    try:
        body = selected.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        ui.error(f"✗ cannot read {selected.name}: {e}")
        return 1

    if len(body) > TOKEN_WARN_CHARS:
        ui.error(
            f"! session is ~{len(body)//4} tokens, may exceed Claude context."
        )
        if not ui.confirm("send anyway?"):
            return 0

    prompt = _build_prompt()
    summary = _call_claude(body, prompt)
    if summary is None:
        return 1

    frontmatter = storage.format_doc_frontmatter(selected.stem)
    out.write_text(frontmatter + summary, encoding="utf-8")
    ui.success(f"✓ wrote {out} ({out.stat().st_size} bytes)")
    return 0


def _select_session(sessions: list[Path], *, name: str | None) -> Path | None:
    interactive = sys.stdin.isatty() and sys.stderr.isatty()
    if name is not None:
        matches = storage.match_sessions(name, sessions)
        if not matches:
            ui.error(f"✗ no sessions match '-n {name}'")
            return None
        if len(matches) == 1:
            ui.info(f"→ matched 1 session for '-n {name}': {matches[0].stem}")
            return matches[0]
        if not interactive:
            ui.error(
                f"✗ '-n {name}' matches {len(matches)} sessions; "
                f"use a more specific name. matches:"
            )
            for p in matches:
                ui.error(f"    {p.stem}")
            return None
        ui.info(f"→ {len(matches)} sessions match '-n {name}':")
        for p in matches:
            ui.info(f"    {p.stem}")
        return ui.pick_session(matches, prompt=f"pick one for '-n {name}':")
    if not interactive:
        ui.error("✗ stdin is not a tty and -n was not provided; pass -n <name>")
        return None
    return ui.pick_session(
        sessions[:PICKER_LIMIT],
        "select a session (enter to confirm):",
    )


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
    """Best-effort: ask the user's interactive shell to print its prompt."""
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


def _call_claude(body: str, prompt: str) -> str | None:
    cmd = ["claude", "-p", prompt]
    try:
        with ui.status("calling claude..."):
            proc = subprocess.run(
                cmd,
                input=body,
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
