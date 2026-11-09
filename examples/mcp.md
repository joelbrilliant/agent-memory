# MCP server

`agent-memory serve` is a stdio MCP server that exposes document recall, session
recall and evidence-gated writes as first-class tools in any MCP-capable
harness. It speaks JSON-RPC 2.0 over
stdin/stdout, one message per line, and wraps the existing CLIs by subprocess so
there is exactly one implementation of the query and write logic. Because it
shells out to `recall`, MCP-driven recalls land in `usage.log` like any other
deliberate call, which keeps the self-audit honest.

It registers itself under the server name `agent-memory` and offers five tools:

- `recall` - inputs: `query` (required), `k` (optional), `source` (optional
  corpus-tag filter).
- `remember` - inputs: `content`, `source`, `evidence` (all required), `tags`
  (optional). The underlying tool still refuses to write without evidence, so a
  `remember` call missing evidence comes back as an error result, not a write.
- `session_recall` - inputs: `query` (required), `k`, `harness`,
  `current_harness`, `current_session_id`, and `since` and `until` as
  YYYY-MM-DD dates (optional).
- `session_read` - inputs: `session_id` (required), `harness`, `start` and
  `limit` (optional). Returns the session's dialogue in order, one page at a
  time.
- `session_list` - inputs: `limit`, `harness` and `sync` (optional).

Installed, it keeps the index in `~/.local/share/agent-memory`. Override the index or root with `AGENT_MEMORY_DB` and `AGENT_MEMORY_ROOT` if you keep them elsewhere.

## Generic registration

`agent-memory connect all` wires every tool it finds (`--remove` undoes it). For a tool it doesn't know, any harness that supports stdio MCP servers needs the same three things:

- command: the absolute path of `agent-memory` (`uv tool dir --bin` prints its folder)
- args: `serve`
- transport: stdio

There is no port to open; the harness launches the command and talks to it over stdin/stdout.

## Concrete example: Claude Code

```
claude mcp add agent-memory -- "$(uv tool dir --bin)/agent-memory" serve
```

After adding it, `recall` and `remember` show up as tools in the session. Verify with
`claude mcp list`.

## Concrete example: Grok

```
grok mcp add agent-memory -- "$(uv tool dir --bin)/agent-memory" serve
```

Set `AGENT_MEMORY_CALLER=grok` in the server environment when configuring by
file. Verify the real process, not just the config entry:

```
grok mcp doctor agent-memory
```

Then ask a Grok session to call `session_recall` for distinctive terms from a
conversation held in another harness. Grok prompt hooks cannot inject context
because passive hook stdout is ignored.

## Quick manual smoke test

You can drive the server by hand to confirm it responds before wiring it into a
harness:

```
printf '%s\n%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
    | agent-memory serve
```

You should get an `initialize` result followed by a `tools/list` result naming
`recall`, `remember`, `session_recall`, `session_read` and `session_list`.
