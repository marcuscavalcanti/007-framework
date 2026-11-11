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
    def test_ci_pushes_target_main_and_release_tags_while_all_pull_requests_run(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        triggers = workflow.split("on:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertEqual(triggers, "  push:\n    branches: [main]\n    tags: [\"v*\"]\n  pull_request:\n")
        self.assertIn("name: \"test (3.13) macOS\"", workflow)
        self.assertIn("      - name: Verify release manifest", workflow)

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
        self.env["GITHUB_EVENT_NAME"] = "push"
        self.env["GITHUB_SHA"] = self.git("rev-parse", "HEAD").stdout.strip()

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

    def test_checkout_fetches_the_tag_ref_explicitly(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        checkout = workflow.split("uses: actions/checkout@", 1)[1].split("- uses:", 1)[0]
        self.assertIn("ref: ${{ inputs.tag && format('refs/tags/{0}', inputs.tag) || github.ref }}", checkout)

    def test_tag_event_cannot_build_a_different_commit(self):
        self.env["GITHUB_SHA"] = "0" * 40
        self.assert_refused()

    def test_manual_recovery_archives_the_bound_tag_from_main(self):
        tag_object = self.git("rev-parse", "refs/tags/v1.2.3").stdout.strip()
        self.env.update(GITHUB_EVENT_NAME="workflow_dispatch", GITHUB_REF_NAME="main",
                        GITHUB_SHA="0" * 40, RELEASE_TAG="v1.2.3", EXPECTED_TAG_OBJECT=tag_object)
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("007-framework-1.2.3.tar.gz", (self.root / "outputs").read_text())

    def test_manual_recovery_refuses_missing_or_changed_tag_object(self):
        self.env.update(GITHUB_EVENT_NAME="workflow_dispatch", GITHUB_REF_NAME="main", RELEASE_TAG="v1.2.3")
        for tag_object in ("", "0" * 40):
            with self.subTest(tag_object=tag_object):
                self.env["EXPECTED_TAG_OBJECT"] = tag_object
                self.assert_refused()
