"""ingest.py: a rebuild that can't read a listed file keeps the committed index, and scratch and backup folders are
never indexed. Every name and note here is invented."""
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class IngestTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.notes = self.root / "notes"
        self.notes.mkdir()
        self.db = self.root / "index.db"
        (self.root / "corpus.txt").write_text(f"notes|{self.notes}/**/*.md\n", encoding="utf-8")

    def tearDown(self):
        for path in self.notes.rglob("*"):
            path.chmod(0o755)
        self.tempdir.cleanup()

    def ingest(self):
        env = {**os.environ, "AGENT_MEMORY_CORPUS": str(self.root / "corpus.txt"), "AGENT_MEMORY_DB": str(self.db),
               "AGENT_MEMORY_EXCLUDE": str(self.root / "exclude.txt")}
        return subprocess.run([sys.executable, str(ROOT / "ingest.py")], env=env, capture_output=True, text=True, timeout=60)

    def paths(self):
        con = sqlite3.connect(self.db)
        try:
            return sorted(Path(row[0]).relative_to(self.notes).as_posix() for row in con.execute("SELECT path FROM docs"))
        finally:
            con.close()

    def test_an_unreadable_file_keeps_the_committed_index(self):
        if os.geteuid() == 0:
            self.skipTest("root can read a file whatever its mode")
        (self.notes / "a.md").write_text("# A\n\nThe quokka rota changes on Fridays.\n", encoding="utf-8")
        locked = self.notes / "b.md"
        locked.write_text("# B\n\nThe wombat budget is due.\n", encoding="utf-8")
        self.assertEqual(self.ingest().returncode, 0)
        before = self.db.read_bytes()
        self.assertEqual(self.paths(), ["a.md", "b.md"])
        (self.notes / "c.md").write_text("# C\n\nA new note.\n", encoding="utf-8")
        locked.chmod(0)
        done = self.ingest()
        self.assertEqual(done.returncode, 1)
        self.assertIn("b.md", done.stderr)
        self.assertIn("existing index was kept", done.stderr)
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(self.paths(), ["a.md", "b.md"])
        self.assertEqual(sorted(path.name for path in self.root.iterdir() if path.name.startswith("index.db")), ["index.db"])
        locked.chmod(0o644)
        self.assertEqual(self.ingest().returncode, 0)
        self.assertEqual(self.paths(), ["a.md", "b.md", "c.md"])
        self.assertEqual(oct(self.db.stat().st_mode & 0o777), "0o600")

    def test_scratch_and_backup_folders_are_never_indexed(self):
        kept = self.notes / "keep.md"
        kept.write_text("# Keep\n\nA note that counts.\n", encoding="utf-8")
        for folder in (".scratch", "scratchpad-1", ".hermes/backups", ".hermes/migration-backups", ".hermes/profiles/work"):
            path = self.notes / folder / "noise.md"
            path.parent.mkdir(parents=True)
            path.write_text("# Noise\n\nA transient copy.\n", encoding="utf-8")
        done = self.ingest()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.paths(), ["keep.md"])
        self.assertIn("excluded-path: ", done.stdout)

    def test_a_fresh_ingest_with_nothing_listed_indexes_nothing(self):
        (self.root / "corpus.txt").write_text("# nothing listed\n", encoding="utf-8")
        done = self.ingest()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.paths(), [])


if __name__ == "__main__":
    unittest.main()
