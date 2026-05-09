# `fl` — Friction Log Tool: Claude Code Plan

## ID format

Pattern: `fl-YYYY-MM-DD-HHMM-XXXXXX` where XXXXXX is 6 random hex chars.

Example: `fl-2026-05-09-1430-a3f78d`

24 chars. Sorts chronologically (alphabetical = chronological). Hex suffix prevents collisions when `fl` is invoked twice in the same minute.

## Storage

- `~/.friction-log/` — flat, no subdirs, not configurable
- `<id>.log` — `script(1)` transcript
- `<id>.timing` — `script -t` timing file
- `fl-doc-<name>.md` — generated summaries (named by user at generation time)

No central `notes.md`. Notes are inline in the relevant `<id>.log` via `### NOTE [HH:MM:SS]: ...` markers.

## Project layout

```
fl/
├── bin/fl                    # bash entrypoint, symlinkable to PATH
├── src/fl/
│   ├── __init__.py
│   ├── __main__.py           # `python -m fl` dispatcher
│   ├── cli.py                # argparse + subcommand routing
│   ├── session.py            # start/status logic, ID generation
│   ├── note.py               # `fl note` command
│   ├── doc.py                # `fl doc` interactive merge+LLM
│   ├── storage.py            # ~/.friction-log paths, file ops
│   └── ui.py                 # rich/questionary helpers, confirmations
├── pyproject.toml            # PEP 621 + uv-compatible
└── README.md
```

## Entrypoint: `bin/fl`

A small bash wrapper (not Python), because `fl` with no args must modify the parent shell — set `FL_SESSION` env var, update PS1, and `exec script(1)`. A Python child process can't do that to its parent.

Responsibilities:
- `fl` (no args): bash-side. If `$FL_SESSION` set, print status and exit. Else generate ID via `python -m fl _new-id`, set env vars, mutate PS1, `exec script -q -f -t <timing> <log>`.
- All other subcommands: delegate to `uv run --script ... python -m fl <subcommand> "$@"`.

~40 lines of bash. Everything else is Python.

## Dependencies (Python)

- `rich` — formatted output, the visible "what just happened" surface
- `questionary` — interactive multi-select for `fl doc`

Plus a hard dependency on the `claude` CLI (Claude Code) being on `$PATH`. `fl doc` shells out to `claude -p '<prompt>' < merged.txt` rather than calling the API directly. Rationale: zero API key management in this tool, free use of whatever model the user's Claude Code is configured for, and the user already has it installed.

Distribution via `uv run` with PEP 723 inline metadata or a `pyproject.toml`. Isolated footprint, no global install.

## Subcommand specs

### `fl` (no args)

**Behavior:**
- If `$FL_SESSION` set → print `▶ already recording <id> (started HH:MM, <N>m elapsed)` in dim color, exit 0.
- Else → generate ID, create `<id>.log` and `<id>.timing`, set `FL_SESSION` and `FL_ID` env vars, prefix PS1 with `[REC <short-id>]`, exec `script -q -f -t <timing> <log>`.

**Visible output (on start):**
```
▶ recording fl-2026-05-09-1430-a3f78d
  → ~/.friction-log/fl-2026-05-09-1430-a3f78d.log
```

**Confirmation:** none needed — this is creating a new file, not deleting anything.

### `fl note [text...]`

**Behavior:**
- If `$FL_SESSION` unset → red error `✗ not recording. run \`fl\` first.`, exit 1.
- If args present → write `### NOTE [HH:MM:SS]: <joined args>` to `$FL_SESSION`.
- If no args → open `$EDITOR` (default `vi`) with a temp file, on save write contents prefixed with `### NOTE [HH:MM:SS]:` to `$FL_SESSION`. Empty save → no-op with dim message.

**Visible output:**
```
✎ noted to fl-2026-05-09-1430-a3f78d
```

**Confirmation:** none — appends only.

### `fl doc`

**Behavior:**
1. Scan `~/.friction-log/` for `fl-*.log`, sort newest first (by filename, since filename = chronological).
2. Show newest 10 in a `questionary.checkbox` picker. Each row:
   - ID (the date-time-hex part)
   - Duration (mtime − filename-time, formatted as `12m`, `1h23m`)
   - Line count
   - First `### NOTE` content if any (truncated to ~60 chars)
3. User selects subset (space to toggle, enter to confirm). Zero selected → abort with dim message.
4. Show preview: `→ will merge N logs (M lines total) and send to Claude for summarization.`
5. Prompt for doc name: `name this doc:` → validates non-empty, no slashes, no spaces (suggest replacement with `-`).
6. Show output path: `→ will write ~/.friction-log/fl-doc-<name>.md`.
7. **Confirmation prompt** (this is the deleterious-ish mutation — overwrites if exists): `proceed? [y/N]`. If `fl-doc-<name>.md` exists, the prompt becomes `overwrite existing fl-doc-<name>.md? [y/N]`.
8. Strip ANSI from selected logs, concatenate with `## <id>` headers between, send to Claude with the extraction prompt, write response to `fl-doc-<name>.md`.
9. Final output: `✓ wrote ~/.friction-log/fl-doc-<name>.md (<N> bytes)`.

