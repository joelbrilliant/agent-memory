"""Model usage per session (product section 9.4, Phase 4c): the session_usage table, counts only.

Each adapter reads one harness's own local files and pins the version it was checked against. A field a harness
doesn't record is "unknown", never zero. Codex, Grok, Gemini CLI and Cursor report "unknown" until their formats
are measured on a real install; Cursor keeps no local token file at all.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOKENS = ("input", "cache_read", "cache_write", "output")
TESTED = {"claude": "Claude Code 2.1.295 (message.usage)", "hermes": "Hermes state.db sessions table"}
UNMEASURED = ("codex", "grok", "gemini", "cursor")
SCHEMA = """CREATE TABLE IF NOT EXISTS session_usage (
  harness TEXT NOT NULL, session TEXT NOT NULL, started_at TEXT, ended_at TEXT, model TEXT,
  input INTEGER, cache_read INTEGER, cache_write INTEGER, output INTEGER,
  tool_calls INTEGER, brain_tool_calls INTEGER, project TEXT, PRIMARY KEY (harness, session))"""


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _stamp(value) -> str | None:
    if not isinstance(value, str) or len(value) < 19:
        return None
    return value[:19].replace(" ", "T") + "Z"


def claude_sessions(root: Path):
    """One row per transcript: summed message.usage, the model, tool calls and brain tool calls."""
    for path in sorted(root.glob("*/*.jsonl")):
        totals = dict.fromkeys(TOKENS, 0)
        seen = False
        model, first, last, tools, brain = None, None, None, 0, 0
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            message = row.get("message") if isinstance(row, dict) else None
            stamp = _stamp(row.get("timestamp")) if isinstance(row, dict) else None
            if stamp:
                first, last = first or stamp, stamp
            if not isinstance(message, dict) or row.get("type") != "assistant":
                continue
            usage = message.get("usage")
            if isinstance(usage, dict):
                seen = True
                for kind, key in (("input", "input_tokens"), ("cache_read", "cache_read_input_tokens"),
                                  ("cache_write", "cache_creation_input_tokens"), ("output", "output_tokens")):
                    value = usage.get(key)
                    totals[kind] += value if isinstance(value, int) else 0
            model = message.get("model") if isinstance(message.get("model"), str) else model
            for block in message.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tools += 1
                    brain += str(block.get("name", "")).startswith("mcp__brain")
        yield {"harness": "claude", "session": _hash(path.name), "started_at": first, "ended_at": last, "model": model,
               **(totals if seen else dict.fromkeys(TOKENS)), "tool_calls": tools, "brain_tool_calls": brain,
               "project": _hash(path.parent.name)}


def hermes_sessions(db: Path):
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.Error:
        return
    try:
        columns = {row[1] for row in con.execute("PRAGMA table_info(sessions)")}
        wanted = {"input": "input_tokens", "cache_read": "cache_read_tokens", "cache_write": "cache_write_tokens",
                  "output": "output_tokens"}
        picks = [wanted[kind] if wanted[kind] in columns else "NULL" for kind in TOKENS]
        for row in con.execute(f"SELECT id, model, started_at, ended_at, {', '.join(picks)} FROM sessions"):
            yield {"harness": "hermes", "session": _hash(str(row[0])), "started_at": _stamp(str(row[2] or "")),
                   "ended_at": _stamp(str(row[3] or "")), "model": row[1], **dict(zip(TOKENS, row[4:8])),
                   "tool_calls": None, "brain_tool_calls": None, "project": None}
    except sqlite3.Error:
        return
    finally:
        con.close()


def collect(db: Path, home: Path | None = None) -> int:
    home = home or Path.home()
    claude_root = Path(os.environ.get("CLAUDE_CONFIG_DIR") or home / ".claude") / "projects"
    hermes_db = Path(os.environ.get("HERMES_HOME") or home / ".hermes") / "state.db"
    rows = list(claude_sessions(claude_root)) + list(hermes_sessions(hermes_db))
    con = sqlite3.connect(str(db))
    try:
        con.execute(SCHEMA)
        con.executemany("INSERT OR REPLACE INTO session_usage VALUES (:harness, :session, :started_at, :ended_at, :model, "
                        ":input, :cache_read, :cache_write, :output, :tool_calls, :brain_tool_calls, :project)", rows)
        con.commit()
    finally:
        con.close()
    return len(rows)


def report(db: Path, days: int) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    con = sqlite3.connect(str(db))
    try:
        con.execute(SCHEMA)
        found = {}
        for harness in ("claude", "hermes"):
            rows = con.execute("SELECT input, cache_read, cache_write, output, tool_calls, brain_tool_calls FROM session_usage "
                               "WHERE harness = ? AND coalesce(ended_at, started_at, '') >= ?", (harness, since)).fetchall()
            found[harness] = {"sessions": len(rows), "tested_on": TESTED[harness],
                              **{kind: (sum(r[i] for r in rows if r[i] is not None) if any(r[i] is not None for r in rows)
                                        else "unknown") for i, kind in enumerate(TOKENS)},
                              "tool_calls": sum(r[4] for r in rows if r[4] is not None) if any(r[4] is not None for r in rows) else "unknown",
                              "brain_tool_calls": sum(r[5] for r in rows if r[5] is not None) if any(r[5] is not None for r in rows) else "unknown"}
        for harness in UNMEASURED:
            found[harness] = {"sessions": "unknown", **dict.fromkeys(TOKENS, "unknown"), "tool_calls": "unknown",
                              "brain_tool_calls": "unknown", "tested_on": "not yet measured"}
        return {"days": days, "since": since, "harnesses": found}
    finally:
        con.close()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="agent-memory usage")
    parser.add_argument("--days", type=int, default=7)
    ns = parser.parse_args(argv)
    db = Path(os.environ["AGENT_SESSION_DB"]).with_name("usage.db")
    collect(db)
    print(json.dumps(report(db, ns.days), sort_keys=True, indent=2))
    return 0
