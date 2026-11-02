"""agent-memory connect (product section 6.4): the same safe-write rules as the brain's `brain connect`, vendored as
one small file so a memory-only install can connect without hand-editing a config. Each tool's own command first,
a strict-JSON merge for Cursor, a printed entry otherwise. Never a write through a link or into unparseable JSON."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

NAME = "agent-memory"
HARNESSES = ("claude", "codex", "gemini", "grok", "cursor", "hermes")


def command() -> str:
    """The absolute path of the installed agent-memory, so a GUI app that doesn't inherit PATH still finds it."""
    folder = os.environ.get("UV_TOOL_BIN_DIR")
    if not folder and shutil.which("uv"):
        done = subprocess.run(["uv", "tool", "dir", "--bin"], capture_output=True, text=True, check=False)
        folder = done.stdout.strip() if done.returncode == 0 else ""
    for candidate in ([Path(folder) / NAME] if folder else []) + [Path(shutil.which(NAME) or "/nonexistent")]:
        if candidate.is_file():
            return str(candidate.absolute())  # the shim in uv's bin folder, which survives an upgrade
    raise SystemExit("agent-memory: install it as a uv tool first (sh install.sh --from <agent-memory wheel>)")


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=120, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(argv, 127, "", type(exc).__name__)


def _cursor(exe: str, remove: bool) -> str:
    path = Path.home() / ".cursor" / "mcp.json"
    wanted = {"type": "stdio", "command": exe, "args": ["serve"]}
    if path.is_symlink():
        return "printed"
    try:
        raw = path.read_text(encoding="utf-8") if path.exists() else ""
        data = json.loads(raw) if raw.strip() else {}
    except (OSError, ValueError):
        return "printed"
    servers = data.get("mcpServers", {}) if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        return "printed"
    if remove:
        if NAME not in servers:
            return "unchanged"
        servers = {k: v for k, v in servers.items() if k != NAME}
    elif servers.get(NAME) == wanted:
        return "unchanged"
    else:
        servers = {**servers, NAME: wanted}
    if path.exists():
        shutil.copy2(path, path.with_name(f"mcp.json.memory-backup-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".mcp.json.{os.getpid()}.tmp")
    temp.write_text(json.dumps({**data, "mcpServers": servers}, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)
    return "removed" if remove else "written"


def connect(harness: str, exe: str, remove: bool) -> dict:
    if harness == "cursor":
        status = _cursor(exe, remove)
        return {"harness": harness, "status": status}
    plans = {
        "claude": (["mcp", "add", "--transport", "stdio", "--scope", "user", NAME, "--", exe, "serve"],
                   ["mcp", "remove", "--scope", "user", NAME]),
        "codex": (["mcp", "add", NAME, "--", exe, "serve"], ["mcp", "remove", NAME]),
        "gemini": (["mcp", "add", "-s", "user", NAME, exe, "serve"], ["mcp", "remove", "-s", "user", NAME]),
        "grok": (["mcp", "add", "-s", "user", NAME, exe, "--", "serve"], ["mcp", "remove", "-s", "user", NAME]),
        "hermes": (["mcp", "add", NAME, "--command", exe, "--args", "serve"], ["mcp", "remove", NAME]),
    }
    tool = shutil.which(harness)
    if tool is None or harness not in plans:
        snippet = {"mcpServers": {NAME: {"type": "stdio", "command": exe, "args": ["serve"]}}}
        return {"harness": harness, "status": "printed", "text": json.dumps(snippet, indent=2)}
    done = _run([tool, *(plans[harness][1] if remove else plans[harness][0])])
    return {"harness": harness, "status": ("removed" if remove else "written") if done.returncode == 0 else "failed"}


def smoke(exe: str) -> str:
    lines = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
             {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    done = subprocess.run([exe, "serve"], input="".join(json.dumps(line) + "\n" for line in lines), capture_output=True,
                          text=True, timeout=60, check=False)
    try:
        answers = [json.loads(line) for line in done.stdout.splitlines() if line.strip()]
    except ValueError:
        return "fail"
    tools = [tool.get("name") for answer in answers for tool in (answer.get("result") or {}).get("tools", [])]
    return "pass" if "recall" in tools else "fail"


USAGE = "usage: agent-memory connect HARNESS... | all [--remove]  (HARNESS is one of: " + ", ".join(HARNESSES) + ")\n"


def main(argv: list[str]) -> int:
    unknown = [arg for arg in argv if arg.startswith("-") and arg != "--remove"]
    if unknown:
        sys.stderr.write(f"agent-memory connect: unknown option {unknown[0]}; the only option is --remove (it takes the entry out again)\n"
                         + USAGE)
        return 2
    remove = "--remove" in argv
    names = [arg for arg in argv if not arg.startswith("--")]
    if not names:
        sys.stderr.write(USAGE)
        return 2
    exe = command()
    if names == ["all"]:
        names = [h for h in HARNESSES if (h == "cursor" and (Path.home() / ".cursor").is_dir()) or shutil.which(h)]
    results = [connect(name, exe, remove) for name in names]
    if not remove:
        verdict = smoke(exe)
        for item in results:
            item["smoke"] = verdict
    print(json.dumps({"results": results}, sort_keys=True))
    return 1 if any(item["status"] == "failed" or item.get("smoke") == "fail" for item in results) else 0
