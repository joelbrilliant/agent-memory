#!/bin/sh
# agent-memory installer. Read it before you run it. It downloads one wheel and its checksum from this project's
# GitHub release (an exact address, never a name looked up on a package index), checks the SHA-256, installs uv if
# needed, installs agent memory as a uv tool on uv's own Python (so SQLite and its full-text search come with it),
# connects it to every agent tool it finds, and indexes your past agent sessions once.
#   curl -LsSf https://github.com/joelbrilliant/agent-memory/releases/latest/download/install.sh | sh
#   curl -LsSf https://github.com/joelbrilliant/agent-memory/releases/latest/download/install.sh | sh -s -- --no-connect
#   sh install.sh [--no-connect] [--from WHEEL]
# --from installs a wheel you already hold and downloads nothing. agent-si, the brain, is a separate tool; this
# installs agent memory only.
set -eu

UV_VERSION="0.11.6"  # pinned, at least two weeks old when chosen, bumped on purpose
UV_MIN="0.9.0"       # a uv on PATH older than this is passed over for the pinned copy
VERSION="0.2.1"
PYTHON="3.13"
# For tests only: a different folder (an http:// or file:// address) holding the wheel and SHA256SUMS.
BASE="${AGENT_MEMORY_INSTALL_BASE_URL:-https://github.com/joelbrilliant/agent-memory/releases/download/v$VERSION}"
FROM=""
CONNECT=1
TMP=""

say() { printf '%s\n' "$*"; }
die() { printf 'install.sh: %s\n' "$1" >&2; exit "${2:-1}"; }

usage() {
  say "usage: sh install.sh [--no-connect] [--from WHEEL]"
  say "  --no-connect   install and index your sessions, but don't change any agent tool's settings"
  say "  --from WHEEL   install this agent-memory wheel and download nothing"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --from) [ $# -ge 2 ] || die "--from needs a wheel" 2; FROM="$2"; shift 2 ;;
    --no-connect) CONNECT=""; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option $1 (see --help). agent memory is never fetched by name from a package index" 2 ;;
  esac
done

case "$(uname -s)" in Darwin|Linux) ;; *) die "agent memory runs on macOS and Linux only" ;; esac
case "$(uname -m)" in x86_64|amd64|arm64|aarch64) ;; *) die "agent memory runs on x86_64 and arm64 only" ;; esac

sha256() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
  else sha256sum "$1" | awk '{print $1}'; fi
}