**Flags (escape hatches for the picker):**
- `--last N` — skip picker, use newest N logs
- `--since DURATION` — e.g. `--since 2h`, skip picker, use logs newer than cutoff
- `--all-today` — skip picker, use logs from today
- These still require the doc-name prompt and confirmation.

**Claude prompt template (in `doc.py`):**
```
Extract a friction log from these terminal transcripts. Each transcript is
prefixed with `## fl-<id>`. Inline `### NOTE` lines are human annotations.

For each thing that fought me: symptom, what I tried, what worked, rough
time spent. Group by theme, not by transcript. Skip routine successful
commands. Be terse.
```

Model: `claude-opus-4-7` (or whichever is current — make it a constant at top of `doc.py` for easy bump).

### `fl status` (bonus, cheap to add)

**Behavior:**
- Prints recording state for current shell (`$FL_SESSION` set?), recent log count, total disk usage of `~/.friction-log/`.
- Read-only.

## UX principles enforced in `ui.py`

These come straight from the requirements:

1. **State always visible.** `fl` start prints the ID and path. `fl note` prints which log it appended to. `fl doc` prints what it will merge, what it will write, and confirms before writing. PS1 prefix shows recording state continuously.

2. **Minimize intrusiveness.** All non-error output uses `rich`'s `dim` style. Errors are red. Successful mutations are a single line with a leading symbol (`▶ ✎ ✓`). No banners, no boxes, no progress bars unless the LLM call is slow enough to warrant a spinner (it is — use `rich.status` for the Claude call).

3. **Confirmations before deleterious mutations.** Only `fl doc` mutates non-trivially (writes a doc file, possibly overwriting). Always confirms. `fl` start and `fl note` are append-only / new-file, no confirmation.

4. **Tell the user what you're about to do.** `fl doc` shows the full plan (selected logs, output path) before the confirmation prompt. No surprise writes.

## Implementation order (suggested for Claude Code)

1. **`storage.py`** — pure functions: `new_id()`, `log_path(id)`, `list_logs()`, `parse_id(filename)`. Easy to unit test, no I/O surprises later.
2. **`ui.py`** — rich-based helpers: `info()`, `error()`, `success()`, `confirm(prompt)`. One file, used everywhere.
3. **`session.py`** — `_new-id` subcommand for the bash wrapper to invoke. Just prints a fresh ID.
4. **`bin/fl`** — bash wrapper. Test by hand: `fl` starts a session, exits drop you back, log file exists with content.
5. **`note.py`** — append logic. Test: `fl note hello` writes correctly; `fl note` (no args) opens editor.
6. **`doc.py`** — the big one. Build in three sub-steps:
   1. Picker logic without LLM (write merged content to a tmp file, verify).
   2. Add Claude API call with the extraction prompt.
   3. Add `--last`, `--since`, `--all-today` flags.
7. **`cli.py` + `__main__.py`** — argparse dispatcher, ties it together.
8. **`README.md`** — install instructions: clone, symlink `bin/fl` to PATH, set `ANTHROPIC_API_KEY`, done.

## Things explicitly out of scope

- No `~/.bashrc` / `~/.zshrc` integration. User runs `fl` manually per shell.
- No tmux integration beyond what works incidentally (it all does).
- No automatic merging on a schedule.
- No editing of existing logs (read-only after `script` exits).
- No deletion of logs (user can `rm ~/.friction-log/fl-*` directly if they want).
- No syncing, no remote backup, no encryption. Local files only.
- No tests beyond manual smoke tests for v1. Add pytest later if it earns its place.

## Risks and gotchas

- **`script` on macOS is BSD, not GNU.** Flag set differs. The wrapper uses `script -q -t <timing> <log>` which works on BSD `script` (macOS default). Verify before shipping.
- **`script -f` (flush) is GNU-only.** On macOS, `script` flushes by default-ish. Drop `-f` from the bash wrapper or detect with `uname`.
- **PS1 mutation only sticks for the duration of `script`'s subshell.** Once `script` exits, the parent shell's PS1 is unchanged. This is fine — the recording state is exactly the lifetime of the `script` subshell.
- **`anthropic` SDK requires `ANTHROPIC_API_KEY` in env.** Document in README. `fl doc` should error early with a clear message if missing, not crash mid-call.
- **Long logs may exceed Claude's context.** `fl doc` should warn if total selected content exceeds ~150K tokens (rough char-based estimate is fine: chars / 4). Suggest selecting fewer logs.
- **ANSI stripping.** `script` captures escape codes. Strip with a regex (`\x1b\[[0-9;]*[a-zA-Z]`) before sending to Claude, or let Claude handle it (it does fine, but uses tokens). Strip — cheaper.
- **Time-box the build to 90 minutes.** This is a tool to help you build the actual thing. Do not let it become the thing.
