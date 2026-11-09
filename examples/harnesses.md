# Harness wiring notes

Agent memory is deliberately CLI-first: any harness that can run a shell command can
use it. Specific notes per harness:

## Claude Code

Two options, use both:
- Auto-recall on every prompt via the UserPromptSubmit hook - see
  [claude-code-hook.md](claude-code-hook.md).
- A line in your CLAUDE.md or a skill so deliberate recall happens at task
  start - see [agent-instructions.md](agent-instructions.md).

The hook can inject a relevant excerpt from another local harness. Connecting agent memory (`agent-memory connect claude`) also gives Claude the explicit `session_recall`,
`session_read` and `session_list` tools.

## Hermes Agent

The reliable path is a skill. Create
`~/.hermes/skills/<category>/agent-memory/SKILL.md` with standard skill
frontmatter (name, description stating when to use it) and the snippet from
[agent-instructions.md](agent-instructions.md) as the body, using `agent-memory recall` and `agent-memory remember` (with the absolute path from `uv tool dir --bin` if it isn't on `PATH`). Hermes agents load skills
before substantial work, so the description is what triggers usage - make it
say "use at the start of substantial tasks to recall past fixes and findings".

`agent-memory connect hermes` registers the MCP server where your Hermes version supports it, and prints the entry to add by hand where it doesn't.

Recent Hermes versions can run the same hook as a `pre_llm_call` shell hook.
The hook detects Hermes's wire format and emits native context. Keep the
explicit MCP tools as well so the agent can search deliberately.

## Codex

Add the [agent-instructions.md](agent-instructions.md) snippet to
`~/.codex/AGENTS.md` (or the project AGENTS.md) with the `agent-memory` command. Codex runs the CLIs via shell like anything else. `agent-memory connect codex` registers the stdio MCP server so session recall is a first-class tool.

## Grok

`agent-memory connect grok` registers the stdio MCP server. Set `AGENT_MEMORY_CALLER=grok` in its environment for clear usage receipts. Add the standing rule from
[agent-instructions.md](agent-instructions.md) to `AGENTS.md`, which Grok reads.

Do not install the Claude prompt hook as Grok auto-recall. Grok runs passive
`UserPromptSubmit` hooks, but ignores their stdout, so the returned context
never reaches the model. The supported continuity path is:

- Grok transcripts are indexed from `~/.grok/sessions`
- `session_recall` is available through the `agent-memory` MCP server
- the standing instruction tells Grok when to call it

Verify all three. A configured MCP entry alone is not proof.

## Anything else with a shell

The contract is four commands: `agent-memory ingest` (rebuild documents), `agent-memory recall "query" -k 5` (search documents), `agent-memory session recall "query" -k 5` (search dialogue), and `agent-memory remember --source X --evidence Y "text"` (write a verified lesson). Wire them wherever your harness keeps standing instructions.
For harnesses that speak MCP but not shell, use [mcp.md](mcp.md).