# True when version $1 is at least $2 (both X.Y.Z).
at_least() { [ "$(printf '%s\n%s\n' "$1" "$2" | sort -t. -k1,1n -k2,2n -k3,3n | head -n 1)" = "$2" ]; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/agent-memory-install.XXXXXX")" || die "can't make a temporary folder"
trap 'rm -rf "$TMP"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

# Download the wheel and SHA256SUMS from $BASE, check the wheel against its line in SHA256SUMS, and set FROM to it.
# Nothing is installed from a download that doesn't match.
fetch_wheel() {
  command -v curl >/dev/null 2>&1 || die "curl isn't here to download with; install curl (Ubuntu: apt install curl ca-certificates) and run this again"
  command -v shasum >/dev/null 2>&1 || command -v sha256sum >/dev/null 2>&1 || die "neither shasum nor sha256sum is here to check the download with"
  wheel="agent_memory-$VERSION-py3-none-any.whl"
  say "Downloading $wheel from $BASE"
  if [ -n "${AGENT_MEMORY_INSTALL_BASE_URL:-}" ]; then PROTO=""; else PROTO="--proto =https --tlsv1.2"; fi
  # shellcheck disable=SC2086
  curl -fsSL $PROTO -o "$TMP/$wheel" "$BASE/$wheel" || die "couldn't download $BASE/$wheel; check your connection, or download the wheel from https://github.com/joelbrilliant/agent-memory/releases and run: sh install.sh --from WHEEL"
  # shellcheck disable=SC2086
  curl -fsSL $PROTO -o "$TMP/SHA256SUMS" "$BASE/SHA256SUMS" || die "couldn't download $BASE/SHA256SUMS, so the wheel can't be checked and nothing was installed"
  want="$(awk -v name="$wheel" '{ n = $2; sub(/^\*/, "", n); if (n == name) { print $1; exit } }' "$TMP/SHA256SUMS")"
  [ -n "$want" ] || die "SHA256SUMS has no line for $wheel, so nothing was installed"
  got="$(sha256 "$TMP/$wheel")"
  [ "$got" = "$want" ] || die "$wheel failed its SHA-256 check (expected $want, got $got), so nothing was installed; download it again or report it at https://github.com/joelbrilliant/agent-memory/issues"
  say "$wheel matches its checksum"
  FROM="$TMP/$wheel"
}

# One line per tool from agent-memory connect's one JSON line, or the line itself when it isn't the shape this expects.
connect_summary() {
  case "$1" in *'"results": []'*) say "  no agent tools found"; return ;; esac
  rows="$(printf '%s\n' "$1" | tr '}' '\n' | sed -n 's/.*"harness": "\([^"]*\)".*"smoke": "\([^"]*\)".*"status": "\([^"]*\)".*/  \1: \3, smoke test \2/p')"
  if [ -n "$rows" ]; then say "$rows"; else say "  $1"; fi
}

if [ -n "$FROM" ]; then
  [ -f "$FROM" ] || die "no wheel at $FROM" 2
else
  fetch_wheel
fi

UV="$(command -v uv 2>/dev/null || true)"
if [ -n "$UV" ]; then
  found="$("$UV" --version 2>/dev/null | awk '{print $2}')"
  at_least "${found:-0.0.0}" "$UV_MIN" || UV=""
fi
if [ -z "$UV" ]; then
  command -v curl >/dev/null 2>&1 || die "uv isn't installed and curl isn't here to fetch it; install curl (Ubuntu: apt install curl ca-certificates) and run this again"
  say "Installing uv $UV_VERSION from astral.sh"
  curl -LsSf "https://astral.sh/uv/$UV_VERSION/install.sh" | env UV_NO_MODIFY_PATH=1 sh >/dev/null || die "uv didn't install"
  for candidate in "${XDG_BIN_HOME:-$HOME/.local/bin}/uv" "$HOME/.cargo/bin/uv"; do
    [ -x "$candidate" ] && UV="$candidate" && break
  done
  [ -n "$UV" ] || die "uv installed but can't be found"
fi

BIN="$("$UV" tool dir --bin)" || die "uv tool dir --bin failed"
existing="$(command -v agent-memory 2>/dev/null || true)"
if [ -n "$existing" ] && [ "$existing" != "$BIN/agent-memory" ]; then
  die "an agent-memory command is already installed at $existing and wasn't installed by uv; remove it, or put uv's $BIN first on PATH"
fi

say "Installing $FROM on uv's Python $PYTHON"
"$UV" tool install --managed-python --python "$PYTHON" "$FROM" >/dev/null || die "uv tool install failed"
"$UV" tool update-shell >/dev/null 2>&1 || true

if ! out="$("$BIN/agent-memory" --version 2>&1)"; then
  printf '%s\n' "$out" >&2
  exit 5
fi
say "$out"

# The tool finds uv's folder and the agent tools through these, whether or not uv's folder is on PATH yet.
UV_TOOL_BIN_DIR="$BIN"; export UV_TOOL_BIN_DIR
PATH="$BIN:$PATH"; export PATH

problems=""
if [ -n "$CONNECT" ]; then
  say ""
  say "Connecting agent memory to the agent tools found here:"
  code=0
  out="$("$BIN/agent-memory" connect all 2>&1)" || code=$?
  connect_summary "$out"
  if [ "$code" -eq 0 ]; then
    say "  undo: agent-memory connect all --remove"
  else
    problems="$problems connect"
  fi
fi
say ""
say "Indexing your past agent sessions (Claude Code, Codex, Grok, Hermes) once, into ~/.local/share/agent-memory on this machine only. This can take a minute."
"$BIN/agent-memory" session sync || problems="$problems session-sync"

say ""
if [ -n "$problems" ]; then
  say "Finished, but these steps failed:$problems. Nothing was rolled back. Fix what's printed above, then run the installer again: it upgrades the tool and keeps your data."
  exit 1
fi
say "Nothing outside your agent sessions is indexed until you list notes in ~/.config/agent-memory/corpus.txt and run: agent-memory ingest"
say "Restart your agent tools to pick up agent memory. To undo: agent-memory connect all --remove, then: uv tool uninstall agent-memory. Your index and sessions are in ~/.local/share/agent-memory."
