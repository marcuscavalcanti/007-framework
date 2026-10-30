"""Replay prompt interface hints: public signature lines the commit added or changed, never bodies; no model, no network."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import interface_hints

GIT_ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
KEEP = "def keep(a):\n    return a\n"
CHILD = ("def keep(a, b=None):\n    return a\n\n\ndef new_func(x, y=2):\n    return x + y\n\n\n"
         "class Box(Base):\n    def method(self, z):\n        return z\n\n\ndef _private(q):\n    return q\n")


class InterfaceHintsTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.repo = Path(scratch.name)
        self.git("init", "-q")
        self.parent = self.commit({"pkg/mod.py": KEEP})

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], env=GIT_ENV, check=True, capture_output=True).stdout.decode().strip()

    def commit(self, files):
        for path, text in files.items():
            (self.repo / path).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / path).write_text(text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "change")
        return self.git("rev-parse", "HEAD")

    def test_hints_are_public_signature_lines_of_given_sources_only(self):
        child = self.commit({"pkg/mod.py": CHILD, "tests/test_mod.py": "def test_box():\n    assert True\n"})
        self.assertEqual(interface_hints.hints(self.repo, self.parent, child, ["pkg/mod.py"]), [
            "pkg/mod.py: class Box(Base):", "pkg/mod.py: def keep(a, b=None):",
            "pkg/mod.py: def method(self, z):", "pkg/mod.py: def new_func(x, y=2):"])

    def test_multi_line_signature_is_joined_and_one_liner_body_never_pulls_following_lines(self):
        begin = KEEP + "\n\ndef begin(repo, task_id=None,\n          now=None, authority=None):\n    return 1\n"
        child = self.commit({"pkg/mod.py": begin})
        self.assertEqual(interface_hints.hints(self.repo, self.parent, child, ["pkg/mod.py"]),
                         ["pkg/mod.py: def begin(repo, task_id=None, now=None, authority=None):"])
        later = self.commit({"pkg/mod.py": begin + "\n\ndef one(x): return x\nLEAK = 1\n"})
        self.assertEqual(interface_hints.hints(self.repo, child, later, ["pkg/mod.py"]), ["pkg/mod.py: def one(x): return x"])

    def test_with_hints_appends_a_signature_block_only_when_there_are_hints(self):
        self.assertEqual(interface_hints.with_hints("msg", []), "msg")
        self.assertEqual(interface_hints.with_hints("msg", ["a.py: def f(x):", "a.py: class C:"]),
                         "msg\n\nInterface expected by the change (signatures only; implement the behaviour yourself):\n"
                         "- a.py: def f(x):\n- a.py: class C:")


if __name__ == "__main__":
    unittest.main()
