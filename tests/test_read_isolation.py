"""1.11.0 item 3c: blind hardening. Orphan `.blind/` receipts are counted, `replay_eval run` names cells by salted token, each
cell asks its CLI to deny reads of protected paths where the set opts in, and a retained stream that touched one marks the cell
contaminated and invalid. A fake agent and synthetic streams only: no model, no vendor CLI."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import effort_lab as lab
import native_runner
import replay_eval
from test_effort_lab import CAPTURE_AGENT, FAKE_AGENT, GOOD, PARTIAL, git, synthetic, synthetic_environ

# FAKE_AGENT after a Claude-shaped stream of its tool calls, written to {stream_copy}. With LAB_SNOOP set, the `medium` arm also
# reads the run's manifest, lists `.blind/` and greps the output directory: the run directory is two levels above its receipt.
STREAM_AGENT = """import json, os, sys
cwd, receipt, effort, prompt, good, partial, stream = sys.argv[1:8]
out = os.path.dirname(os.path.dirname(receipt))
calls = [{"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": cwd + "/calc.py"}},
         {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "python -m unittest discover -s tests"}}]
if os.environ.get("LAB_SNOOP") and effort == "medium":
    calls += [{"type": "tool_use", "id": "t3", "name": "Read", "input": {"file_path": out + "/run-manifest.json"}},
              {"type": "tool_use", "id": "t4", "name": "Bash", "input": {"command": "ls -la " + out + "/.blind"}},
              {"type": "tool_use", "id": "t5", "name": "Grep", "input": {"pattern": "accepted", "path": out}}]
with open(stream, "w") as handle:
    for block in calls:
        handle.write(json.dumps({"type": "assistant", "message": {"content": [block]}}) + "\\n")
        handle.write(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": block["id"], "content": out}]}}) + "\\n")
""" + FAKE_AGENT

# Review #11: an agent that tampers with where its controller promotes its artifacts. `mode` and `path` come after {stream_copy}:
# planted, a clean-looking stream at the cell's own final name (path) and no fresh one; symlink, its stream a link to a clean file
# outside the results (path) while it reads the run.
TAMPER_AGENT = """import json, os, sys
stream, mode, path = sys.argv[7:10]
clean = json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "x"}}]}}) + "\\n"
if mode == "planted":
    open(path, "w").write(clean)
elif mode == "symlink":
    open(path, "w").write(clean)
    os.symlink(path, stream)
