"""Phase 4c: agent memory as its own package. A real uv install from a wheel (offline) into a temporary tool folder,
data outside the tool environment, the old script names as aliases, connect, and token counts. Invented data only."""
from __future__ import annotations

import hashlib
import http.server
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import zipfile
import threading
from functools import partial
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_memory import __version__, usage  # noqa: E402


def _uv_python() -> bool:
    if not shutil.which("uv"):
        return False
    done = subprocess.run(["uv", "python", "find", "--managed-python", "3.13"], capture_output=True, text=True)
    return done.returncode == 0


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    if not _uv_python():
        pytest.skip("needs uv and a uv-managed Python 3.13")
    work = tmp_path_factory.mktemp("install")
    subprocess.run(["uv", "build", "--wheel", "-q", "--out-dir", str(work / "wheels"), str(ROOT)], check=True)
    wheel = next((work / "wheels").glob("agent_memory-*.whl"))
    env = {**os.environ, "UV_TOOL_DIR": str(work / "tools"), "UV_TOOL_BIN_DIR": str(work / "bin"), "UV_OFFLINE": "1",
           "HOME": str(work / "home"), "XDG_DATA_HOME": str(work / "home" / "data"), "XDG_CONFIG_HOME": str(work / "home" / "config"),
           "UV_CACHE_DIR": os.environ.get("UV_CACHE_DIR", str(Path.home() / ".cache" / "uv")),
           "UV_PYTHON_INSTALL_DIR": str(Path.home() / ".local" / "share" / "uv" / "python")}
    for key in ("AGENT_MEMORY_DB", "AGENT_MEMORY_ROOT", "AGENT_SESSION_DB", "AGENT_MEMORY_USAGE_LOG", "AGENT_MEMORY_CORPUS"):
        env.pop(key, None)
    (work / "home").mkdir()
    done = subprocess.run(["uv", "tool", "install", "--managed-python", "--python", "3.13", str(wheel)], env=env,
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return work, env, wheel


def _run(work, env, *argv, stdin=None):
    return subprocess.run([str(work / "bin" / argv[0]), *argv[1:]], env=env, capture_output=True, text=True, input=stdin)


def test_install_ingest_recall_and_the_old_names(installed) -> None:
    work, env, wheel = installed
    assert _run(work, env, "agent-memory", "--version").stdout.strip() == f"agent-memory {__version__}"
    notes = work / "home" / "notes"
    notes.mkdir()
    (notes / "vite.md").write_text("# Vite zombie prevention\n\nUse scripts/start-vite.sh, never npx vite directly.\n")
    config = work / "home" / "config" / "agent-memory"
    config.mkdir(parents=True)
    (config / "corpus.txt").write_text(f"notes|{notes}/*.md\n")  # tag|glob
    done = _run(work, env, "agent-memory", "ingest")
    assert done.returncode == 0, done.stderr
    data = work / "home" / "data" / "agent-memory"
    assert (data / "index.db").is_file()  # outside the tool environment
    assert not list((work / "tools").rglob("index.db"))
    found = _run(work, env, "agent-memory", "recall", "zombie vite")
    assert found.returncode == 0 and "vite.md" in found.stdout
    assert "vite.md" in _run(work, env, "recall", "zombie").stdout  # the old name still works
    before = (data / "index.db").read_bytes()
    done = subprocess.run(["uv", "tool", "install", "--reinstall", "--managed-python", "--python", "3.13", str(wheel)], env=env,
                          capture_output=True, text=True)
    assert done.returncode == 0 and (data / "index.db").read_bytes() == before  # an upgrade keeps the data


def test_serve_lists_recall_from_the_installed_package(installed) -> None:
    work, env, _ = installed
    lines = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
             {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
             {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "recall", "arguments": {"query": "zombie"}}}]
    done = _run(work, env, "agent-memory", "serve", stdin="".join(json.dumps(line) + "\n" for line in lines))
    answers = [json.loads(line) for line in done.stdout.splitlines()]
    assert "recall" in [tool["name"] for tool in answers[1]["result"]["tools"]]
    assert "vite.md" in answers[2]["result"]["content"][0]["text"]  # through the package's own recall, not a checkout path


