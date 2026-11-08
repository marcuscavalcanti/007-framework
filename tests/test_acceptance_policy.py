"""Configured acceptance environment and wrapper controls; no provider calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from types import MappingProxyType

import effort_lab
import replay_eval
import test_dataset_admission as fixtures


class AcceptancePolicyTests(unittest.TestCase):
    def test_explicit_mapping_objects_remain_valid_without_inheritance(self):
        checks, accepted = replay_eval.acceptance({"acceptance": [[sys.executable, "-c",
            "import os; assert os.environ['SYNTHETIC_ONLY']=='yes'"]]}, Path.cwd(),
            env=MappingProxyType({"SYNTHETIC_ONLY": "yes"}))
        self.assertTrue(accepted)
        self.assertEqual(checks[0]["exit"], 0)

    def test_collect_preserves_an_explicit_environment_without_parent_variables(self):
        with tempfile.TemporaryDirectory() as temporary:
            tree = Path(temporary)
            (tree / "test_fixture.py").write_text("import unittest\nclass T(unittest.TestCase):\n def test_ok(self): pass\n")
            real_run = subprocess.run
            with mock.patch.dict(os.environ, {"PARENT-ONLY-SYNTHETIC": "must-not-reach-child"}, clear=True), \
                    mock.patch.object(effort_lab.subprocess, "run", wraps=real_run) as launched:
                result = effort_lab.collect(tree, {"adapter": "unittest", "tests": "test_fixture.py"}, None, {})
                self.assertTrue(result)
                self.assertFalse("PARENT-ONLY-SYNTHETIC" in launched.call_args.kwargs["env"])

    def test_collect_keeps_the_legacy_inherited_environment_when_omitted(self):
        with tempfile.TemporaryDirectory() as temporary:
            tree = Path(temporary)
            (tree / "test_fixture.py").write_text("import unittest\nclass T(unittest.TestCase):\n def test_ok(self): pass\n")
            real_run = subprocess.run
            with mock.patch.dict(os.environ, {"PARENT-ONLY-SYNTHETIC": "intentional-host-mode"}, clear=True), \
                    mock.patch.object(effort_lab.subprocess, "run", wraps=real_run) as launched:
                self.assertTrue(effort_lab.collect(tree, {"adapter": "unittest", "tests": "test_fixture.py"}, None, None))
                self.assertEqual(launched.call_args.kwargs["env"]["PARENT-ONLY-SYNTHETIC"], "intentional-host-mode")

    def test_recheck_honors_the_same_explicit_environment_and_wrapper(self):
        fixture = fixtures.RetainedExecutionTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        cell = fixture.execute()
        marker = fixture.root / "wrapper-count"
        wrapper = ("import os,sys; from pathlib import Path; "
                   "assert 'PARENT-ONLY-SYNTHETIC' not in os.environ; assert os.environ['ONLY_ALLOWED']=='yes'; "
                   "p=Path(sys.argv[1]); p.write_text(p.read_text()+'x' if p.exists() else 'x'); "
                   "os.execv(sys.argv[2], sys.argv[2:])")
        policy = {"acceptance_env": {"ONLY_ALLOWED": "yes"},
                  "acceptance_sandbox": [sys.executable, "-c", wrapper, str(marker)]}
        task = {"project_id": "project", "id": cell["task_id"], "replay_ref": cell["replay_ref"]}
        with mock.patch.dict(os.environ, {"PARENT-ONLY-SYNTHETIC": "must-not-reach-child"}, clear=True):
            result = replay_eval.recheck_retained_case(task, fixture.output / "cases", acceptance_config=policy)
        self.assertTrue(result["replay_ready"], result)
        self.assertEqual(result["oracle_exits"], [[0], [0]])
        self.assertEqual(marker.read_text(), "xx")