""" + FAKE_AGENT


class StreamScan(unittest.TestCase):
    """The detector alone, on synthetic Claude and Codex streams."""
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.out = self.root / "x" / "out"
        self.out.mkdir(parents=True)
        self.work = self.root / "work"
        self.work.mkdir()
        self.protected = [("run-directory", str(self.out))]

    def scan(self, *rows, raw=b""):
        stream = self.root / "stream.jsonl"
        stream.write_bytes(b"".join(json.dumps(r).encode() + b"\n" for r in rows) + raw)
        return replay_eval.scan_stream(stream, self.protected, str(self.work))

    @staticmethod
    def claude(name, **arguments):
        return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": name + json.dumps(arguments), "name": name, "input": arguments}]}}

    @staticmethod
    def codex(command, **extra):
        return {"type": "item.completed", "item": {"id": command, "type": "command_execution", "command": command, **extra}}

    def test_each_tool_that_names_a_protected_path_is_a_hit(self):
        out = str(self.out)
        relative = os.path.relpath(out, self.work)
        for label, row in (("read", self.claude("Read", file_path=out + "/run-manifest.json")),
                           ("grep", self.claude("Grep", pattern="x", path=out)),
                           ("glob", self.claude("Glob", pattern=out + "/**/*.json")),
                           ("bash", self.claude("Bash", command=f"cat '{out}/.blind/1.runner.json' | head")),
                           ("claude-absolute-rule", self.claude("Bash", command=f"echo //{out.lstrip('/')}/x")),
                           ("relative", self.claude("Bash", command=f"cat {relative}/dispatch.jsonl")),
                           ("case", self.claude("Read", file_path=out.upper() + "/A.JSON")),
                           ("codex", self.codex(f"/bin/zsh -lc 'ls {out}'")),
                           ("codex-file", {"type": "item.started", "item": {"id": "f", "type": "file_change",
                                                                             "changes": [{"path": out + "/x.json", "kind": "add"}]}})):
            with self.subTest(label=label):
                found = self.scan(row)
                self.assertEqual(found["status"], "contaminated", found)
                self.assertEqual([h["protected"] for h in found["hits"]], ["run-directory"])

    def test_home_shorthand_is_expanded(self):
        plugins = Path.home() / "scan-probe-plugins"
        self.protected = [("plugin-copy", str(plugins))]
        self.assertEqual(self.scan(self.claude("Bash", command="grep -r answer ~/scan-probe-plugins/cache"))["status"], "contaminated")

    def test_what_is_not_a_call_or_not_the_path_is_clean(self):
        out = str(self.out)
        found = self.scan(
            self.claude("Read", file_path=str(self.root / "a" / "x" / "out" / "f")),  # a longer path ending the same way
            self.claude("Read", file_path=out + "side/f"),  # a sibling whose name starts the same
            self.codex("go test ./...", aggregated_output=f"wrote {out}/x"),  # a path in a command's output is no access
            {"type": "item.completed", "item": {"id": "m", "type": "agent_message", "text": f"I will not read {out}"}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": f"thinking about {out}"}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "content": out}]}},
            raw=b'{"type": "assistant", "message": {"content": [\n')  # a torn last line: counted, and the scan is incomplete
        self.assertEqual((found["status"], found["hits"], found["tool_calls"], found["unparsed_lines"]), ("incomplete", [], 3, 1))

    def test_an_empty_malformed_or_hostile_stream_is_never_clean(self):
        """Review #12: an empty or wholly malformed stream read `clean`; a deeply nested line or a call id that is a list aborted
        the scan; a line of any length was read whole."""
        out = str(self.out)
        self.assertEqual(self.scan()["status"], "unscanned")
        self.assertEqual(self.scan()["reason"], "empty-stream")
        self.assertEqual(self.scan(raw=b"not json\n{torn")["status"], "unscanned")
        deep = (b'{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "d", "name": "Read", "input": '
                + b'{"a": ' * 5000 + b'"x"' + b"}" * 5000 + b"}]}}\n")  # nested past the recursion limit
        listed = {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": ["a"], "name": "Read", "input": {"file_path": out + "/x"}}]}}
        found = self.scan(listed, self.claude("Read", file_path="ok"), raw=deep)
        self.assertEqual((found["status"], found["tool_calls"], found["unparsed_lines"]), ("contaminated", 2, 1))
        with mock.patch.object(replay_eval, "MAX_SCAN_LINE", 400):  # a short limit; the middle line is far longer, the others far shorter
            long = self.scan(self.claude("Read", file_path="ok"), self.claude("Bash", command="x" * 2000), self.claude("Read", file_path="z"))
        self.assertEqual((long["status"], long["tool_calls"], long["unparsed_lines"]), ("incomplete", 2, 1))

    def test_no_retained_stream_is_unscanned(self):
        self.assertEqual(replay_eval.scan_stream(None, self.protected, str(self.work))["status"], "unscanned")
        self.assertEqual(replay_eval.scan_stream(self.root / "absent.jsonl", self.protected, str(self.work))["status"], "unscanned")


class DenyRules(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)

    def test_claude_settings_pass_native_runners_own_check_and_codex_profile_its_option_list(self):
        paths = [str(self.root / "out"), str(self.root / "set dir")]
        text, digest = replay_eval.claude_read_settings(paths)
        value = json.loads(text)
        self.assertEqual(set(value), {"permissions", "sandbox"})
        for path in paths:
            self.assertIn(f"Read(/{path}/**)", value["permissions"]["deny"])
            self.assertIn(f"Read(/{path})", value["permissions"]["deny"])
        self.assertEqual(value["sandbox"]["filesystem"]["denyRead"], paths)
        self.assertTrue(value["sandbox"]["failIfUnavailable"])
        self.assertEqual(native_runner.claude_settings("claude", ["claude", "--settings", text]), digest)
        profile = replay_eval.codex_read_profile(paths)
        self.assertTrue(profile.startswith(f'permissions.{replay_eval.CODEX_READ_PROFILE}={{extends=":workspace", filesystem={{'))
        self.assertIn(json.dumps(paths[1]) + '="deny"', profile)
        command = ["codex", "exec", "--json", "--ignore-user-config", "-c", profile,
                   "-c", f'default_permissions="{replay_eval.CODEX_READ_PROFILE}"', "-m", "m", "-c", 'model_reasoning_effort="high"', "-"]
        self.assertEqual(native_runner.native_request("codex", command), (["m"], ["high"], ["openai"]))

    def test_protected_paths_refuse_home_and_keep_only_existing_ones(self):
        out = self.root / "out"
        out.mkdir()
        with mock.patch.dict(os.environ, {"HOME": str(self.root / "home")}):
            (self.root / "home" / ".claude" / "plugins").mkdir(parents=True)
            found = replay_eval.protected_paths({"repos": {"r": str(self.root / "missing")}}, {}, out)
            self.assertEqual([label for label, _ in found], ["run-directory", "plugin-copy"])
            for bad in (str(self.root / "home"), str(self.root), "/"):
                with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "HOME or the filesystem root"):
                    replay_eval.protected_paths({"read_protect": [("set-directory", bad)]}, {}, out)

    def test_the_mode_comes_from_the_placeholders_the_set_carries(self):
        self.assertEqual(replay_eval.read_isolation_mode(["agent", "{cwd}"]), "unenforced")
        self.assertEqual(replay_eval.read_isolation_mode(["x", "--settings", "{read_isolation_claude_settings}"]), "claude-settings")
        self.assertEqual(replay_eval.read_isolation_mode(["x", "-c", "{read_isolation_codex_profile}"]), "codex-profile")


class LabIsolation(unittest.TestCase):
    """End to end through `007 lab run`, `report` and `status`, with a synthetic repository and a fake agent."""
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        synthetic(self.repo)
        self.agent = self.root / "agent.py"
        self.agent.write_text(STREAM_AGENT)
        self.config = {"repo": str(self.repo), "adapter": "unittest", "tests": "tests/test_*.py", "as_of": "2026-03-01T00:00:00+00:00", "seed": 7,
                       "want": 1, "min_source_lines": 1, "min_message": 50,
                       "agent_command": [sys.executable, "-I", str(self.agent), "{cwd}", "{runner_receipt}", "{effort}", "{prompt_file}", GOOD, PARTIAL,
                                         "{stream_copy}"],
                       "arms": {e: {"provider": "none", "model": "none", "effort": e, "doctrine": ""} for e in ("medium", "high")},
                       "compare": {"candidate": "medium", "reference": "high"}, "served_identity": "requested-only"}

    def mined(self, **changes):
        out = self.root / "lab"
        lab.mine({**self.config, **changes}, out, 2)
        lab.sensitivity(out / "replay-set.json", 2)
        return out / "replay-set.json"

    def run_lab(self, path, results, replicates=2, **options):
        return lab.run(path, results, replicates=replicates, jobs=2, max_calls=99, max_usd=99, stop_usd=1, max_invalid=99, **options)

    def test_an_agent_that_reads_the_run_is_contaminated_invalid_and_counted(self):
        path, results = self.mined(), self.root / "results"
        with mock.patch.dict(os.environ, {"LAB_SNOOP": "1"}):
            state = self.run_lab(path, results)
        self.assertIsNone(state["stop"])
        cells = {c["cell"]: c for c in lab.load_cells(results)}
        tasks = len(json.loads(path.read_text())["tasks"])
        self.assertEqual(state["invalid"], 2 * tasks)  # counted against --max-invalid like any invalid cell
        for cid, cell in cells.items():
            snooped = cell["arm"] == "medium"
            self.assertEqual(cell["contamination"]["status"], "contaminated" if snooped else "clean", cid)
            self.assertEqual(cell["valid"], not snooped)
            self.assertEqual(cell["read_isolation"], "unenforced")
            if snooped:
                self.assertEqual((cell["failure_class"], cell["accepted"]), ("contaminated", False))
                self.assertEqual(cell["contamination"]["hits"], [{"protected": "run-directory", "tools": ["Bash", "Grep", "Read"]}])
        # the invalid limit stops a run whose agent keeps reading the run
        again = self.root / "again"
        with mock.patch.dict(os.environ, {"LAB_SNOOP": "1"}):
            stopped = lab.run(path, again, replicates=2, jobs=1, max_calls=99, max_usd=99, stop_usd=1, max_invalid=1)
        self.assertEqual(stopped["stop"], "invalid-budget")
        status = json.dumps(lab.status(path, results))
        self.assertNotRegex(status, r"(?i)medium|high")
        pooled = lab.status(path, results)["read_isolation"]
        self.assertEqual(pooled["contamination"], {"clean": 2 * tasks, "contaminated": 2 * tasks, "incomplete": 0, "unscanned": 0, "unrecorded": 0})
        self.assertNotIn("contaminated_cells", pooled)

    def test_contamination_shows_in_the_report_per_arm_and_pooled(self):
        path, results = self.mined(), self.root / "results"
        with mock.patch.dict(os.environ, {"LAB_SNOOP": "1"}):
            self.run_lab(path, results, replicates=1)
        self.run_lab(path, results, replicates=2)  # a resume with a clean agent: medium now has valid cells
        report = lab.report(path, results, None)
        tasks = len(json.loads(path.read_text())["tasks"])
        self.assertEqual(report["read_isolation"]["contamination"]["contaminated"], tasks)
        self.assertEqual(len(report["read_isolation"]["contaminated_cells"]), tasks)
        self.assertTrue(all(c.endswith("-r01-medium") for c in report["read_isolation"]["contaminated_cells"]))
        self.assertEqual(report["arm_accounting"]["arms"]["medium"]["invalid"], {"contaminated": tasks})
        self.assertEqual(report["arm_accounting"]["arms"]["high"]["invalid"], {})
        text = (results / "report.md").read_text()
        self.assertIn(f"**{tasks} contaminated cells read a protected path and are invalid**", text)
        self.assertIn("contaminated", text.split("- **Cells, `medium`:**")[1].splitlines()[0])

    def test_a_clean_agent_is_not_marked(self):
        path, results = self.mined(), self.root / "results"
        self.assertIsNone(self.run_lab(path, results)["stop"])
        cells = lab.load_cells(results)
        self.assertTrue(cells and all(c["valid"] and c["contamination"]["status"] == "clean" for c in cells))
        self.assertTrue(all(c["contamination"]["tool_calls"] == 2 for c in cells))
        report = lab.report(path, results, None)
        self.assertEqual(report["read_isolation"]["contaminated_cells"], [])
        self.assertIn("- **Read isolation:** asked of the CLI: unenforced", (results / "report.md").read_text())

    def test_deny_rules_reach_the_claude_arm_and_unenforced_is_recorded_without_them(self):
        """The Claude placeholders put the run's protected paths in the argv, as settings native_runner admits; a set without any
        records `unenforced` in every cell, never silently; the Codex placeholder records its own mode."""
        (self.root / "agent.py").write_text(CAPTURE_AGENT)
        capture = self.root / "capture"
        capture.mkdir()
        command = [sys.executable, "-I", str(self.root / "agent.py"), "{cwd}", "{runner_receipt}", "{effort}", "{prompt_file}", GOOD, PARTIAL]
        cases = (("claude", command + ["--settings", "{read_isolation_claude_settings}", "--settings-sha256", "{read_isolation_claude_settings_sha256}"],
                  "claude-settings"),
                 ("codex", command + ["-c", "{read_isolation_codex_profile}"], "codex-profile"),
                 ("plain", command, "unenforced"))
        for name, agent_command, mode in cases:
            with self.subTest(name=name):
                out = self.root / f"lab-{name}"
                lab.mine({**self.config, "agent_command": agent_command}, out, 2)
                lab.sensitivity(out / "replay-set.json", 2)
                results = self.root / f"results-{name}"
                for stale in capture.iterdir():
                    stale.unlink()
                with mock.patch.dict(os.environ, synthetic_environ(self.root, LAB_CAPTURE=str(capture)), clear=True):
                    self.assertIsNone(self.run_lab(out / "replay-set.json", results, replicates=1)["stop"])
                cells = lab.load_cells(results)
                self.assertEqual({c["read_isolation"] for c in cells}, {mode})
                self.assertEqual({c["contamination"]["status"] for c in cells}, {"unscanned"})  # no {stream_copy}: nothing to scan
                argvs = [json.loads(p.read_text())["argv"] for p in capture.iterdir()]
                self.assertEqual(len(argvs), len(cells))
                expected = {str(results.absolute()), str(out.resolve()), str(self.repo.absolute())}
                for argv in argvs:
                    if name == "claude":
                        text, digest = argv[argv.index("--settings") + 1], argv[argv.index("--settings-sha256") + 1]
                        value = json.loads(text)
                        self.assertEqual(native_runner.claude_settings("claude", ["claude", "--settings", text]), digest)
                        self.assertLessEqual(expected, set(value["sandbox"]["filesystem"]["denyRead"]))
                        self.assertLessEqual({f"Read(/{p}/**)" for p in expected}, set(value["permissions"]["deny"]))
                        self.assertFalse(any(Path(argv[1]).resolve().is_relative_to(p) for p in value["sandbox"]["filesystem"]["denyRead"]))
                    elif name == "codex":
                        profile = argv[-1]
                        self.assertTrue(profile.startswith("permissions.lab_read_isolation="))
                        for p in expected:
                            self.assertIn(json.dumps(p) + '="deny"', profile)
                    else:
                        self.assertFalse(any("read_isolation" in part or "deny" in part for part in argv))

    def test_a_workspace_inside_a_protected_path_is_refused_before_the_agent(self):
        path = self.mined()
        config = json.loads(path.read_text())
        # the refusal guards deny rules: the cell asks its CLI for them (without, see test_layout_refusals_apply_only_when_prevention_is_asked)
        config["agent_command"] = config["agent_command"] + ["--settings", "{read_isolation_claude_settings}"]
        output = self.root / "inside"
        output.mkdir()
        real = tempfile.mkdtemp

        def inside(suffix=None, prefix=None, dir=None):  # the cell's workspace only, as if TMPDIR were the output directory
            return real(suffix, prefix, output if prefix and prefix.startswith("007-") and "acceptance" not in prefix else dir)
        with mock.patch.object(replay_eval.tempfile, "mkdtemp", side_effect=inside):
            with self.assertRaisesRegex(RuntimeError, "inside a protected path"):
                replay_eval.execute_cell(config, config["tasks"][0], "high", 1, output, 60)
        self.assertEqual([p.name for p in output.iterdir()], [])

    def tamper(self, mode, path):
        """One blinded cell run by TAMPER_AGENT through execute_cell: (output directory, cell id, the call's outcome)."""
        config = json.loads(self.mined().read_text())
        config.update(blind_salt="0" * 32, agent_command=[sys.executable, "-I", str(self.root / "tamper.py"), "{cwd}", "{runner_receipt}",
                                                          "{effort}", "{prompt_file}", GOOD, PARTIAL, "{stream_copy}", mode, str(path)])
        (self.root / "tamper.py").write_text(TAMPER_AGENT)
        output = self.root / f"out-{mode}"
        output.mkdir(exist_ok=True)
        task = config["tasks"][0]
        try:
            return output, replay_eval.cell_id(task, "high", 1), replay_eval.execute_cell(config, task, "high", 1, output, 60)
        except RuntimeError as error:
            return output, replay_eval.cell_id(task, "high", 1), error

    def test_promotion_never_replaces_follows_a_link_or_scans_another_attempts_stream(self):
        """Review #11: in token mode the stream's final name was not checked before the agent's files were renamed onto it, a
        staged symlink was promoted and followed, and with no fresh stream a file already at the final name was scanned."""
        config = json.loads(self.mined().read_text())
        cid = replay_eval.cell_id(config["tasks"][0], "high", 1)
        output, _, planted = self.tamper("planted", self.root / "out-planted" / f"{cid}.stream.jsonl")
        self.assertIsInstance(planted, RuntimeError)  # a file this attempt did not create is never read as its stream
        self.assertIn("appeared", str(planted))
        self.assertFalse((output / f"{cid}.json").exists())
        outside = self.root / "outside.jsonl"
        output, _, linked = self.tamper("symlink", outside)
        self.assertIsInstance(linked, RuntimeError)
        self.assertIn("not a regular file", str(linked))
        self.assertFalse((output / f"{cid}.stream.jsonl").is_symlink())
        self.assertTrue(outside.is_file())  # the link is dropped, never its target
        # a `.blind` that is a link would send every agent's files elsewhere: refused before the agent runs
        output = self.root / "out-linked-blind"
        output.mkdir()
        (self.root / "elsewhere").mkdir()
        (output / ".blind").symlink_to(self.root / "elsewhere")
        config.update(blind_salt="0" * 32)
        with self.assertRaisesRegex(RuntimeError, "not a directory"):
            replay_eval.execute_cell(config, config["tasks"][0], "high", 1, output, 60)
        self.assertEqual(list((self.root / "elsewhere").iterdir()), [])
        # an honest agent still promotes both files, and its own stream is the one scanned
        output, _, row = self.tamper("honest", self.root / "unused")
        self.assertEqual(row["contamination"]["status"], "unscanned")  # TAMPER_AGENT writes no stream when honest
        self.assertTrue((output / f"{cid}.runner.json").is_file())
        self.assertEqual(replay_eval.blind_files(output), [])

    def test_a_sealed_salt_whose_tokens_collide_stops_before_any_dispatch(self):
        path, results = self.mined(), self.root / "results"
        self.assertIsNone(self.run_lab(path, results, replicates=1)["stop"])
        with mock.patch.object(replay_eval, "blind_token", return_value="0" * 16):  # every cell, one staging name
            state = self.run_lab(path, results, replicates=2)
        self.assertEqual((state["stop"], state["calls"]), ("blind-token-collision", 0))
        with mock.patch.object(replay_eval, "blind_token", return_value="0" * 16), self.assertRaisesRegex(ValueError, "own token"):
            replay_eval.unique_salt(["a", "b"])

    def test_layout_refusals_apply_only_when_prevention_is_asked(self):
        """Review #13: a protected path that is HOME, or one holding the workspace, was refused for every cell, even one that asks
        its CLI to deny nothing; those cells became controller errors and spent the invalid budget."""
        config = json.loads(self.mined().read_text())
        home = self.root / "home"
        home.mkdir()
        config["read_protect"] = [("too-wide", str(home))]
        task = config["tasks"][0]
        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            output = self.root / "plain-out"
            output.mkdir()
            row = replay_eval.execute_cell(config, task, "high", 1, output, 60)  # unenforced: runs, says what it could not protect
            self.assertEqual((row["valid"], row["contamination"]["protection_dropped"]), (True, ["too-wide"]))
            asked = {**config, "agent_command": config["agent_command"] + ["--settings", "{read_isolation_claude_settings}"]}
            output = self.root / "asked-out"
            output.mkdir()
            with self.assertRaisesRegex(ValueError, "HOME or the filesystem root"):
                replay_eval.execute_cell(asked, task, "high", 1, output, 60)

    def test_an_orphan_blind_receipt_is_counted_named_and_stops_a_resume(self):
        path, results = self.mined(), self.root / "results"
        self.assertIsNone(self.run_lab(path, results, replicates=1)["stop"])
        salt = json.loads((results / "run-manifest.json").read_text())["blind_salt"]
        task = json.loads(path.read_text())["tasks"][0]["id"]
        lost = lab.replay_eval.cell_id({"id": task}, "medium", 2)  # its agent ran, its controller died: no result
        digest = lab._sha256(results / "run-manifest.json")
        with (results / "dispatch.jsonl").open("a") as handle:
            handle.write(json.dumps({"cell": lost, "dispatched_at": lab._now(), "manifest_sha256": digest}) + "\n")
        name = replay_eval.blind_token(salt, lost) + ".runner.json"
        (results / ".blind" / name).write_text("{}")
        report = lab.report(path, results, None)
        self.assertEqual(report["orphan_blind_files"], [{"file": name, "cell": lost}])
        self.assertIn(lost, report["orphan_receipts"])
        self.assertEqual(report["arm_accounting"]["arms"]["medium"]["no_result"], 1)
        self.assertIn("1 files an agent left under its token in `.blind/` (0 not traced to a cell)", (results / "report.md").read_text())
        status = lab.status(path, results)
        self.assertEqual(status["orphans"]["blind_files"], {"tokens": 1, "other": 0})  # counts only: a name is whatever was written
        self.assertNotRegex(json.dumps(status), r"(?i)medium|high")
        resumed = self.run_lab(path, results)
        self.assertEqual((resumed["stop"], resumed["orphans"]), ("uncertain-attempts", [lost]))

    def test_an_orphan_token_is_traced_against_the_declared_plan(self):
        """Review #12: with the ledger lost, a token was looked up only one replicate past the highest finished cell."""
        path, results = self.mined(), self.root / "results"
        self.assertIsNone(self.run_lab(path, results, replicates=1)["stop"])
        config = json.loads(path.read_text())
        salt = json.loads((results / "run-manifest.json").read_text())["blind_salt"]
        lost = lab.replay_eval.cell_id(config["tasks"][0], "medium", 4)
        (results / ".blind" / (replay_eval.blind_token(salt, lost) + ".runner.json")).write_text("{}")
        (results / "dispatch.jsonl").unlink()
        rows = lab.load_cells(results)
        self.assertEqual(lab.blind_orphans(config, results, rows)[0]["cell"], None)  # without the plan: not traced, kept explicit
        self.assertEqual(lab.blind_orphans(config, results, rows, planned_replicates=4)[0]["cell"], lost)

    def test_a_blind_file_alone_stops_a_resume_even_without_its_dispatch(self):
        """The ledger normally names the lost attempt too; without that row the `.blind/` file alone still stops the resume."""
        path, results = self.mined(), self.root / "results"
        self.assertIsNone(self.run_lab(path, results, replicates=1)["stop"])
        salt = json.loads((results / "run-manifest.json").read_text())["blind_salt"]
        task = json.loads(path.read_text())["tasks"][0]["id"]
        lost = lab.replay_eval.cell_id({"id": task}, "high", 2)
        (results / ".blind" / (replay_eval.blind_token(salt, lost) + ".stream.jsonl")).write_text("")
        (results / ".blind" / "unknown.runner.json").write_text("")
        resumed = self.run_lab(path, results)
        self.assertEqual((resumed["stop"], resumed["orphans"]), ("uncertain-attempts", sorted([lost, ".blind/unknown.runner.json"])))
        self.assertEqual(sorted(e["cell"] or e["file"] for e in lab.report(path, results, None)["orphan_blind_files"]),
                         sorted([lost, "unknown.runner.json"]))

    def test_cells_from_before_1_11_report_the_same_verdict(self):
        """Removing what 1.11.0 adds to each cell (token, isolation mode, scan) leaves every verdict and count as it was."""
        path, results = self.mined(), self.root / "results"
        self.assertIsNone(self.run_lab(path, results)["stop"])
        new = lab.report(path, results, None)
        for cell in results.glob("*-r0*.json"):
            if cell.name.endswith(".runner.json"):
                continue
            row = json.loads(cell.read_text())
            for key in ("blind_token", "read_isolation", "contamination"):
                row.pop(key, None)
            cell.write_text(json.dumps(row))
        old = lab.report(path, results, None)
        for key in ("verdict", "arm_accounting", "excluded_invalid", "orphan_receipts", "contrast", "per_task", "reachable_behaviour"):
            self.assertEqual(old[key], new[key], key)
        self.assertEqual(old["read_isolation"]["contamination"]["unrecorded"], old["read_isolation"]["cells"])
        self.assertIn("unrecorded", (results / "report.md").read_text())


class ReplayRunner(unittest.TestCase):
    """`replay_eval run` outside the lab: the same salted token, sealed in its own summary, and the same leakage probe."""
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        repo = self.root / "repo"
        repo.mkdir()
        synthetic(repo)
        base = git(repo, "rev-list", "--max-parents=0", "HEAD").strip()
        (self.root / "agent.py").write_text(CAPTURE_AGENT)
        self.set = self.root / "set.json"
        self.set.write_text(json.dumps({
            "seed": 5, "replicates_per_arm_task": 2, "repos": {"source": str(repo)},
            "agent_command": [sys.executable, "-I", str(self.root / "agent.py"), "{cwd}", "{runner_receipt}", "{effort}", "{prompt_file}",
                              GOOD, PARTIAL],
            "arms": {"alpha": {"provider": "none", "model": "none", "effort": "medium", "doctrine": ""},
                     "bravo": {"provider": "none", "model": "none", "effort": "high", "doctrine": ""}},
            "tasks": [{"id": "case", "repo": "source", "base": base, "accepted": base, "prompt": "Make add really add.",
                       "acceptance": [[sys.executable, "-c", "raise SystemExit(0)"]]}]}))

    def test_nothing_the_agent_sees_names_its_arm_and_the_salt_is_sealed_in_the_summary(self):
        capture, out = self.root / "capture", self.root / "out"
        capture.mkdir()
        argv = ["replay_eval.py", "--set", str(self.set), "run", "--arms", "alpha,bravo", "--out", str(out)]
        environ = synthetic_environ(self.root, LAB_CAPTURE=str(capture))
        with mock.patch.dict(os.environ, environ, clear=True), mock.patch.object(sys, "argv", argv), mock.patch.object(sys, "stdout"):
            self.assertEqual(replay_eval.main(), 0)
        captures = [json.loads(p.read_text()) for p in sorted(capture.iterdir())]
        self.assertEqual(len(captures), 4)
        roots = sorted({str(p) for base in (self.root, Path(tempfile.gettempdir())) for p in (base, base.resolve())}, key=len, reverse=True)
        leaks = []
        for seen in captures:
            self.assertRegex(Path(seen["cwd"]).name, r"^007-\d{16}-")
            self.assertRegex(Path(seen["argv"][2]).name, r"^\d{16}\.runner\.json$")
            self.assertTrue(seen["canary"])
            self.assertEqual(seen["env_naming_arm"], [])
            fields = {"cwd": seen["cwd"], "argv": seen["argv"][:3] + seen["argv"][4:],  # argv[3] is {effort}: the treatment itself
                      "tree": [name for name in seen["tree"] if name.split(os.sep)[0] != ".git"],
                      "stdin": seen["stdin"], "prompt_file": seen["prompt_file"]}
            for field, value in fields.items():
                text = json.dumps(value)
                for root in roots:
                    text = text.replace(root, "/")
                leaks += [(field, w) for w in ("alpha", "bravo", "medium", "high") if re.search(rf"(?<![A-Za-z0-9_]){w}(?![A-Za-z0-9_])", text, re.I)]
        self.assertEqual(sorted(set(leaks)), [])
        summary = json.loads((out / "summary.json").read_text())
        self.assertRegex(summary["blind_salt"], r"^[0-9a-f]{32}$")
        self.assertEqual(list((out / ".blind").iterdir()), [])
        tokens = {Path(seen["argv"][2]).name.removesuffix(".runner.json") for seen in captures}
        for cell in summary["cells"]:
            cid = replay_eval.cell_id({"id": cell["task"]}, cell["arm"], cell["replicate"])
            self.assertEqual(cell["blind_token"], replay_eval.blind_token(summary["blind_salt"], cid))
            self.assertTrue((out / f"{cid}.runner.json").is_file())
            self.assertEqual((cell["read_isolation"], cell["contamination"]["status"]), ("unenforced", "unscanned"))
            tokens.discard(cell["blind_token"])
        self.assertEqual(tokens, set())

    def test_the_salt_is_on_disk_before_the_first_agent_runs(self):
        out = self.root / "out"
        seen = []

        def first(config, *args, **kwargs):
            seen.append(json.loads((out / "summary.json").read_text())["blind_salt"] == config["blind_salt"])
            raise RuntimeError("the controller dies")
        argv = ["replay_eval.py", "--set", str(self.set), "run", "--arms", "alpha", "--out", str(out)]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(replay_eval, "execute_cell", side_effect=first):
            with self.assertRaises(RuntimeError):
                replay_eval.main()
        self.assertEqual(seen, [True])

    def test_a_standalone_run_protects_every_tasks_hidden_tests(self):
        """Review #13: outside the lab only the current task's hidden sources were protected; another task's were readable."""
        sources = [self.root / f"hidden-{i}.py" for i in range(2)]
        for source in sources:
            source.write_text("")
        tasks = [{"id": f"t{i}", "hidden_acceptance": [{"source": str(sources[i])}]} for i in range(2)]
        found = replay_eval.protected_paths({"read_protect": replay_eval.standalone_protect(self.set, tasks)}, tasks[0], self.root / "o")
        self.assertLessEqual({("hidden-test", str(s)) for s in sources}, set(found))

    def test_a_summary_is_replaced_whole_never_truncated(self):
        """Review #12: summary.json, which seals the salt, was rewritten in place; a crash mid-write could lose it."""
        out = self.root / "sealed"
        out.mkdir()
        replay_eval.write_summary(out, self.set, {"seed": 5, "blind_salt": "a" * 32}, 1, [])
        before = (out / "summary.json").read_bytes()
        with mock.patch.object(replay_eval.os, "fsync", side_effect=OSError("disk full")), self.assertRaises(OSError):
            replay_eval.write_summary(out, self.set, {"seed": 5, "blind_salt": "a" * 32}, 1, [{"cell": 1}])
        self.assertEqual((out / "summary.json").read_bytes(), before)
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["summary.json"])

    def test_records_from_before_1_11_still_load_unchanged(self):
        """A replay output written before 1.11.0: labelled receipts, no salt in its summary, no token or scan in its cells."""
        out = self.root / "old"
        out.mkdir()
        receipt = json.dumps({"schema": "007-framework/runner-receipt/v1", "valid": True}).encode()
        row = {"schema": "007-framework/replay-cell/v1", "task": "case", "arm": "alpha", "replicate": 1, "valid": True, "accepted": True,
               "failure_class": "none", "runner_receipt_sha256": hashlib.sha256(receipt).hexdigest()}
        (out / "case-r01-alpha.runner.json").write_bytes(receipt)
        (out / "case-r01-alpha.json").write_text(json.dumps(row))
        replay_eval.write_summary(out, self.set, {"seed": 5}, 1, [row])
        results, receipts = replay_eval.read_cell_artifacts(out)
        self.assertEqual((results, set(receipts)), ({"case-r01-alpha": row}, {"case-r01-alpha"}))
        self.assertNotIn("blind_salt", json.loads((out / "summary.json").read_text()))
        self.assertEqual(replay_eval.blind_files(out), [])
        loaded = lab.load_cells(out)
        self.assertEqual([(c["valid"], c["accepted"]) for c in loaded], [(True, True)])
        self.assertEqual(lab.read_isolation(loaded)["contamination"]["unrecorded"], 1)


if __name__ == "__main__":
    unittest.main()
