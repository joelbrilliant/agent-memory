"""agent-memory: ingest, recall, remember, session, serve, connect and usage (product section 6.4).

Installed, the data lives outside the tool environment, because uv replaces that environment on every upgrade:
the index, sessions, episodes and logs in ~/.local/share/agent-memory, and corpus.txt in ~/.config/agent-memory.
The existing environment variables override each, so a setup that already sets them keeps its places.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "agent-memory"


def config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "agent-memory"


def _defaults() -> None:
    data, config = data_dir(), config_dir()
    for key, value in (("AGENT_MEMORY_DB", data / "index.db"), ("AGENT_MEMORY_ROOT", data),
                       ("AGENT_SESSION_DB", data / "sessions.db"), ("AGENT_MEMORY_USAGE_LOG", data / "usage.log"),
                       ("AGENT_MEMORY_CORPUS", config / "corpus.txt"), ("AGENT_MEMORY_EXCLUDE", config / "exclude.txt")):
        os.environ.setdefault(key, str(value))
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    config.mkdir(parents=True, exist_ok=True, mode=0o700)


USAGE = """usage: agent-memory COMMAND [...]

  ingest              index the files corpus.txt lists (nothing is indexed until you approve corpus.txt)
  recall "query"      search the index
  remember ...        write an evidence-gated episode
  session ...         index and recall local agent sessions
  serve               the MCP server, on standard input and output
  connect HARNESS     wire an agent tool to it (claude, codex, gemini, grok, cursor, hermes, all)
  usage [--days N]    model tokens per harness, from local session files (counts only)
"""


def _run(module: str, argv: list[str]) -> int:
    sys.argv = [f"agent-memory {module}", *argv]
    if module == "ingest":
        import ingest

        return ingest.main() or 0
    if module == "recall":
        from agent_memory import recall

        return recall.main() or 0
    if module == "remember":
        from agent_memory import remember

        return remember.main() or 0
    if module == "session":
        import session_continuity

        return session_continuity.main(argv) or 0
    if module == "serve":
        import mcp_server

        return mcp_server.main() or 0
    raise SystemExit(USAGE)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write(USAGE)
        return 0 if argv else 2
    if argv[0] == "--version":
        from agent_memory import __version__

        print(f"agent-memory {__version__}")
        return 0
    _defaults()
    command, rest = argv[0], argv[1:]
    if command == "connect":
        from agent_memory import connect

        return connect.main(rest)
    if command == "usage":
        from agent_memory import usage

        return usage.main(rest)
    if command not in ("ingest", "recall", "remember", "session", "serve"):
        sys.stderr.write(USAGE)
        return 2
    return _run(command, rest)


# The old script names stay, as aliases (product section 6.4).
def recall_main() -> int:
    return main(["recall", *sys.argv[1:]])


def remember_main() -> int:
    return main(["remember", *sys.argv[1:]])


def session_main() -> int:
    return main(["session", *sys.argv[1:]])
