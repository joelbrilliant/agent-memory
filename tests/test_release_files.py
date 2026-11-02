"""The files a release carries: licence, notice, author, version, and the LongMemEval comparison running from the
package on a tiny invented dataset."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_memory import __version__  # noqa: E402


class ReleaseFilesTest(unittest.TestCase):
    def test_licence_notice_and_author_name_the_author_and_nobody_else(self):
        licence = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("Apache License", licence)
        self.assertIn("   Copyright 2026 Joel Brilliant\n", licence)
        self.assertNotIn("[yyyy]", licence)
        self.assertEqual((ROOT / "NOTICE").read_text(encoding="utf-8").splitlines(),
                         ["agent-memory", "Copyright 2026 Joel Brilliant", "", "Built by Joel Brilliant, with the help of my agents."])
        project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('authors = [{name = "Joel Brilliant"}]', project)
        self.assertIn('license = "Apache-2.0"', project)
        self.assertNotRegex(project, r"@")
        self.assertIn(f'version = "{__version__}"', project)

    def test_the_readme_opens_with_the_one_command_and_the_prompt_and_credits_the_author(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        command = "curl -LsSf https://github.com/joelbrilliant/agent-memory/releases/latest/download/install.sh | sh"
        self.assertIn(command, readme)
        self.assertLess(readme.index(command), readme.index("Or tell your agent"))
        self.assertIn("Built by Joel Brilliant", readme)
        self.assertIn("https://github.com/joelbrilliant/agent-si", readme)
        self.assertIn("AGENT-INSTALL.md", readme)
        for old in ("template", "Use this template", "agent-memory-kit", "gh repo create", "git clone"):
            self.assertNotIn(old, readme)
        agent = (ROOT / "AGENT-INSTALL.md").read_text(encoding="utf-8")
        for old in ("agent-memory-kit", "gh repo create", "git clone", "template"):
            self.assertNotIn(old, agent)

    def test_the_longmemeval_comparison_runs_from_the_package(self):
        entry = {
            "question_id": "q1", "question_type": "single-session-user", "question": "which quokka rota changed",
            "answer_session_ids": ["s2"], "haystack_session_ids": ["s1", "s2"],
            "haystack_sessions": [
                [{"role": "user", "content": "talking about wombat budgets"}, {"role": "assistant", "content": "ok"}],
                [{"role": "user", "content": "the quokka rota changed on Friday"}, {"role": "assistant", "content": "noted"}],
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data.json"
            data.write_text(json.dumps([entry]), encoding="utf-8")
            done = subprocess.run([sys.executable, "-I", str(ROOT / "benchmarks" / "longmemeval_compare.py"), str(data)],
                                  capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        summary = json.loads(done.stdout)
        self.assertEqual(summary["questions"], 1)
        for mode in ("today", "per_message", "any_word"):
            self.assertEqual(summary["recall_any"][mode]["@5"], 1.0, mode)

    def test_no_results_file_of_private_origin_ships(self):
        self.assertEqual(sorted(path.name for path in (ROOT / "benchmarks").iterdir() if path.suffix != ".pyc" and path.is_file()),
                         ["README.md", "longmemeval_compare.py"])
        text = (ROOT / "benchmarks" / "longmemeval_compare.py").read_text(encoding="utf-8")
        self.assertRegex(text, r"huggingface\.co/datasets/xiaowu0162/longmemeval-cleaned")
        self.assertIsNone(re.search(r"/Users/|~/Projects|\.hermes/", text))


if __name__ == "__main__":
    unittest.main()
