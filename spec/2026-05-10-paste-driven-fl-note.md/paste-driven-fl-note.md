# Drop `script`-based recording; switch to paste-driven `fl note` with named sessions

## Context

`script(1)` on zsh 5.9 has a paste/option-edit bug that makes the current
recording flow unusable on macOS (see `README.md`). Capturing the full
keystroke stream was always more than this tool needs — the actual product is
"history + output, plus my notes, summarized by an LLM."

This plan rewires `fl` around manual paste input via `fl note`, organized into
named sessions. PS1 management leaves the tool entirely (user keeps a
timestamped prompt in their own rc; fl just documents that this works better).
**No fl logic outside the final LLM step depends on parsing timestamps** —
ordering inside a session is insertion order; ordering across sessions, when
needed, is fs mtime.

## End-state design

### Storage

- `~/.friction-log/<TS>-<name>.md` — one append-only markdown file per session.
  - `<TS>` = `YYYY-MM-DD-T-HH-MM` (creation time, computed once when the session
    file is first created).
  - `<name>` = user-provided suffix (free-form, dashes encouraged).
  - Canonical session id = the full filename stem.
- `~/.friction-log/archive/` — moved session files live here.
- Old `.log` / `.timing` / `fl-doc-*.md` files: ignored by the new code (hard
  cut). Existing files remain on disk; user can `rm` or `mv` manually.

### Chunk format inside a session file

Every `fl note` invocation appends:

```
\n--- 2026-05-10 14:32:07 ---\n
<body>\n
```

The timestamp is **text only** — never re-parsed by fl. Used solely as a hint
for the LLM in `fl doc`.

### `fl note` — the only input primitive

Signatures:
- `fl note [-n <term>] <inline text...>` — short note from args
- `cmd | fl note [-n <term>]` — stdin (heredoc / pipe / `pbpaste |`) when
  stdin is not a TTY
- `fl note [-n <term>]` with TTY stdin and no args → opens `$EDITOR`

Session resolution (single shared algorithm, used by both the `-n` path and
the no-arg path):

1. Build the candidate list = existing session stems, mtime-desc.
2. If `-n <term>` provided: filter candidates by **case-insensitive,
   dash-token-aware substring** against the post-timestamp suffix.
   - "Dash-token-aware" = split `<term>` on `-`, require each token to be a
     substring of the suffix (lowercased). E.g. `auth-bug` → tokens
     `["auth","bug"]`, both must appear → matches `authn-bug-fix`.
   - Implementation: ~3 lines of pure Python. **No new dependency.** If we
     later want fuzziness, we can swap in `rapidfuzz`, but that's out of scope.
3. Decide:
   - **Exactly 1 match and `-n` was given** → use it silently.
   - **0 matches and `-n` was given** → show picker with one option:
     `+ create new "<TS>-<term>"` (confirm-and-go).
   - **≥2 matches, or `-n` omitted** → show picker over candidates +
     `+ create new…` (which prompts for the suffix when chosen).

After resolution, the chunk delimiter + body are appended atomically (single
`open("a")` + write).

### `fl doc`

- Picker (questionary, multi-select) over session files in
  `~/.friction-log/` (excluding `archive/`), mtime-desc.
- Same flag surface as today: `--last N`, `--since 2h`, `--all-today` (these
  now key off file mtime, not parsed timestamps inside content).
- Merge: concatenate the picked `.md` files verbatim, each prefixed with
  `## <session-id>`. **No ANSI stripping** — content is user-pasted plain
  text already.
- LLM prompt (`EXTRACTION_PROMPT` in `doc.py`) updated to:
  - Explain the `--- YYYY-MM-DD HH:MM:SS ---` chunk delimiter = paste time.
  - Explain that pasted bodies often contain a user-style PS1 prefix carrying
    a wall-clock timestamp; show **one concrete example** of the running
    user's PS1 by capturing it at `fl doc` time.
  - Capture trick: spawn `$SHELL -i -c 'print -P "$PS1"'` for zsh /
    `bash -i -c 'echo "$PS1"'` for bash, fall back to a generic example if
    capture fails. Embed the captured string in the prompt as
    `Example PS1 in this user's terminal: <captured>`.
- Output filename unchanged: `fl-doc-<name>.md`.

### `fl archive`

- Picker over session files; selected files move to
  `~/.friction-log/archive/`. Drop the "refuse if live session" guard
  (no live concept anymore).

### `fl status`

- **Removed.** No recording lifecycle to report on.

### `bin/fl`

