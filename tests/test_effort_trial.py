import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts" / "effort_trial.py"
T0 = 1_790_000_000

# Synthetic files with the structure of the real ones (other keys, an existing notify entry and hooks); no real values.
CODEX = '''model = "gpt-6-astra"
model_reasoning_effort = "medium"
sandbox_mode = "workspace-write"
notify = ["/usr/bin/env", "node", "/opt/codex-notify.js"]

[plugins."ponytail@ponytail"]
enabled = true

[projects."/Users/someone/Projects/project-alpha"]
trust_level = "trusted"

[mcp_servers.node_repl]
command = "node"
args = []

[mcp_servers.node_repl.env]
CODEX_HOME = "/Users/someone/.codex"

[profiles.fast]
model_reasoning_effort = "low" # a profile's own effort is never touched

[hooks.state."ponytail@ponytail:hooks/claude-codex-hooks.json:session_start:0:0"]
trusted_hash = "sha256:0000"
'''
CLAUDE = json.dumps({
    "env": {}, "permissions": {"allow": ["Bash(python3:*)"]}, "model": "opus[1m]",
    "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "node ~/.claude/start.js", "timeout": 15,
                                           "statusMessage": "Loading"}]}],
              "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "rtk hook claude"}]}]},
    "effortLevel": "medium",
    "modelSettings": {"claude-opus-5": {"effortLevel": "medium"}, "claude-opus-5-5": {"effortLevel": "xhigh"}},
    "enabledPlugins": {"ponytail@ponytail": True}, "fastMode": False}, indent=2) + "\n"
KIMI = '''default_model = "kimi-code/k3"

[providers."managed:kimi-code"]
type = "kimi"
api_key = ""
base_url = "https://example.test/coding/v1"

[providers."managed:kimi-code".oauth]
storage = "file"
key = "oauth/kimi-code"

[models."kimi-code/k3"]
provider = "managed:kimi-code"
model = "k3"
max_context_size = 262144
support_efforts = [ "low", "high", "max" ]
default_effort = "high"

[thinking]
enabled = true
effort = "high"

[services.moonshot_search]
base_url = "https://example.test/search"
'''
FILES = {"codex": (".codex/config.toml", CODEX), "claude": (".claude/settings.json", CLAUDE),
         "kimi": (".kimi-code/config.toml", KIMI)}
ARMS = {"codex": ["medium", "xhigh"], "claude": ["medium", "xhigh"], "kimi": ["low", "high"]}


