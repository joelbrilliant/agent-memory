# agent-memory

Local, boring-on-purpose memory for AI agents. It searches the markdown you already have and the conversations you have already had with your agents (Claude Code, Codex, Grok and Hermes), and it only writes a memory when there is evidence for it. Plain SQLite FTS5 full-text search: no embeddings, no vector database, no daemon, no external service and no language model in the indexing or retrieval path. Python standard library only. Apache-2.0.

Built by Joel Brilliant, with the help of my agents. It works on its own, and it pairs with [agent-si](https://github.com/joelbrilliant/agent-si), a sourced memory for what is true right now. The agent-si installer installs both.

## Install

One command, on macOS or Linux (x86_64 or arm64):

```sh
curl -LsSf https://github.com/joelbrilliant/agent-memory/releases/latest/download/install.sh | sh
```

It downloads one wheel and its checksum from this project's GitHub release (an exact address, never a name looked up on a package index), checks the SHA-256 and stops if it doesn't match, installs [uv](https://docs.astral.sh/uv/) if you don't have it, installs agent memory as the `agent-memory` command, connects it to every agent tool it finds (Claude Code, Codex CLI, Gemini CLI, Grok Build, Hermes, Cursor), and builds a local index of your past agent sessions. It prints how to undo each step. Read the script first if you like: [install.sh](install.sh) is about 150 lines of POSIX `sh`.

To change no agent tool's settings, add `--no-connect`:

```sh
curl -LsSf https://github.com/joelbrilliant/agent-memory/releases/latest/download/install.sh | sh -s -- --no-connect
```

**Or tell your agent.** Paste this into your agent:

```text
Read https://raw.githubusercontent.com/joelbrilliant/agent-memory/main/AGENT-INSTALL.md and follow it to install agent memory on this machine. Ask me before you run anything that changes my machine, and before you index anything other than my agent sessions.
```

[AGENT-INSTALL.md](AGENT-INSTALL.md) is written for the agent: download the installer, check its SHA-256, run it, prove recall works, say what was connected and how to undo it.

To install a wheel you already hold: `sh install.sh --from <agent-memory wheel>`.

## What it keeps, and where

- **Nothing is indexed until you say so.** A fresh install holds no notes, no episodes and no seeded data. The installer indexes your past agent sessions once, from the folders the agent tools themselves keep (`~/.claude/projects`, `~/.codex/sessions`, `~/.grok/sessions`, `~/.hermes/state.db`), into a database on your machine. Your notes are indexed only when you list them.
- **Your index and sessions** live in `~/.local/share/agent-memory/` (`index.db`, `sessions.db`, `usage.log`, and the `episodes/` that `remember` writes). **Your lists** live in `~/.config/agent-memory/` (`corpus.txt`, `exclude.txt`, and optionally `session-sources.json`). Both survive an upgrade. Nothing is sent anywhere.

## Use it

```sh
mkdir -p ~/.config/agent-memory
cat > ~/.config/agent-memory/corpus.txt <<'LIST'
notes|~/notes/**/*.md
episodes|~/.local/share/agent-memory/episodes/**/*.md
LIST
agent-memory ingest                                   # build the index from the files listed there
agent-memory recall "some words from a note" -k 5     # search it
agent-memory remember --source me --evidence "commit abc123" "what I learned"
```

`corpus.txt` is a list of `tag|glob` lines. Leading `~/` is expanded, and only `.md` files are indexed. See [corpus.example.txt](corpus.example.txt). The `episodes` line makes what you `remember` recallable.

Past agent sessions:

```sh
agent-memory session sync                             # again whenever you like; only changed sessions are re-read
agent-memory session list -n 20
agent-memory session recall "distinctive terms from an earlier conversation" -k 5
```

Other commands: `agent-memory serve` (the MCP server on standard input and output, which `connect` wires into your tools), `agent-memory connect all` (or `claude`, `codex`, `gemini`, `grok`, `cursor`, `hermes`; `--remove` undoes it), `agent-memory usage` (model tokens per session, counts only). The older names `recall`, `remember` and `session-memory` still work.

Extra Hermes profiles can be listed in `~/.config/agent-memory/session-sources.json`: `{"hermes_profiles": {"work": "~/.hermes/profiles/work/state.db"}}`.

## Using it with agent-si

[agent-si](https://github.com/joelbrilliant/agent-si) is a separate tool. Install either one, or both: neither needs the other, and each connects only itself to your tools.

If you use both, they split the work:
- **agent-si** holds what's true now: facts with their sources, actions, waits and disputes.
- **Agent memory** holds what happened before: past sessions, notes and lessons.

Agent memory's tools tell your agent to check an agent-si brain for anything current. `agent-memory usage` counts model tokens per session, and `brain usage report` shows those counts when both are installed.

## The two rules that matter

**Evidence-gated writes.** `remember` will not write an episode without `--evidence` and a `--source`. This is deliberate and it is a hard gate, not a warning. An unverified claim in a memory store is worse than no memory, because it comes back later wearing authority: it gets trusted exactly when you have stopped checking it. The evidence can be a file path, a commit SHA, a PR or issue URL, or a log path. If you cannot point at one, you do not get to write. Note the gate forces a *reference*, it does not validate one - a fabricated path passes the tool. That is deliberate: verification is the self-audit's job, and a citation that leads nowhere is exactly what an audit catches.

**One home per fact.** This store owns exactly one thing: episodes. Everything else it indexes, it reads and never claims to own. Derived files (`index.db`, `sessions.db`, `usage.log`, `hook.log`, `ingest.log`) are rebuilt per machine and never synced. If a fact belongs in a skill file or a design doc, it goes there, not into an episode that forks the truth.

## Integrations

Each is a short, practical file under [examples/](examples/):

- [examples/claude-code-hook.md](examples/claude-code-hook.md) - auto-recall on every Claude Code prompt via a UserPromptSubmit hook.
- [examples/mcp.md](examples/mcp.md) - the MCP server, so `recall` and `remember` become first-class tools in an MCP-capable harness. `agent-memory connect` does the wiring for you.
- [examples/scheduled-ingest.md](examples/scheduled-ingest.md) - rebuild the index on a schedule (launchd on macOS, cron on Linux).
- [examples/self-audit.md](examples/self-audit.md) - a scheduled prompt that judges whether recall earned its keep and reports KEEP or KILL.
- [examples/agent-instructions.md](examples/agent-instructions.md) - a copy-paste system-prompt snippet for any agent harness.
- [examples/session-continuity.md](examples/session-continuity.md) - session source paths, privacy boundaries, verification and per-harness behaviour.

## Self-audit

Schedule a checkpoint that is allowed to recommend deleting agent memory. Memory that cannot prove it changed an outcome should die: it costs attention on every read and it accumulates rot. Point a scheduled prompt at `usage.log`, `hook.log` and `episodes/`, ask whether recall demonstrably changed any outcome over the window, and have it report KEEP or KILL with evidence. It never deletes anything itself. See [examples/self-audit.md](examples/self-audit.md).

## Honest limitations

- It is keyword search (BM25 with porter stemming), not semantic search. It finds documents that share words with your query, stemmed; it does not understand meaning. Synonyms and paraphrases can miss.
- It indexes markdown files only. Other formats are ignored.
- It is a single-user, local design. There is no server, no multi-tenant story, and no concurrency model beyond one person on one machine.
- The auto-recall hook uses a small hard-coded English stopword list, so its term extraction is English-only. The CLIs themselves are language-agnostic.
- Grok indexes local dialogue and exposes deliberate recall through MCP, but its passive prompt hooks ignore stdout. It cannot receive silent hook injection. Use `session_recall` through MCP and a standing instruction.
- Session continuity is local to one machine. If harness histories live on different machines, each machine has its own index unless you deliberately provide a secure shared filesystem. Raw transcripts are never synced.
- No performance claim is made here. [benchmarks/longmemeval_compare.py](benchmarks/longmemeval_compare.py) measures session recall on the public LongMemEval data, so you can reproduce a number yourself.

## Updates and uninstall

New releases are on the [releases page](https://github.com/joelbrilliant/agent-memory/releases). Nothing here checks for them or fetches anything by name, so run the install command again when you want the newest: it upgrades the tool and keeps your data.

```sh
agent-memory connect all --remove
uv tool uninstall agent-memory
```

Your data stays in `~/.local/share/agent-memory` and `~/.config/agent-memory` until you delete those folders.

## Changes

- 0.2.1:
  - Session recall ranks by any term, so a message that misses one word of the query is still found. The auto-recall hook still tries every term first.
  - `session_read` (`agent-memory session read <session-id> --start 8`) returns a session's dialogue in order, 40 messages a page, and each recall excerpt shows its message number.
  - Session recall takes `since` and `until` dates (`--since 2026-10-01 --until 2026-10-31`, local days, both included).
  - Hermes session discovery also finds the sessions current Hermes Agent writes with `source = 'local'` and the surface (cli, telegram and so on) in a `created_source` column. Older `state.db` files, and rows migrated from them, are read as before, and an untitled Hermes session is named after its surface.
- 0.2.0: first public release.

## Working from a clone

The code is in this repository: `agent_memory/` (the command), `ingest.py`, `mcp_server.py`, `session_adapters.py` and `session_continuity.py`. `./test.sh` runs the smoke test and the unit tests, and `python -m pytest tests/test_package.py` needs `uv` and builds and installs a wheel into a temporary folder. The scripts `recall`, `remember` and `session-memory` in the root also run straight from a clone, keeping their files beside them.

## Requirements

- macOS or Linux. The installer uses uv's own Python 3.13, so SQLite and its full-text search come with it. From a clone, Python 3.11 or newer with SQLite compiled with FTS5:

```sh
python3 -c "import sqlite3; c=sqlite3.connect(':memory:'); c.execute(\"CREATE VIRTUAL TABLE t USING fts5(x)\"); print('fts5 ok')"
```

No other dependencies.
