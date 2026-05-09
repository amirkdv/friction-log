# `fl` — friction log

Record terminal sessions, annotate them inline, and turn a batch into a summary via Claude Code.

## Install

```sh
git clone <this repo> ~/code/friction-log
ln -s ~/code/friction-log/bin/fl ~/.local/bin/fl   # or any dir on PATH
```

Inside a recording, `fl` exports `FL_ID` and spawns your `$SHELL` interactively, so your normal rc files (`~/.zshrc`, `~/.bashrc`, etc.) run as usual. To get a yellow `[REC <id>]` prompt prefix while recording, add one line to your shell rc:

```zsh
# ~/.zshrc
[[ -n $FL_ID ]] && PROMPT="%F{yellow}[REC ${FL_ID#fl-}]%f $PROMPT"
```

```bash
# ~/.bashrc
[[ -n $FL_ID ]] && PS1="\[\033[33m\][REC ${FL_ID#fl-}]\[\033[0m\] $PS1"
```

Dependencies:

- `script(1)` (preinstalled on macOS and most Linux)
- [`uv`](https://github.com/astral-sh/uv) (recommended) — `bin/fl` will use it to run the Python side in an isolated env. Falls back to `python3` + `PYTHONPATH` if `uv` is missing.
- [Claude Code](https://claude.com/claude-code) CLI on `$PATH` for `fl doc`. No `ANTHROPIC_API_KEY` needed in this tool — `claude` handles auth.

## Usage

```sh
fl                    # start recording the current shell
fl note rate-limited again on the prod webhook
fl note               # opens $EDITOR for a longer note
exit                  # ends the recording (script exits)

fl doc                # interactively pick recent logs, summarize, write fl-doc-<name>.md
fl doc --last 3       # skip picker, use newest 3
fl doc --since 2h     # logs from the last 2 hours
fl doc --all-today    # logs from today

fl status             # show recording state and disk usage
fl archive            # interactively move sessions to ~/.friction-log/archive/
```

Logs live in `~/.friction-log/`, flat. Filenames sort chronologically.

## Notes / caveats

- On macOS, `script(1)` is BSD: timing data is not captured (the `-t` flag means something different there). You still get the full transcript.
- `fl` with no args replaces the current shell with a `script`-wrapped subshell. `exit` returns you to the parent shell. The `[REC <id>]` PS1 prefix is visible only inside the recording.
- Logs are read-only after `script` exits. Delete with `rm ~/.friction-log/fl-*` if you want.