class EffortTrialTests(unittest.TestCase):
    """The effort trial writes one key per agent file, deterministically by seed, and records every assignment."""

    def setUp(self):
        self.trial = importlib.import_module("effort_trial")
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name, "home")
        for name, text in FILES.values():
            Path(self.home, name).parent.mkdir(parents=True, exist_ok=True)
            Path(self.home, name).write_text(text)
        self.log = self.home / ".007-framework" / "observatory" / "effort_trial.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def file(self, agent):
        return Path(self.home, FILES[agent][0])

    def configure(self, **trial):
        path = self.home / ".007-framework" / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        base = {"enabled": True, "agents": ["codex", "claude", "kimi"], "arms": ARMS, "seed": 0,
                "claude_model": "claude-opus-5-5"}
        path.write_text(json.dumps({"observatory": {"projects": [], "effort_trial": {**base, **trial}}}))

    def seed_for(self, agent, arm, k=0):
        return next(s for s in range(1000) if self.trial.draw(s, agent, k, ARMS[agent]) == arm)

    def records(self, event=None):
        rows = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.is_file() else []
        return [r for r in rows if event is None or r["event"] == event]

    def test_codex_changes_only_the_top_level_effort_line(self):
        self.configure(agents=["codex"], seed=self.seed_for("codex", "xhigh"))
        self.trial.apply(self.home)
        expected = CODEX.replace('model_reasoning_effort = "medium"', 'model_reasoning_effort = "xhigh"', 1)
        self.assertEqual(self.file("codex").read_text(), expected)              # [profiles.fast] keeps "low"
        assign, = self.records("assign")
        self.assertEqual({k: assign[k] for k in ("agent", "arm", "draw_index", "seed", "original", "session_id")},
                         {"agent": "codex", "arm": "xhigh", "draw_index": 0, "seed": self.seed_for("codex", "xhigh"),
                          "original": "medium", "session_id": None})
        self.assertEqual((assign["file_sha256_before"], assign["file_sha256_after"]),
                         (self.trial.sha256(CODEX.encode()), self.trial.sha256(expected.encode())))
        self.assertIn("at", assign)
        backup = self.home / ".007-framework" / "observatory" / "effort_trial_backup" / "codex-config.toml"
        self.assertEqual(backup.read_text(), CODEX)
        self.assertEqual(oct(backup.stat().st_mode & 0o777), "0o600")

    def test_codex_without_the_key_gets_it_as_the_first_line_and_an_active_profile_is_refused(self):
        bare = CODEX.replace('model_reasoning_effort = "medium"\n', "", 1)
        self.file("codex").write_text(bare)
        self.configure(agents=["codex"], seed=self.seed_for("codex", "xhigh"))
        self.trial.apply(self.home)
        self.assertEqual(self.file("codex").read_text(), 'model_reasoning_effort = "xhigh"\n' + bare)
        self.file("codex").write_text('profile = "fast"\n' + CODEX)
        self.trial.restore(self.home)                                         # back to an inactive trial
        self.trial.apply(self.home)
        self.assertEqual(self.file("codex").read_text(), 'profile = "fast"\n' + CODEX)
        self.assertIn("active profile fast", self.records("refused")[-1]["reason"])

    def test_claude_writes_the_entry_claude_code_reads_byte_for_byte(self):
        # Claude Code 2.1.296 reads modelSettings.<model>.effortLevel; the top-level effortLevel is ignored for current models
        self.configure(agents=["claude"], seed=self.seed_for("claude", "medium"))
        self.trial.apply(self.home)
        expected = CLAUDE.replace('"claude-opus-5-5": {\n      "effortLevel": "xhigh"',
                                  '"claude-opus-5-5": {\n      "effortLevel": "medium"')
        self.assertNotEqual(expected, CLAUDE)
        self.assertEqual(self.file("claude").read_text(), expected)
        self.assertEqual(self.records("assign")[0]["key"], ["modelSettings", "claude-opus-5-5", "effortLevel"])

    def test_claude_keeps_unusual_formatting_and_refuses_an_insertion_it_cannot_format(self):
        odd = '{\n    "model" : "opus",\n    "modelSettings": { "claude-opus-5-5": {"effortLevel":"xhigh"} },\n    "x": [1,2]\n}'
        self.file("claude").write_text(odd)
        self.configure(agents=["claude"], seed=self.seed_for("claude", "medium"))
        self.trial.apply(self.home)
        self.assertEqual(self.file("claude").read_text(), odd.replace('"effortLevel":"xhigh"', '"effortLevel":"medium"'))
        self.trial.restore(self.home)
        self.assertEqual(self.file("claude").read_text(), odd)
        missing = odd.replace('"claude-opus-5-5"', '"claude-sonnet-5"')
        self.file("claude").write_text(missing)
        self.trial.apply(self.home)
        self.assertEqual(self.file("claude").read_text(), missing)             # dumping would reformat the whole file
        self.assertIn("byte-preserving", self.records("refused")[-1]["reason"])
        standard = json.dumps({"model": "opus", "modelSettings": {}}, indent=2) + "\n"
        self.file("claude").write_text(standard)
        self.trial.apply(self.home)
        self.assertEqual(json.loads(self.file("claude").read_text())["modelSettings"],
                         {"claude-opus-5-5": {"effortLevel": self.records("assign")[-1]["arm"]}})
        self.trial.restore(self.home)
        self.assertEqual(self.file("claude").read_text(), standard, "restore removes the key and only the objects it created")

    def test_claude_needs_the_model_whose_entry_it_reads(self):
        self.configure(agents=["claude"], claude_model=None)
        self.trial.apply(self.home)
        self.assertEqual(self.file("claude").read_text(), CLAUDE)
        self.assertIn("claude_model", self.records("refused")[-1]["reason"])

    def test_kimi_writes_thinking_effort_not_the_model_default_and_only_supported_arms(self):
        # Kimi resolves requested ?? thinking.effort ?? the model's default_effort; default_effort is refreshed from its server
        self.configure(agents=["kimi"], seed=self.seed_for("kimi", "low"))
        self.trial.apply(self.home)
        self.assertEqual(self.file("kimi").read_text(), KIMI.replace('\neffort = "high"', '\neffort = "low"'))
        self.trial.restore(self.home)
        self.assertEqual(self.file("kimi").read_text(), KIMI)
        self.configure(agents=["kimi"], arms={"kimi": ["medium", "high"]})
        self.trial.apply(self.home)
        self.assertEqual(self.file("kimi").read_text(), KIMI)
        self.assertIn("supported: low, high, max", self.records("refused")[-1]["reason"])   # config_guard is the single source

    def test_apply_is_idempotent_and_draws_once_per_new_session(self):
        self.configure(agents=["codex"], seed=11)
        for _ in range(3):
            self.trial.apply(self.home)                                       # no session: keep the current arm in place
        self.trial.apply(self.home, "codex", session_id="s1")
        self.trial.apply(self.home, "codex", session_id="s1")                 # the same session's later prompts
        self.trial.apply(self.home, "codex", session_id="s2")
        assigns = self.records("assign")
        self.assertEqual([(r["draw_index"], r["session_id"]) for r in assigns], [(0, None), (1, "s1"), (2, "s2")])
        self.assertEqual([r["arm"] for r in assigns], [self.trial.draw(11, "codex", k, ARMS["codex"]) for k in range(3)])
        value = tomllib.loads(self.file("codex").read_text())["model_reasoning_effort"]
        self.assertEqual(value, assigns[-1]["arm"])
        self.assertEqual(self.trial.status(self.home)["by_agent"]["codex"]["holds_last_applied"], True)

    def test_the_arm_sequence_is_fixed_by_the_seed(self):
        def sequence(seed, n=24):
            home = Path(tempfile.mkdtemp(dir=self.tmp.name))
            Path(home, ".codex").mkdir()
            Path(home, ".codex", "config.toml").write_text(CODEX)
            Path(home, ".007-framework").mkdir()
            Path(home, ".007-framework", "config.json").write_text(json.dumps({"observatory": {"effort_trial": {
                "enabled": True, "agents": ["codex"], "arms": ARMS, "seed": seed}}}))
            for i in range(n):
                self.trial.apply(home, "codex", session_id=f"s{i}")
            log = home / ".007-framework" / "observatory" / "effort_trial.jsonl"
            return [json.loads(line)["arm"] for line in log.read_text().splitlines()]
        self.assertEqual(sequence(5), sequence(5))
        self.assertNotEqual(sequence(5), sequence(6))
        self.assertEqual(set(sequence(5)), {"medium", "xhigh"})

    def test_a_hand_edit_is_recorded_once_and_left_alone(self):
        self.configure(agents=["codex"], seed=self.seed_for("codex", "xhigh"))
        self.trial.apply(self.home)
        edited = self.file("codex").read_text().replace('= "xhigh"', '= "medium"', 1)   # an arm, but not the one applied
        self.file("codex").write_text(edited)
        for session in ("s1", "s2", "s3"):
            self.trial.apply(self.home, "codex", session_id=session)
        self.assertEqual(self.file("codex").read_text(), edited)
        override, = self.records("manual-override")
        self.assertEqual((override["found"], override["expected"]), ("medium", "xhigh"))
        self.assertEqual(len(self.records("assign")), 1)
        self.assertEqual(self.trial.status(self.home)["by_agent"]["codex"]["holds_last_applied"], False)
        self.trial.restore(self.home)                                         # ends the run and keeps the human's value
        self.assertEqual(self.file("codex").read_text(), edited)
        self.assertEqual(self.records("restore")[-1]["arm"], "medium")
        self.trial.apply(self.home, "codex", session_id="s4")                 # a new run starts from that value
        self.assertEqual(self.records("assign")[-1]["original"], "medium")

    def test_a_file_that_does_not_parse_is_refused_without_writing(self):
        self.file("codex").write_text(CODEX + "broken = [\n")
        self.configure(agents=["codex"])
        self.trial.apply(self.home)
        self.trial.apply(self.home)
        self.assertEqual(self.file("codex").read_text(), CODEX + "broken = [\n")
        self.assertEqual(len(self.records("refused")), 1, "the same refusal is not logged on every hook call")
        self.assertFalse((self.home / ".007-framework" / "observatory" / "effort_trial_backup").exists())

    def test_disabled_apply_restores_only_the_effort_key(self):
        self.configure(seed=self.seed_for("codex", "xhigh"))
        self.trial.apply(self.home)
        self.assertEqual(sorted(r["agent"] for r in self.records("assign")), ["claude", "codex", "kimi"])
        changed = self.file("codex").read_text()
        self.file("codex").write_text(changed.replace('sandbox_mode = "workspace-write"', 'sandbox_mode = "read-only"'))
        self.configure(enabled=False)
        self.trial.apply(self.home)
        self.assertEqual(self.file("codex").read_text(), CODEX.replace('"workspace-write"', '"read-only"'))
        self.assertEqual(self.file("claude").read_text(), CLAUDE)
        self.assertEqual(self.file("kimi").read_text(), KIMI)
        self.assertEqual(sorted(r["agent"] for r in self.records("restore")), ["claude", "codex", "kimi"])
        self.trial.apply(self.home)
        self.assertEqual(len(self.records("restore")), 3, "nothing left to restore")

    def test_the_write_is_atomic_keeps_the_mode_and_follows_a_symlink(self):
        seed = next(s for s in range(1000) if self.trial.draw(s, "codex", 0, ARMS["codex"]) == "xhigh"
                    and self.trial.draw(s, "claude", 0, ARMS["claude"]) == "medium")   # both files must change
        self.configure(agents=["codex", "claude"], seed=seed)
        os.chmod(self.file("codex"), 0o600)
        with mock.patch.object(self.trial.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.trial.apply(self.home, "codex")
        self.assertEqual(self.file("codex").read_text(), CODEX)
        self.assertEqual(sorted(p.name for p in self.file("codex").parent.iterdir()), ["config.toml"])
        self.assertEqual(self.records("assign"), [])
        self.trial.apply(self.home, "codex")
        self.assertEqual(oct(self.file("codex").stat().st_mode & 0o777), "0o600")
        target = Path(self.tmp.name, "dotfiles", "settings.json")
        target.parent.mkdir()
        target.write_text(CLAUDE)
        self.file("claude").unlink()
        self.file("claude").symlink_to(target)
        self.trial.apply(self.home, "claude")
        self.assertTrue(self.file("claude").is_symlink())
        self.assertNotEqual(target.read_text(), CLAUDE)

    def test_install_and_uninstall_round_trip_and_keep_existing_hooks(self):
        for agent in FILES:
            command = self.trial.hook_command(agent, python="/opt/py/bin/python3", script="/repo/scripts/effort_trial.py")
            self.assertEqual(command, f"/opt/py/bin/python3 /repo/scripts/effort_trial.py apply --agent {agent} --hook "
                                      ">/dev/null 2>&1 || true")
            self.trial.install(self.home, [agent], command=command)
            once = self.file(agent).read_text()
            text, original = once, FILES[agent][1]
            if agent == "claude":
                data, before = json.loads(text), json.loads(original)
                self.assertEqual(data["hooks"].pop("UserPromptSubmit"),
                                 [{"hooks": [{"type": "command", "command": command, "timeout": 10}]}])
                self.assertEqual(data, before)
            else:
                data, before = tomllib.loads(text), tomllib.loads(original)
                if agent == "codex":
                    self.assertEqual(data["hooks"].pop("UserPromptSubmit"),
                                     [{"hooks": [{"type": "command", "command": command, "timeout": 10}]}])
                else:
                    self.assertEqual(data.pop("hooks"), [{"event": "UserPromptSubmit", "command": command, "timeout": 10}])
                self.assertEqual(data, before)
                self.assertTrue(text.startswith(original))
            self.trial.install(self.home, [agent], command=command)
            self.assertEqual(self.file(agent).read_text(), once, f"{agent}: install is idempotent")
            self.trial.uninstall(self.home, [agent])
            self.assertEqual(self.file(agent).read_text(), original, f"{agent}: uninstall restores every byte")
            self.trial.uninstall(self.home, [agent])
            self.assertEqual(self.file(agent).read_text(), original)
            backup = self.home / ".007-framework" / "observatory" / "effort_trial_backup" / f"{agent}-{Path(FILES[agent][0]).name}"
            self.assertEqual(backup.read_text(), original)
        self.assertEqual([r["event"] for r in self.records()], ["install", "uninstall"] * 3)

    def test_hook_mode_is_silent_never_fails_and_stores_only_the_session_id(self):
        self.configure(agents=["claude"])
        payload = json.dumps({"session_id": "s1", "hook_event_name": "UserPromptSubmit", "prompt": "PRIVATE prompt"})
        run = lambda: subprocess.run([sys.executable, str(SCRIPT), "apply", "--agent", "claude", "--hook", "--home", str(self.home)],
                                     input=payload, capture_output=True, text=True)
        out = run()
        self.assertEqual((out.returncode, out.stdout, out.stderr), (0, "", ""))
        self.assertEqual(self.records("assign")[-1]["session_id"], "s1")
        self.assertNotIn("PRIVATE", self.log.read_text())
        (self.home / ".007-framework" / "config.json").write_text("{broken")
        out = run()
        self.assertEqual((out.returncode, out.stdout), (0, ""))
        self.assertIn("not valid JSON", self.records("refused")[-1]["reason"])   # config_guard names the real cause

    def test_assigned_effort_is_the_arm_its_agent_held_when_the_session_started(self):
        def rec(at, event, arm=None, session_id=None, agent="claude"):
            return {"at": f"2026-10-25T10:00:{at:02d}+00:00", "event": event, "agent": agent, "arm": arm, "session_id": session_id}
        records = [rec(1, "assign", "medium"), rec(3, "assign", "xhigh", "s2"), rec(5, "manual-override"),
                   rec(6, "restore", "high"), rec(7, "assign", "medium", "x"), rec(9, "restore", "high"),
                   rec(2, "assign", "low", agent="codex")]

        def assigned(sid, second, effort, source="claude"):
            session = {"session_id": sid, "source": source, "effort": effort, "started_at": f"2026-10-25T10:00:{second:02d}Z"}
            value = self.trial.assignment(records, session)
            return value["assigned_effort"], value["effort_compliant"]
        self.assertEqual(assigned("s0", 0, "medium"), (None, None))           # before the trial
        self.assertEqual(assigned("s1", 2, "medium"), ("medium", True))
        self.assertEqual(assigned("s2", 4, "medium"), ("medium", True), "its own first prompt drew the next session's arm")
        self.assertEqual(assigned("s3", 4, "high"), ("xhigh", False))
        self.assertEqual(assigned("s4", 6, "high"), (None, None))            # after a hand edit: not randomized
        self.assertEqual(assigned("s5", 8, "unmeasured"), ("medium", None))
        self.assertEqual(assigned("s6", 10, "medium"), (None, None))         # restored
        self.assertEqual(assigned("c1", 4, "low", source="codex"), ("low", True))
        self.assertEqual(assigned("g1", 4, "unmeasured", source="gemini"), (None, None))


class ObservatoryAssignmentTests(unittest.TestCase):
    """The observatory rows carry the intention-to-treat arm (assigned_effort) for the trial's projects only."""

    def test_report_rows_carry_assigned_effort_for_the_trial_repos(self):
        hist = importlib.import_module("observatory_history")
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "project-beta")
            repo.mkdir()
            env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
                   "GIT_AUTHOR_EMAIL": "t@example.test", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.test",
                   "GIT_AUTHOR_DATE": f"@{T0 + 100} +0000", "GIT_COMMITTER_DATE": f"@{T0 + 100} +0000"}
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            (repo / "f.txt").write_text("x\n")
            subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True, env=env)
            subprocess.run(["git", "commit", "-qm", "work"], cwd=repo, check=True, env=env)
            store = Path(tmp, "observatory", "sessions.jsonl")
            hist.record(store, [{"source": "codex", "session_id": "a", "project_id": "p1", "cwd": str(repo), "model": "m",
                                 "effort": "xhigh", "started_at": T0, "updated_at": T0 + 200, "total_tokens": 1,
                                 "reasoning_output_tokens": 0}])
            (store.parent / "effort_trial.jsonl").write_text(json.dumps(
                {"at": T0 - 60, "event": "assign", "agent": "codex", "arm": "medium", "session_id": None}) + "\n")
            entries = [{"project_id": "p1", "path": str(repo)}]
            row, = hist.report(store, entries, "p1", {"p1"}, now=T0 + 40 * 86400, slack_s=0, trial_repos=["project-beta"])
            self.assertEqual((row["assigned_effort"], row["effort_compliant"]), ("medium", False))
            row, = hist.report(store, entries, "p1", {"p1"}, now=T0 + 40 * 86400, slack_s=0)
            self.assertEqual(row["assigned_effort"], "medium", "no trial repos: every project enters the analysis")
            row, = hist.report(store, entries, "p1", {"p1"}, now=T0 + 40 * 86400, slack_s=0, trial_repos=["Other"])
            self.assertEqual((row["assigned_effort"], row["effort_compliant"]), (None, None))


if __name__ == "__main__":
    unittest.main()