def test_connect_uses_each_tools_command(installed, tmp_path) -> None:
    work, env, _ = installed
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    log = tmp_path / "calls.jsonl"
    for name in ("claude", "codex"):
        path = fakebin / name
        path.write_text(f"#!{sys.executable}\nimport json, sys\nopen({str(log)!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    home = work / "home"
    (home / ".cursor").mkdir(exist_ok=True)
    run_env = {**env, "PATH": f"{fakebin}:{work / 'bin'}:/usr/bin:/bin"}
    done = subprocess.run([str(work / "bin" / "agent-memory"), "connect", "claude", "codex", "cursor"], env=run_env,
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    results = {item["harness"]: item for item in json.loads(done.stdout)["results"]}
    assert {item["status"] for item in results.values()} == {"written"} and {item["smoke"] for item in results.values()} == {"pass"}
    exe = str((work / "bin" / "agent-memory").absolute())
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert ["mcp", "add", "--transport", "stdio", "--scope", "user", "agent-memory", "--", exe, "serve"] in calls
    cursor = json.loads((home / ".cursor" / "mcp.json").read_text())["mcpServers"]["agent-memory"]
    assert cursor == {"type": "stdio", "command": exe, "args": ["serve"]}


def test_token_counts_are_counts_and_unknown_is_never_zero(tmp_path) -> None:
    project = tmp_path / ".claude" / "projects" / "-Users-example-work"
    project.mkdir(parents=True)
    rows = [{"type": "user", "timestamp": "2026-10-12T01:00:00.000Z", "message": {"role": "user", "content": "Plan the pilot"}},
            {"type": "assistant", "timestamp": "2026-10-12T01:00:05.000Z", "message": {
                "model": "claude-opus-5-5", "usage": {"input_tokens": 120, "cache_read_input_tokens": 9000,
                                                      "cache_creation_input_tokens": 400, "output_tokens": 80},
                "content": [{"type": "tool_use", "name": "mcp__brain-work__brief"}, {"type": "tool_use", "name": "Bash"}]}},
            {"type": "assistant", "timestamp": "2026-10-12T01:01:00.000Z", "message": {
                "model": "claude-opus-5-5", "usage": {"input_tokens": 30, "cache_read_input_tokens": 9100,
                                                      "cache_creation_input_tokens": 0, "output_tokens": 20}, "content": []}}]
    (project / "s1.jsonl").write_text("\n".join(json.dumps(row) for row in rows))
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    con = sqlite3.connect(hermes / "state.db")
    con.execute("CREATE TABLE sessions (id TEXT, model TEXT, started_at TEXT, ended_at TEXT, input_tokens INTEGER, "
                "output_tokens INTEGER, cache_read_tokens INTEGER, cache_write_tokens INTEGER)")
    con.execute("INSERT INTO sessions VALUES ('h1', 'example-model', '2026-10-12 02:00:00', '2026-10-12 02:10:00', 500, 60, 0, 0)")
    con.commit()
    con.close()
    db = tmp_path / "usage.db"
    os.environ.pop("CLAUDE_CONFIG_DIR", None)
    os.environ.pop("HERMES_HOME", None)
    assert usage.collect(db, home=tmp_path) == 2
    found = usage.report(db, days=36500)["harnesses"]
    assert {k: found["claude"][k] for k in ("sessions", "input", "cache_read", "cache_write", "output", "tool_calls", "brain_tool_calls")} == {
        "sessions": 1, "input": 150, "cache_read": 18100, "cache_write": 400, "output": 100, "tool_calls": 2, "brain_tool_calls": 1}
    assert (found["hermes"]["input"], found["hermes"]["output"], found["hermes"]["tool_calls"]) == (500, 60, "unknown")
    for harness in ("codex", "grok", "gemini", "cursor"):
        assert found[harness]["input"] == "unknown" and found[harness]["sessions"] == "unknown"
    stored = sqlite3.connect(db).execute("SELECT session, project FROM session_usage WHERE harness = 'claude'").fetchone()
    assert "s1" not in stored[0] and "example" not in stored[1]  # hashed, never a path or a name


def _env_for(installed, tmp_path, fakes=()):
    """A machine of its own for install.sh: HOME, uv's folders and PATH in tmp_path, uv offline, fake agent tools."""
    _, env, _ = installed
    uv_dir = str(Path(shutil.which("uv")).parent)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir(exist_ok=True)
    log = tmp_path / "calls.jsonl"
    for name in fakes:
        path = fakebin / name
        path.write_text(f"#!{sys.executable}\nimport json, sys\nopen({str(log)!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    run_env = {**env, "HOME": str(home), "XDG_DATA_HOME": str(home / "data"), "XDG_CONFIG_HOME": str(home / "config"),
               "UV_TOOL_DIR": str(tmp_path / "tools"), "UV_TOOL_BIN_DIR": str(tmp_path / "bin"),
               "PATH": f"{fakebin}:{uv_dir}:/usr/bin:/bin"}
    return run_env, log


class Release:
    """A local stand-in for a GitHub release folder: the wheel and SHA256SUMS, served over http on 127.0.0.1. It
    records every path asked for, so a test can see that nothing but those two exact addresses was fetched."""

    def __init__(self, folder: Path, wheel: Path, corrupt: bool = False, sums: bool = True) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        data = wheel.read_bytes()
        (folder / wheel.name).write_bytes(data + b"damaged" if corrupt else data)
        if sums:
            (folder / "SHA256SUMS").write_text(f"{hashlib.sha256(data).hexdigest()}  {wheel.name}\n")
        self.paths: list[str] = []
        outer = self

        class Handler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                outer.paths.append(self.path)
                super().do_GET()

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(folder)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return f"http://127.0.0.1:{self.server.server_port}"

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()


def _install_sh(env, *args, base=None, stdin=None, script=None):
    run_env = {**env, **({"AGENT_MEMORY_INSTALL_BASE_URL": base} if base else {})}
    if stdin is not None:
        return subprocess.run(["sh", "-s", "--", *args], env=run_env, input=stdin, capture_output=True, text=True, timeout=300)
    return subprocess.run(["sh", str(script or ROOT / "install.sh"), *args], env=run_env, capture_output=True, text=True, timeout=300)


def test_install_sh_from_a_wheel_installs_agent_memory_only(installed, tmp_path) -> None:
    _, _, wheel = installed
    env, log = _env_for(installed, tmp_path, fakes=("claude",))
    done = _install_sh(env, "--from", str(wheel), "--no-connect")
    assert done.returncode == 0, done.stderr + done.stdout
    assert f"agent-memory {__version__}" in done.stdout and "Connecting agent memory" not in done.stdout
    assert "Indexing your past agent sessions" in done.stdout and not log.exists()  # --no-connect touched no tool
    assert sorted(path.name for path in (tmp_path / "bin").iterdir()) == ["agent-memory", "recall", "remember", "session-memory"]
    for args in (["--with-brain"], ["--with-memory"], ["--version", "0.1.0"], ["--print"]):
        assert _install_sh(env, *args).returncode == 2, args
    other = tmp_path / "other"
    other.mkdir()
    (other / "agent-memory").write_text("#!/bin/sh\n")
    (other / "agent-memory").chmod(0o755)
    done = _install_sh({**env, "PATH": f"{other}:{env['PATH']}"}, "--from", str(wheel))
    assert done.returncode == 1 and "already installed" in done.stderr


def test_the_default_install_downloads_the_exact_release_files_checks_them_connects_and_prints_the_undo(installed, tmp_path) -> None:
    _, _, wheel = installed
    env, log = _env_for(installed, tmp_path, fakes=("claude",))
    with Release(tmp_path / "release", wheel) as base:
        done = _install_sh(env, base=base)
    assert done.returncode == 0, done.stderr + done.stdout
    out = done.stdout
    assert f"{wheel.name} matches its checksum" in out and f"agent-memory {__version__}" in out
    assert "  claude: written, smoke test pass" in out and "undo: agent-memory connect all --remove" in out
    assert "Indexing your past agent sessions" in out and "uv tool uninstall agent-memory" in out
    exe = str((tmp_path / "bin" / "agent-memory").absolute())
    assert ["mcp", "add", "--transport", "stdio", "--scope", "user", "agent-memory", "--", exe, "serve"] in [
        json.loads(line) for line in log.read_text().splitlines()]
    assert (tmp_path / "home" / "data" / "agent-memory" / "sessions.db").is_file()  # the session index was built


def test_the_default_url_is_an_exact_release_address_and_only_the_wheel_and_the_sums_are_fetched(installed, tmp_path) -> None:
    text = (ROOT / "install.sh").read_text()
    assert 'BASE="${AGENT_MEMORY_INSTALL_BASE_URL:-https://github.com/joelbrilliant/agent-memory/releases/download/v$VERSION}"' in text
    assert re.search(rf'^VERSION="{re.escape(__version__)}"$', text, re.M)
    _, _, wheel = installed
    env, _ = _env_for(installed, tmp_path)
    release = Release(tmp_path / "release", wheel)
    with release as base:
        done = _install_sh(env, "--no-connect", base=base)
    assert done.returncode == 0, done.stderr + done.stdout
    assert release.paths == [f"/{wheel.name}", "/SHA256SUMS"]


def test_a_damaged_download_stops_before_anything_is_installed(installed, tmp_path) -> None:
    _, _, wheel = installed
    env, log = _env_for(installed, tmp_path, fakes=("claude",))
    with Release(tmp_path / "release", wheel, corrupt=True) as base:
        done = _install_sh(env, base=base)
    assert done.returncode == 1 and "failed its SHA-256 check" in done.stderr and "nothing was installed" in done.stderr
    assert not (tmp_path / "bin").exists() or not list((tmp_path / "bin").iterdir())
    assert not (tmp_path / "tools").exists() or not list((tmp_path / "tools").iterdir())
    assert not log.exists() and "matches its checksum" not in done.stdout
    # No SHA256SUMS at all, or none for this wheel, is also a stop.
    with Release(tmp_path / "bare", wheel, sums=False) as base:
        missing = _install_sh(env, base=base)
    assert missing.returncode == 1 and "SHA256SUMS" in missing.stderr and not (tmp_path / "bin").exists()
    (tmp_path / "other-sums").mkdir()
    with Release(tmp_path / "other-sums", wheel, sums=False) as base:
        (tmp_path / "other-sums" / "SHA256SUMS").write_text("0" * 64 + "  something-else.whl\n")
        absent = _install_sh(env, base=base)
    assert absent.returncode == 1 and "has no line for" in absent.stderr and not (tmp_path / "bin").exists()


def test_it_works_piped_into_sh_like_the_published_one_liner(installed, tmp_path) -> None:
    _, _, wheel = installed
    env, log = _env_for(installed, tmp_path, fakes=("claude",))
    with Release(tmp_path / "release", wheel) as base:
        done = _install_sh(env, "--no-connect", base=base, stdin=(ROOT / "install.sh").read_text())
    assert done.returncode == 0, done.stderr + done.stdout
    assert f"agent-memory {__version__}" in done.stdout and not log.exists()
    assert (tmp_path / "bin" / "agent-memory").is_file()


def test_nothing_in_the_repo_installs_or_fetches_agent_memory_by_name() -> None:
    pattern = re.compile(r"agent[-_]memory==|(?:pip3?|pipx|uvx)\s+(?:install\s+)?[\"']?agent-memory|uv\s+tool\s+install\b[^\n]*\s[\"']?agent-memory[\"']?\s*($|[`;&|)])", re.I)
    found = []
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT).as_posix()
        if not path.is_file() or path.suffix not in {".py", ".md", ".sh", ".toml", ".txt", ""} or rel.startswith(("tests/", "build/", ".git/")) or ".egg-info" in rel:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            if pattern.search(line):
                found.append(f"{rel}:{number}")
    assert not found, found


def test_connect_refuses_an_option_it_does_not_have(installed, tmp_path) -> None:
    work, env, _ = installed
    for flag in ("--print", "--yes", "--with-brain"):
        done = subprocess.run([str(work / "bin" / "agent-memory"), "connect", "all", flag], env=env, capture_output=True, text=True)
        assert done.returncode == 2 and f"unknown option {flag}" in done.stderr and "--remove" in done.stderr and done.stdout == ""


def test_a_fresh_install_holds_nothing_of_anyones(installed, tmp_path) -> None:
    """Clean slate: no seeded notes, episodes or sessions. recall and session recall find nothing until the person's
    own files exist, and the first hit is theirs."""
    work, _, _ = installed
    env, _ = _env_for(installed, tmp_path)
    home = tmp_path / "home"

    def am(*argv):
        return subprocess.run([str(work / "bin" / "agent-memory"), *argv], env={**env, "PATH": f"{work / 'bin'}:/usr/bin:/bin"},
                              capture_output=True, text=True, timeout=120)

    recall = am("recall", "memory")
    assert recall.returncode == 1 and "index.db not found" in recall.stderr and "agent-memory ingest" in recall.stderr
    assert "no session results" in am("session", "recall", "memory").stdout.lower()
    assert am("session", "list", "-n", "5").returncode == 0
    assert not (home / "data" / "agent-memory" / "episodes").exists() and not (home / "config" / "agent-memory" / "corpus.txt").exists()
    # The tool's own files hold no corpus and no seeded episode either.
    shipped = zipfile.ZipFile(next((work / "wheels").glob("*.whl"))).namelist()
    assert not [name for name in shipped if name.startswith(("episodes/", "tests/", "benchmarks/")) or name.endswith(("corpus.txt", "index.db", "sessions.db"))]
    # Then the person's own files arrive, and only they are found.
    notes = home / "notes"
    notes.mkdir()
    (notes / "mine.md").write_text("# Mine\n\nThe quokka rota changes on Fridays.\n")
    (home / "config" / "agent-memory").mkdir(parents=True, exist_ok=True)
    (home / "config" / "agent-memory" / "corpus.txt").write_text(f"notes|{notes}/*.md\n")
    assert am("ingest").returncode == 0
    found = am("recall", "quokka rota").stdout
    assert "mine.md" in found and found.count(". [") == 1
    assert "no results" in am("recall", "zebra").stdout.lower()


def test_serve_points_agents_at_the_brain_for_anything_current(installed) -> None:
    work, env, _ = installed
    lines = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
             {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    done = _run(work, env, "agent-memory", "serve", stdin="".join(json.dumps(line) + "\n" for line in lines))
    answers = [json.loads(line) for line in done.stdout.splitlines()]
    assert "agent-si brain" in answers[0]["result"]["instructions"]
    tools = {tool["name"]: tool["description"] for tool in answers[1]["result"]["tools"]}
    assert "agent-si brain" in tools["recall"] and "agent-si brain" in tools["session_recall"]