- Drops the entire `script(1)` branch (BSD/GNU detection, `FL_ID` /
  `FL_SESSION` exports, subshell spawn).
- Becomes a thin dispatcher: `fl <subcommand> ...` → `uv run` (or
  `python3 -m fl`) the Python CLI.
- **Bare `fl` (no args) routes to `fl note`** — same behavior as `fl note`
  with no flags: stdin if piped, $EDITOR if TTY, then session picker. This is
  the primary one-keystroke paste entry point. `fl --help` (or `fl help`) is
  how you reach the help text.

### README

- Replace the warning + install/usage with the new flow.
- Document recommended PS1 line for zsh + bash (timestamped) as **optional but
  helpful for `fl doc`**.
- Drop `script(1)` from the dependency list.

## Files to modify

- `bin/fl` — strip `script` lifecycle; keep only python dispatch.
- `src/fl/cli.py` — remove old recording route and `fl status`; route bare
  `fl` (and `fl <text...>` where the first token isn't a known subcommand) to
  the `note` handler; remove `--last`/etc. defaults that assumed script logs.
- `src/fl/storage.py` — new helpers: `session_files()` (excludes `archive/`),
  `resolve_session(term, *, allow_create) -> Path`, `new_session_path(suffix)`;
  drop `.log`/`.timing` pair logic and `id_from_path` script-format parsing.
- `src/fl/note.py` — full rewrite around the resolution algorithm above; add
  stdin handling (`sys.stdin.isatty()` gate); keep $EDITOR fallback.
- `src/fl/doc.py` — drop ANSI stripping; switch input to `.md` session files;
  rewrite `EXTRACTION_PROMPT`; add PS1-capture helper; merge logic uses
  `## <id>` headers only.
- `src/fl/archive.py` — operate on session `.md` files; drop live-session guard.
- `src/fl/session.py` — delete (no longer meaningful) or shrink to just
  filename helpers if any are still used.
- `src/fl/ui.py` — keep; may add a small "create new <term>" picker helper.
- `README.md` — rewrite Install/Usage/Caveats per above.
- `tests/` — does not exist yet. **Add hermetic e2e tests** (per global rule):
  `tests/test_note.py`, `tests/test_doc.py`, `tests/test_archive.py` using
  `pytest` + `tmp_path` to override `~/.friction-log`, and a fake `claude`
  binary on `PATH` for the `fl doc` path. Seed with happy-path + one
  ambiguous-match + one zero-match case for `fl note`.

## Critical reuse

- `ui.py` questionary picker — reuse for both note resolution and doc/archive.
- `doc.py` time-window filtering (`--since`, `--all-today`) — keep, just
  re-source from file mtime.
- `bin/fl`'s `uv`-vs-`python3` fallback block — keep verbatim.

## Migration / rollout

The repo is pre-public, so this is a clean replacement, not a dual-write
phase. Implementation order:

1. Land storage + `fl note` rewrite + tests; manually exercise paste flows.
2. Land `fl doc` rewrite + PS1 capture; verify summaries on a real session.
3. Land `fl archive` simplification + `fl status` removal.
4. Strip `bin/fl` script branch and rewrite README in the same commit.
5. Once the new flow has been used for real for ~a few sessions and feels
   right, delete `session.py` and any leftover script-era code paths.

## Verification

- Unit/e2e (hermetic, per `~/.claude/CLAUDE.md` rule 1):
  - `fl note -n new-term "hello"` with empty store → creates
    `<TS>-new-term.md` after picker confirm.
  - `echo "body" | fl note -n existing` with one match → silent append.
  - `fl note -n auth` with two matching sessions → picker shows both.
  - `fl note` with no args, TTY stdin, fake `$EDITOR=/bin/true` → empty-note
    short-circuit.
  - `fl doc --last 1` with a fake `claude` on PATH → produces
    `fl-doc-*.md` and the prompt sent to `claude` contains the chunk-delimiter
    explanation and a `Example PS1` line.
  - `fl archive` moves the picked file under `archive/` and excludes it from
    subsequent `fl doc` pickers.
- Manual: paste a chunk of real terminal output (containing a timestamped
  PS1) into `fl note -n smoke <<EOF ... EOF`, then run `fl doc --last 1`,
  inspect that the LLM correctly anchors events using PS1 timestamps.

## Open follow-ups (out of scope for this plan)

- If dash-token substring proves too loose/strict in real use, revisit with
  `rapidfuzz`.
- A `fl rename <old> <new>` could be useful once sessions accumulate, but not
  needed for v1.
