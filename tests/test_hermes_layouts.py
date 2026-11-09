"""Hermes session discovery across both state.db layouts. Older Hermes put the surface (cli, telegram...) in
sessions.source. Current Hermes writes source 'local' and the surface in a created_source column, and a file migrated
from the older layout keeps its old rows with the surface in source and no created_source."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from session_adapters import SessionRoots, discover_hermes  # noqa: E402
from session_continuity import recall_sessions, sync_index  # noqa: E402

# (session id, source, created_source, title, what the person said)
OLDER_LAYOUT = (
    ("old-human", "telegram", None, "Rollout chat", "oldercanary rollout plan for the Brisbane office"),
    ("old-cron", "cron", None, "Nightly", "oldercron noise must never be indexed"),
)
CURRENT_LAYOUT = (
    ("new-human", "local", "cli", "", "currentcanary rollout plan for the Brisbane office"),
    ("new-cron", "local", "cron", "Nightly", "currentcron noise must never be indexed"),
    ("migrated-human", "telegram", None, "Rollout chat", "migratedcanary rollout plan for the Brisbane office"),
)


def write_state_db(path, rows, *, created_source_column):
    """The two tables the index reads. Without the created_source column (the older layout) that value is dropped."""
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT NOT NULL, %stitle TEXT, cwd TEXT, "
        "started_at REAL NOT NULL, ended_at REAL);\n"
        "CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, "
        "role TEXT NOT NULL, content TEXT, timestamp REAL NOT NULL);"
        % ("created_source TEXT, " if created_source_column else "")
    )
    for n, (session_id, source, created_source, title, said) in enumerate(rows):
        started = 1000.0 + 100 * n
        values = [session_id, source]
        if created_source_column:
            values.append(created_source)
        values += [title, "/work", started, None]
        conn.execute("INSERT INTO sessions VALUES (%s)" % ",".join("?" * len(values)), values)
        conn.executemany(
            "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            [(session_id, "user", said, started + 1), (session_id, "assistant", "Noted.", started + 2)],
        )
    conn.commit()
    conn.close()


class HermesLayoutsTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        for name in ("claude", "codex", "grok"):
            (self.root / name).mkdir()
        self.older = self.root / "older-state.db"
        self.current = self.root / "current-state.db"
        write_state_db(self.older, OLDER_LAYOUT, created_source_column=False)
        write_state_db(self.current, CURRENT_LAYOUT, created_source_column=True)

    def tearDown(self):
        self.tempdir.cleanup()

    def roots(self, hermes_db):
        return SessionRoots(hermes_db=hermes_db, claude_root=self.root / "claude",
                            codex_root=self.root / "codex", grok_root=self.root / "grok")

    def test_discovery_takes_the_human_sessions_of_both_layouts_and_never_cron(self):
        older = {d.session_id: d for d in discover_hermes(self.older, strict=True)}
        self.assertEqual(sorted(older), ["old-human"])
        self.assertEqual(older["old-human"].title, "Rollout chat")
        current = {d.session_id: d for d in discover_hermes(self.current, strict=True)}
        self.assertEqual(sorted(current), ["migrated-human", "new-human"])
        # An untitled session is named after its surface, not after 'local'.
        self.assertEqual(current["new-human"].title, "cli session")

    def test_sync_index_indexes_the_human_sessions_of_both_layouts(self):
        cases = (
            ("older", self.older, {"oldercanary": "old-human"}, "oldercron"),
            ("current", self.current, {"currentcanary": "new-human", "migratedcanary": "migrated-human"}, "currentcron"),
        )
        for name, hermes_db, canaries, cron_canary in cases:
            with self.subTest(layout=name):
                session_db = self.root / ("%s-sessions.db" % name)
                result = sync_index(session_db, self.roots(hermes_db))
                self.assertEqual(result.source_errors, ())
                self.assertEqual(result.sessions_by_harness.get("hermes"), len(canaries))
                conn = sqlite3.connect(session_db)
                indexed = sorted(row[0] for row in conn.execute(
                    "SELECT session_id FROM session_sources WHERE harness='hermes'"))
                conn.close()
                self.assertEqual(indexed, sorted(canaries.values()))
                for canary, session_id in canaries.items():
                    hits = recall_sessions(session_db, canary, sync=False)
                    self.assertEqual([hit.session_id for hit in hits], [session_id])
                self.assertEqual(recall_sessions(session_db, cron_canary, sync=False), [])


if __name__ == "__main__":
    unittest.main()
