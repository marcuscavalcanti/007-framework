"""Exercise the tag workflow's source recipe in a local synthetic repository."""

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReleaseWorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="007-release-fixture-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.env = {"PATH": os.environ["PATH"], "HOME": str(self.root), "RUNNER_TEMP": str(self.root),
                    "GITHUB_OUTPUT": str(self.root / "outputs"), "GITHUB_REF_NAME": "v1.2.3",
                    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "LANG": "C"}
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        self.recipe = textwrap.dedent(workflow.split("        run: |\n", 1)[1].split("      - name:", 1)[0])
        self.git("init", "-q")
        (self.repo / "bin").mkdir()
        (self.repo / "bin/007").write_text("print('007 1.2.3')\n")
        (self.repo / "file with spaces.txt").write_text("synthetic source\n")
        evidence = self.repo / "evidence/v1.2.3"
        evidence.mkdir(parents=True)
        (evidence / "release-evidence.md").write_text("Synthetic recipe qualification only\n")
        files = sorted(path for path in self.repo.rglob("*") if path.is_file() and ".git" not in path.parts)
        (evidence / "manifest.sha256").write_text("".join(
            hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.relative_to(self.repo).as_posix() + "\n"
            for path in files))
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "tag", "-a", "v1.2.3", "-m", "fixture")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, env=self.env, check=True, capture_output=True, text=True, timeout=15)

    def execute(self):
        return subprocess.run(["bash", "-c", self.recipe], cwd=self.repo, env=self.env, capture_output=True, text=True, timeout=30)

    def assert_refused(self):
        result = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "outputs").exists())
        self.assertEqual(list(self.root.glob("007-distribution.*")), [])

    def test_annotated_matching_tag_produces_verified_source_and_checksum(self):
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        outputs = dict(line.split("=", 1) for line in (self.root / "outputs").read_text().splitlines())
        archive = Path(outputs["archive"])
        self.assertEqual(archive.parent, Path(outputs["directory"]))
        self.assertEqual(sorted(path.name for path in archive.parent.iterdir()), ["007-framework-1.2.3.tar.gz", "SHA256SUMS.txt"])
        self.assertEqual((archive.parent / "SHA256SUMS.txt").read_text(),
                         hashlib.sha256(archive.read_bytes()).hexdigest() + "  " + archive.name + "\n")

    def test_lightweight_tag_is_refused(self):
        self.git("tag", "-d", "v1.2.3")
        self.git("tag", "v1.2.3")
        self.assert_refused()

    def test_mismatched_version_is_refused(self):
        (self.repo / "bin/007").write_text("print('007 9.9.9')\n")
        self.assert_refused()

    def test_corrupt_source_is_refused(self):
        (self.repo / "file with spaces.txt").write_text("corrupted fixture\n")
        self.assert_refused()

    def test_unsafe_tag_name_is_refused(self):
        self.env["GITHUB_REF_NAME"] = "v1.2.3/extra"
        self.assert_refused()
