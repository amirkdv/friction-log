# `fl` — friction log

Paste terminal output (and short notes) into named sessions, then turn a
session into a Claude-summarized doc.

The flow is built around manual paste: when something is fighting you in your
terminal, select the relevant chunk, run `pbpaste | fl` (or pipe directly).
Later, `fl doc` picks one session and asks Claude to extract a friction
summary. Each session has at most one corresponding doc; the doc filename
mirrors the session stem (`fl-doc-<TS>-<suffix>.md`).

## Running tests

From the repo root:

```sh
uv run pytest
```

That's it — no env vars, no services, no network. The suite is hermetic:
each test gets a throwaway `$HOME`, a `PATH` that pins the in-repo `bin/fl`
wrapper and the fake `claude` from `tests/fakes/`, and runs `fl` as a real
subprocess.

Useful variants:

```sh
uv run pytest -k note            # filter by name
uv run pytest tests/test_doc.py  # one file
uv run pytest -x -vv             # stop on first failure, verbose
```

If `uv` isn't installed: `pip install -e '.[dev]'` then `pytest`.

## Repo layout

```
bin/fl              # bash wrapper — entry point, dispatches to python via uv
src/fl/             # python package
  cli.py            # argparse + command routing
  note.py           # `fl` / `fl -n` — append to a session
  doc.py            # `fl doc` — pick one session, call `claude` for summary
  archive.py        # `fl archive`
  storage.py        # ~/.friction-log layout, session filename conventions
  ui.py             # questionary pickers, rich output
tests/
  conftest.py       # fl_env / run_fl / seed_session fixtures (hermetic)
  fakes/            # fake `claude` binary on PATH during tests
  test_*.py         # one file per command group
spec/               # design notes
pyproject.toml
```

## Test conventions

- Tests invoke `fl` as a subprocess via the `run_fl` fixture — no in-process
  imports of `fl.cli`. This keeps argparse, the bash dispatcher, and env
  handling under test.
- External tools (`claude`) are faked by shimming `tests/fakes/` onto `PATH`.

## Agent rules (Claude Code, Cursor, etc.)

These rules are mandatory for any AI agent making changes in this repo.
`CLAUDE.md` and `.cursorrules` are symlinks to this file — edit `AGENTS.md`
and both pick it up.

1. **New feature → new test.** Every new feature or user-visible behavior
   must land with a test in `tests/test_<feature>.py` using `run_fl` +
   `seed_session`. No feature PR without a test.

2. **Bug fix → red/green.** Reproduce the bug with a failing test *first*.
   Run it, show it fails for the right reason, then make the minimal fix and
   confirm the suite is green. Do not skip the red step even when the fix
   looks obvious. If the bug genuinely cannot be expressed as a test (e.g.,
   a packaging-only issue), say so explicitly.

3. **Editing existing tests requires explicit permission.** Do not modify,
   rename, delete, or weaken any test in `tests/` without first asking the
   user and getting an explicit yes. Adding *new* tests is always fine;
   touching existing assertions, fixtures, or test names is not. If a fix
   appears to require changing a test, stop and ask — usually it means the
   fix is wrong.

4. **Keep these instructions in sync.** When a change introduces a new
   convention, fixture, directory, or workflow that future agents will need
   to know, update `AGENTS.md` in the same change. Stale agent instructions
   are a bug; treat them like one.

## Install (end-user)

```sh
git clone <this repo> ~/code/friction-log
ln -s ~/code/friction-log/bin/fl ~/.local/bin/fl   # any dir on PATH
```

Dependencies:

- [`uv`](https://github.com/astral-sh/uv) (recommended) — `bin/fl` uses it to
  run the Python side in an isolated env. Falls back to `python3` +
  `PYTHONPATH` if `uv` is missing.
- [Claude Code](https://claude.com/claude-code) CLI on `$PATH` for `fl doc`.

### Recommended: timestamped PS1

`fl` itself doesn't touch your prompt. But if your PS1 carries a wall-clock
timestamp, `fl doc` can use those embedded timestamps to anchor commands
inside a paste. Suggested rc snippet:

```zsh
# ~/.zshrc
PROMPT='%F{8}%D{%Y-%m-%d %H:%M}%f '$PROMPT
```

```bash
# ~/.bashrc
PS1='\D{%Y-%m-%d %H:%M} '"$PS1"
```

## Usage

```sh
pbpaste | fl -n auth-bug          # append the clipboard to session "auth-bug"
fl -n auth-bug "rate-limited again"  # one-line note via args
echo "$output" | fl -n auth-bug   # pipe arbitrary command output
fl -n auth-bug                    # interactive: opens $EDITOR
fl                                # picker: pick or create a session

fl ls                             # list sessions; one row per session, with
                                  # any associated doc in its own column
fl doc                            # pick a session, summarize → fl-doc-<...>.md
fl doc -n auth                    # session matching "auth" (picker if 2+)
fl view -n auth                   # open a session or doc in $EDITOR

fl archive                        # interactively move sessions to archive/
```

`-n <term>` matches sessions by **case-insensitive, dash-token-aware
substring** of the post-timestamp suffix. So `-n auth-bug` happily targets
an existing `2026-05-10-T-14-32-authn-bug-fix`. Zero matches → a new session
is created (or confirmed in interactive mode). Multiple matches → a picker
filtered to those (or an error if you're piping).

## Storage

```
~/.friction-log/
  fl-session-2026-05-10-T-14-32-auth-bug.md     # one file per session
  fl-session-2026-05-10-T-15-00-deploy-flake.md # append-only
  fl-doc-2026-05-10-T-14-32-auth-bug.md         # `fl doc` output for that
                                                # session (mirrors the stem)
  fl-doc-2026-05-10-T-14-32-auth-bug-1.md       # regenerated → -N suffix
  archive/                                      # archived sessions + docs
```

Each `fl note` invocation appends a chunk preceded by

```
--- 2026-05-10 14:32:07 ---
```

The timestamp is text only — `fl` itself never re-parses it. It exists for
the LLM in `fl doc`.
