# Full continuity install prompt

Give this to the agent that can inspect your local machine. The agent should adapt to the agent tools that are actually installed.

## Copy this prompt

> Install agent memory as my local cross-harness memory and continuity layer. Read
> https://raw.githubusercontent.com/joelbrilliant/agent-memory/main/AGENT-INSTALL.md,
> https://raw.githubusercontent.com/joelbrilliant/agent-memory/main/examples/session-continuity.md and
> https://raw.githubusercontent.com/joelbrilliant/agent-memory/main/examples/harnesses.md completely before
> changing anything.
>
> My goal is to move between the agent tools I have installed (Hermes Agent, Claude Code, Codex, Grok) without
> repeating prior context. Use only the ones that are installed on this machine. Do not install a vector database,
> embedding service, daemon or separate LLM memory layer.
>
> Before indexing, show me two separate approval lists:
>
> 1. the markdown corpus you propose for durable work recall
> 2. the exact local session-history paths you propose for transcript recall
>
> Do not index either list until I approve it. Never copy raw transcripts into Git or cloud storage. Preserve my
> existing agent-tool settings and merge narrow changes instead of replacing whole config files.
>
> After approval, build both indexes, connect the `agent-memory` MCP server to every compatible tool (the installer's
> `connect` step does this), add the prompt hook where supported, and add a small standing instruction that says to
> call `session_recall` before asking me to repeat earlier context.
>
> Grok prompt hooks are passive and ignore stdout. Do not claim silent Grok injection. For Grok, verify transcript
> indexing, MCP health and one real `session_recall` call from a Grok session.
>
> Verify the result with:
>
> - a document known-answer query
> - `agent-memory session list` with counts by installed tool
> - one real cross-tool canary conversation
> - a negative privacy check proving system prompts, reasoning, tools, generated summaries and secret-shaped
>   messages are excluded
>
> Report observed evidence, exact files changed, and any tool that could not be wired. Do not claim success from
> configuration alone.

## What to expect

The agent will pause twice for approval: once for documents and once for chat history. That is intentional. Everything after approval is local, deterministic and reversible.
