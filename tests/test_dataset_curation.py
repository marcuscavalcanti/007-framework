"""Read-only admission checkpoints; no generators, business oracles or models."""
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import test_dataset_admission as fixtures

replay, capture, ROOT = fixtures.replay, fixtures.capture, fixtures.ROOT


class CurationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.DatasetTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.vault, self.task = self.fixture.root, self.fixture.vault, self.fixture.task
        self.checkpoint = self.root / 'curation' / 'checkpoint.json'

    def curate(self, tasks=None, **extra):
        self.assertTrue(hasattr(replay, 'curate_dataset'), 'curation checkpoint is not implemented')
        return replay.curate_dataset(tasks if tasks is not None else [self.task], vault_root=self.vault,
                                     checkpoint=self.checkpoint, **extra)

    def followup(self, **changes):
        value = {
            "project_id": "project", "task_id": "task", "input_sha256": self.fixture.ref["sha256"],
            "result_sha256": hashlib.sha256(self.fixture.result.read_bytes()).hexdigest(),
            "observed_at": "2026-10-12T12:00:00Z", "corrective_lines": 9,
            "repair_rounds": 1, "escape_7d": "yes", "description": "PRIVATE OBSERVATION",
            **changes,
        }
        payload = capture._json_bytes(value)
        digest = hashlib.sha256(payload).hexdigest()
        name = f"followup-{digest}.json"
        path = self.fixture.result.parent / name
        if not path.exists():
            capture.write_bytes_no_replace(path, payload, "fixture followup")
        return {"manifest": f"project/task/{name}", "sha256": digest}

    def test_bound_followups_are_sanitized_append_only_and_quiet_on_repeat(self):
        self.curate()
        ref = self.followup()
        task = {**self.task, "followup_refs": [ref]}
        result = self.curate([task])
        row = result["admission"]["cases"][0]
        self.assertEqual(result["delta_ids"], ["case"])
        self.assertEqual(len(row.get("declared_followups", [])), 1)
        self.assertEqual(row["declared_followups"][0]["source_sha256"], ref["sha256"])
        self.assertEqual(row["declared_followups"][0]["corrective_lines"], 9)
        self.assertFalse(row["causal_eligible"])
        self.assertFalse(row["replay_ready"])
        self.assertNotIn("PRIVATE OBSERVATION", self.checkpoint.read_text())
        before = self.checkpoint.read_bytes()
        self.assertFalse(self.curate([task])["changed"])
        self.assertEqual(self.checkpoint.read_bytes(), before)
        later = self.followup(observed_at="2026-10-12T13:00:00Z", escape_7d="no")
        task["followup_refs"] = [later, ref]
        result = self.curate([task])
        self.assertEqual(result["delta_ids"], ["case"])
        self.assertEqual(len(result["admission"]["cases"][0]["declared_followups"]), 2)
        task["followup_refs"].reverse()
        self.assertFalse(self.curate([task])["changed"])
        self.assertEqual(capture.qualify_case(self.vault, "project", "task", self.fixture.ref)["state"],
                         "case-retained")

    def hypothesis(self, **changes):
        value = {"project_id": "project", "task_id": "task", "input_sha256": self.fixture.ref["sha256"],
            "result_sha256": hashlib.sha256(self.fixture.result.read_bytes()).hexdigest(),
            "kind": "gate", "status": "proposed", "mechanism": "PRIVATE MECHANISM",
            "evidence": "PRIVATE EVIDENCE", "counterproof": "Focal mutant fails",
            "positive_control": "Legitimate control passes", "experiment": "Future OLD NEW, not executed",
            **changes}
        raw = capture._json_bytes(value)
        digest = hashlib.sha256(raw).hexdigest()
        name = f"hypothesis-{digest}.json"
        if not (self.fixture.result.parent / name).exists():
            capture.write_bytes_no_replace(self.fixture.result.parent / name, raw, "fixture hypothesis")
        return {"manifest": f"project/task/{name}", "sha256": digest}

    def test_hypotheses_are_bound_sanitized_bounded_per_cycle_and_quiet(self):
        gate, route = self.hypothesis(), self.hypothesis(kind="routing")
        task = {**self.task, "hypothesis_refs": [route, gate]}
        with patch.object(replay, 'run', side_effect=AssertionError('oracle forbidden')):
            value = self.curate([task])
        rows = value["admission"]["cases"]
        self.assertEqual(len(rows[0].get("declared_hypotheses", [])), 2)
        self.assertEqual({entry['kind'] for entry in value['admission']['proposal_delta']}, {'gate','routing'})
        self.assertFalse(rows[0]["causal_eligible"])
        self.assertFalse(rows[0]["replay_ready"])
        self.assertNotIn("PRIVATE", self.checkpoint.read_text())
        before = self.checkpoint.read_bytes()
        task['hypothesis_refs'].reverse()
        self.assertFalse(self.curate([task])['changed'])
        self.assertEqual(before, self.checkpoint.read_bytes())
        later = self.hypothesis(mechanism='PRIVATE SECOND')
        task['hypothesis_refs'].append(later)
        value = self.curate([task])
        self.assertEqual(value['admission']['proposal_delta'], [
            {'case_id':'case','kind':'gate','source_sha256':later['sha256']}])
        replay.read_curation_checkpoint(self.checkpoint, vault_root=self.vault)

    def test_invalid_or_excess_hypotheses_never_advance_the_checkpoint(self):
        self.curate()
        before = self.checkpoint.read_bytes()
        for change in ({'kind':'unknown'}, {'kind':[]}, {'status':'approved'}, {'evidence':''},
                       {'counterproof':None}, {'mechanism':'x'*1025}, {'task_id':'other'},
                       {'project_id':'foreign'}, {'result_sha256':'b'*64}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.curate([{**self.task,'hypothesis_refs':[self.hypothesis(**change)]}])
            self.assertEqual(before,self.checkpoint.read_bytes())
        gate = self.hypothesis()
        other = self.hypothesis(mechanism='Another private gate')
        for refs in ([gate,other], [gate,gate], [gate]*9, [{'manifest':'../outside','sha256':'a'*64}]):
            with self.subTest(refs=refs), self.assertRaises(ValueError):
                self.curate([{**self.task,'hypothesis_refs':refs}])
            self.assertEqual(before,self.checkpoint.read_bytes())

    def test_hypothesis_source_loss_or_ambiguous_binding_preserves_history(self):
        ref = self.hypothesis()
        task = {**self.task,'hypothesis_refs':[ref]}
        self.curate([task])
        before = self.checkpoint.read_bytes()
        lost = self.curate()
        self.assertFalse(lost['complete'])
        self.assertIn('hypothesis-history-shrank',lost['gaps'])
        self.assertEqual(before,self.checkpoint.read_bytes())
        for tasks in ([task,self.task],[self.task,task]):
            with self.assertRaises(ValueError):
                self.curate(tasks)
        path = self.vault/ref['manifest']
        original = path.read_bytes()
        path.write_bytes(original[:-1]+b'x')
        with self.assertRaises(ValueError):
            self.curate([task])
        self.assertEqual(before,self.checkpoint.read_bytes())
        path.unlink()
        with self.assertRaises(OSError):
            self.curate([task])
        path.symlink_to(self.fixture.result)
        with self.assertRaises(ValueError):
            self.curate([task])
        self.assertEqual(before,self.checkpoint.read_bytes())

    def test_rehashed_checkpoint_cannot_forge_proposal_delta_or_promotion(self):
        ref = self.hypothesis()
        self.curate([{**self.task,'hypothesis_refs':[ref]}])
        original = self.checkpoint.read_bytes()
        self.assertIn('proposal_delta', json.loads(original)['admission'])
        for mutate in (
            lambda v: v['admission']['proposal_delta'][0].update(source_sha256='f'*64),
            lambda v: v['admission']['cases'][0]['declared_hypotheses'][0].update(status='approved'),
            lambda v: v['admission']['cases'][0].update(retained_case=False),
            lambda v: v['admission']['cases'].append({**v['admission']['cases'][0],'project_id':'foreign'}),
            lambda v: v['admission']['cases'].append({**v['admission']['cases'][0],'id':'shadow','project_id':'foreign'}),
            lambda v: v['admission']['cases'].append({**v['admission']['cases'][0],'id':'shadow','declared_hypotheses':[]})):
            value = json.loads(original)
            mutate(value)
            value['admission']['counts'] = replay.dataset_counts(value['admission']['cases'])
            content = {k:value[k] for k in ('vault_sha256','verifier_sha256','admission')}
            value['checkpoint_sha256'] = hashlib.sha256(capture._json_bytes(content)).hexdigest()
            self.checkpoint.write_bytes(capture._json_bytes(value))
            with self.assertRaises(ValueError):
                replay.read_curation_checkpoint(self.checkpoint,vault_root=self.vault)
        self.checkpoint.write_bytes(original)

    def test_full_followup_history_does_not_block_one_new_hypothesis(self):
        refs = [self.followup(corrective_lines=i) for i in range(8)]
        task = {**self.task,'followup_refs':refs}
        self.curate([task])
        task['hypothesis_refs'] = [self.hypothesis()]
        value = self.curate([task])
        row = value['admission']['cases'][0]
        self.assertEqual(len(row['declared_followups']),8)
        self.assertEqual(len(row['declared_hypotheses']),1)
        self.assertEqual(value['admission']['proposal_delta'][0]['kind'],'gate')
        before = self.checkpoint.read_bytes()
        task['followup_refs'].append(self.followup(corrective_lines=9))
        with self.assertRaises(ValueError):
            self.curate([task])
        self.assertEqual(before,self.checkpoint.read_bytes())

    def test_wrong_or_invalid_followup_never_advances_checkpoint(self):
        self.curate()
        before = self.checkpoint.read_bytes()
        for changes in ({"project_id": "foreign"}, {"task_id": "other"},
                        {"input_sha256": "a" * 64}, {"result_sha256": "b" * 64},
                        {"repair_rounds": True}, {"corrective_lines": -1},
                        {"escape_7d": 0}, {"observed_at": "invalid"},
                        {"observed_at": "2099-01-01T00:00:00Z"}):
            with self.subTest(changes=changes):
                ref = self.followup(**changes)
                with self.assertRaises(ValueError):
                    self.curate([{**self.task, "followup_refs": [ref]}])
                self.assertEqual(self.checkpoint.read_bytes(), before)
        ref = self.followup()
        for refs in ([ref, ref], [{**ref, "sha256": "c" * 64}],
                     [{**ref, "manifest": "../outside"}], [ref] * 9):
            with self.subTest(refs=refs), self.assertRaises(ValueError):
                self.curate([{**self.task, "followup_refs": refs}])
        self.assertEqual(self.checkpoint.read_bytes(), before)

    def test_missing_followup_reference_cannot_erase_previous_observation(self):
        ref = self.followup()
        self.curate([{**self.task, "followup_refs": [ref]}])
        before = self.checkpoint.read_bytes()
        result = self.curate()
        self.assertFalse(result["complete"])
        self.assertIn("followup-history-shrank", result["gaps"])
        self.assertEqual(self.checkpoint.read_bytes(), before)

    def test_followup_is_not_attached_to_an_ambiguous_trial(self):
        self.curate()
        before = self.checkpoint.read_bytes()
        ref = self.followup()
        for tasks in ([{**self.task, "followup_refs": [ref]}, self.task],
                      [self.task, {**self.task, "followup_refs": [ref]}]):
            with self.assertRaises(ValueError):
                self.curate(tasks)
            self.assertEqual(self.checkpoint.read_bytes(), before)

    def test_changed_missing_or_symlink_followup_preserves_checkpoint(self):
        ref = self.followup()
        self.curate([{**self.task, "followup_refs": [ref]}])
        before = self.checkpoint.read_bytes()
        path = self.vault / ref["manifest"]
        original = path.read_bytes()
        path.write_bytes(original[:-1] + b"x")
        with self.assertRaises(ValueError):
            self.curate([{**self.task, "followup_refs": [ref]}])
        self.assertEqual(self.checkpoint.read_bytes(), before)
        path.unlink()
        with self.assertRaises(OSError):
            self.curate([{**self.task, "followup_refs": [ref]}])
        path.symlink_to(self.fixture.result)
        with self.assertRaises(ValueError):
            self.curate([{**self.task, "followup_refs": [ref]}])
        self.assertEqual(self.checkpoint.read_bytes(), before)

    def test_rehashed_checkpoint_cannot_attach_followup_to_unretained_case(self):
        ref = self.followup()
        self.curate([{**self.task, "followup_refs": [ref]}])
        value = json.loads(self.checkpoint.read_bytes())
        row = value["admission"]["cases"][0]
        row.update(retained_case=False, input_sha256=None, result_sha256=None)
        value["admission"]["counts"] = replay.dataset_counts([row])
        content = {key: value[key] for key in ("vault_sha256", "verifier_sha256", "admission")}
        value["checkpoint_sha256"] = hashlib.sha256(capture._json_bytes(content)).hexdigest()
        self.checkpoint.write_bytes(capture._json_bytes(value))
        with self.assertRaises(ValueError):
            replay.read_curation_checkpoint(self.checkpoint, vault_root=self.vault)

    def test_same_bytes_do_not_rewrite_or_promote_a_case(self):
        with patch.object(replay, 'run', side_effect=AssertionError('oracle forbidden')):
            first = self.curate()
            before = self.checkpoint.read_bytes()
            second = self.curate()
        self.assertTrue(first['complete'])
        self.assertTrue(first['changed'])
        self.assertEqual(first['delta_ids'], ['case'])
        self.assertFalse(second['changed'])
        self.assertEqual(second['delta_ids'], [])
        self.assertEqual(self.checkpoint.read_bytes(), before)
        self.assertEqual(first['checkpoint_sha256'], second['checkpoint_sha256'])
        self.assertEqual(first['admission']['counts']['retained'], 1)
        self.assertEqual(first['admission']['counts']['qualified-comparison'], 0)
        self.assertEqual(self.checkpoint.stat().st_mode & 0o777, 0o600)

    def test_addition_is_a_single_delta_and_reordering_is_quiet(self):
        self.curate()
        observation = {**self.task, 'id': 'new', 'source_task_id': 'new', 'replay_ref': None,
                       'family': 'other', 'split': 'discovery', 'prompt': 'PRIVATE INPUT'}
        result = self.curate([observation, self.task])
        self.assertEqual(result['delta_ids'], ['new'])
        self.assertEqual(result['admission']['counts']['retained'], 1)
        self.assertNotIn('PRIVATE INPUT', self.checkpoint.read_text())
        self.assertFalse(self.curate([self.task, observation])['changed'])

    def test_unreadable_or_unfinished_publication_does_not_advance(self):
        self.curate()
        before = self.checkpoint.read_bytes()
        result = self.fixture.result
        result.rename(result.with_name('pending-result.json'))
        pending = self.curate()
        self.assertFalse(pending['complete'])
        self.assertFalse(pending['changed'])
        self.assertEqual(self.checkpoint.read_bytes(), before)
        result.with_name('pending-result.json').rename(result)
        (result.parent / 'outputs/files/tracked.py').unlink()
        unavailable = self.curate()
        self.assertFalse(unavailable['complete'])
        self.assertEqual(self.checkpoint.read_bytes(), before)

    def test_history_shrink_is_not_a_completed_empty_collection(self):
        self.curate()
        before = self.checkpoint.read_bytes()
        result = self.curate([])
        self.assertFalse(result['complete'])
        self.assertIn('source-history-shrank', result['gaps'])
        self.assertEqual(self.checkpoint.read_bytes(), before)

    def test_forgotten_retention_reference_does_not_erase_previous_evidence(self):
        self.curate()
        before = self.checkpoint.read_bytes()
        result = self.curate([{**self.task, 'replay_ref': None, 'split': 'discovery'}])
        self.assertFalse(result['complete'])
        self.assertIn('source-history-shrank', result['gaps'])
        self.assertEqual(self.checkpoint.read_bytes(), before)

    def test_reused_case_id_cannot_rebind_the_historical_source(self):
        self.curate()
        before = self.checkpoint.read_bytes()
        other = self.fixture.additional_case([sys.executable, '-c', 'pass'], name='other')
        result = self.curate([{**other, 'id': 'case'}])
        self.assertFalse(result['complete'])
        self.assertIn('source-identity-changed', result['gaps'])
        self.assertEqual(self.checkpoint.read_bytes(), before)

    def test_corrupt_checkpoint_and_foreign_scope_are_not_overwritten(self):
        self.curate()
        original = self.checkpoint.read_bytes()
        value = json.loads(original)
        value['admission']['counts']['retained'] = 999
        self.checkpoint.write_text(json.dumps(value))
        bad = self.checkpoint.read_bytes()
        with self.assertRaises(ValueError):
            self.curate()
        self.assertEqual(self.checkpoint.read_bytes(), bad)
        self.checkpoint.write_bytes(original)
        other = self.root / 'other-vault'
        with self.assertRaises(ValueError):
            replay.curate_dataset([self.task], vault_root=other, checkpoint=self.checkpoint)
        self.assertEqual(self.checkpoint.read_bytes(), original)

    def test_concurrent_owner_and_failed_publication_preserve_checkpoint(self):
        self.curate()
        before = self.checkpoint.read_bytes()
        lock = self.checkpoint.with_name(self.checkpoint.name + '.lock')
        lock.mkdir(mode=0o700)
        with self.assertRaises(ValueError):
            self.curate()
        lock.rmdir()
        changed = {**self.task, 'class': 'inspect'}
        with patch('framework_cli.write_json_atomic', side_effect=OSError('publication failed')):
            with self.assertRaises(OSError):
                self.curate([changed])
        self.assertEqual(self.checkpoint.read_bytes(), before)
        self.assertFalse(lock.exists())
        self.assertEqual(self.curate([changed])['delta_ids'], ['case'])

    def test_cli_is_quiet_on_repeat_and_refuses_oracle_execution(self):
        manifest = self.root / 'set.json'
        manifest.write_text(json.dumps({'tasks': [self.task]}))
        command = [sys.executable, str(ROOT / 'scripts/replay_eval.py'), '--set', str(manifest),
                   '--vault', str(self.vault), '--checkpoint', str(self.checkpoint), 'curate']
        first = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)['delta_ids'], ['case'])
        before = self.checkpoint.read_bytes()
        second = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(second.stdout, '')
        denied = subprocess.run(command + ['--recheck'], capture_output=True, text=True, timeout=30)
        self.assertEqual(denied.returncode, 2)
        self.assertEqual(self.checkpoint.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
