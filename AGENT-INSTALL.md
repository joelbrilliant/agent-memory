# Install agent-memory, for an agent

This file is for an AI agent installing agent memory for a person. It uses only this repository's public release. Do the steps in order, stop at the first one that fails, and show the output of each check rather than saying it passed. Two rules bind you throughout: never index documents or local chat history the person hasn't approved, and never claim a step worked without its output.

Agent memory searches a person's markdown notes and their past agent sessions with plain SQLite full-text search, and writes a memory only with evidence. Joel Brilliant built it.

## 1. Ask first

Tell the person, in plain words, that the installer will:
- install `uv` (a Python tool installer) if they don't have it, then agent memory as a `uv` tool, from a wheel it downloads from this project's GitHub release and checks against a SHA-256 first;
- add an MCP entry for agent memory to each agent tool it finds (Claude Code, Codex CLI, Gemini CLI, Grok Build, Hermes, Cursor);
- read their past agent session files once to build a local search index: `~/.claude/projects`, `~/.codex/sessions`, `~/.grok/sessions` and `~/.hermes/state.db`, where they exist. The index stays on their machine in `~/.local/share/agent-memory`.

Ask whether they want their agent tools connected (if not, you will add `--no-connect`) and whether the session index is fine. Don't run anything before they say yes. Notes and documents are a separate step (5) with their own approval.

## 2. Check the machine

macOS or Linux, x86_64 or arm64, with `curl` and either `shasum` or `sha256sum`:

```sh
uname -sm
command -v curl shasum sha256sum
```

## 3. Download the installer and check it

Work in a new empty folder:

```sh
mkdir -p ~/Downloads/agent-memory-install && cd ~/Downloads/agent-memory-install
curl -fLO https://github.com/joelbrilliant/agent-memory/releases/latest/download/install.sh
curl -fLO https://github.com/joelbrilliant/agent-memory/releases/latest/download/SHA256SUMS
grep ' install.sh$' SHA256SUMS | shasum -a 256 -c -        # on Linux: sha256sum -c -
```

It must print `install.sh: OK`. If it doesn't, stop and tell the person: don't run the file.

## 4. Run it

```sh
sh install.sh
```

Add `--no-connect` if they didn't want their agent tools connected. The script downloads the wheel and `SHA256SUMS` from the release for its own version, stops before installing if the wheel doesn't match, installs, connects, indexes the sessions, and prints how to undo each step. It never fetches agent memory by name from a package index, and neither should you: don't use `pip`, `pipx`, `uvx` or `uv tool install` with just the name, because the name isn't published and could belong to someone else.

## 5. Prove it works

A new terminal may not have uv's tool folder on its `PATH` yet, so use the full path:

```sh
AM="$(uv tool dir --bin)/agent-memory"
"$AM" --version
"$AM" session list -n 5
```

Right after install nothing of the person's notes is indexed, and there are no seeded notes or episodes: `session list` shows only what is in their own agent session files, and `"$AM" recall "anything"` says there is no index until they approve a list of notes. Report that as the starting state.

Then, only with their approval, add notes. Explore for the markdown they value (a notes folder, project docs, past reviews, a wiki or vault) and never include `.git`, dependency folders, credential or config folders, or other people's data. Show them the draft of `~/.config/agent-memory/corpus.txt` (`tag|glob` lines, see `corpus.example.txt` in this repository) and wait for a yes:

```sh
mkdir -p ~/.config/agent-memory
# write the approved lines, plus: episodes|~/.local/share/agent-memory/episodes/**/*.md
"$AM" ingest
```

Report the whole summary, especially the `secret-scan` count and the skipped paths on stderr: files that hold key-shaped strings deserve attention whatever this install does.

Ask for 3 to 5 things they know are in their notes, and run `"$AM" recall "<words that appear in the note>" -k 5` for each. This is keyword search with stemming, not semantic search: phrase the query with words likely to be in the document. The right document should be in the top 3. Show them the actual output, and don't call the install done on an empty index.

For sessions, ask for one distinctive phrase from an earlier conversation and run `"$AM" session recall "<phrase>" -k 5`. The correct tool and conversation should come back. A session hit is a lead, not authority: check the live task before acting on it.

## 6. Tell the person what happened

Report, from the installer's own output: the version installed; which agent tools were connected (lines like `claude: written, smoke test pass`) and which weren't; that agent tools must be restarted to see the new MCP entry; and how to undo each part:
- `agent-memory connect all --remove` takes out the tool entries;
- `uv tool uninstall agent-memory` removes the tool;
- the index and sessions are theirs, in `~/.local/share/agent-memory` and `~/.config/agent-memory`, and stay until they delete those folders.

## Later

- Wire the standing instruction from [examples/agent-instructions.md](examples/agent-instructions.md) into their agent's own instructions if they want deliberate recall at the start of substantial work.
- Rebuild the index on a schedule ([examples/scheduled-ingest.md](examples/scheduled-ingest.md)).
- Schedule the self-audit about two weeks out, which is allowed to recommend deleting agent memory ([examples/self-audit.md](examples/self-audit.md)).
- To update, repeat steps 3 and 4 with the newest release: it upgrades the tool and keeps their data.
