"""Incomplete candidates remain usable for bounded calibration, never fake ROI."""
import hashlib
import contextlib
import io
import json
import sys
from unittest import TestCase
from unittest.mock import patch
import test_replay_capture as fixtures
import replay_eval as replay
import replay_capture as capture


class IncompleteReplayTests(TestCase):
    def test_native_telemetry_collision_preserves_only_a_quiescent_candidate(self):
        for cleanup_state in ('gone','cleanup-group-observable'):
            with self.subTest(cleanup_state=cleanup_state):
                fixture = fixtures.ReplayCaptureTests(methodName='runTest')
                fixture.setUp()
                try:
                    cli = __import__('framework_cli')
                    cli.init_project(fixture.repo, fixture.root / 'registry.json')
                    executable = fixture.root / 'codex'
                    events = [{'type':'thread.started','thread_id':'synthetic'}, {'type':'turn.started'},
                              {'type':'turn.completed','usage':{'input_tokens':4,'output_tokens':2}}]
                    executable.write_text('#!' + sys.executable + '\nfrom pathlib import Path\nimport json\n'
                        + "Path('tracked.py').write_bytes(b'value = 9\\n')\n"
                        + "Path('.007/tasks/native-collision.telemetry.json').write_text('{}')\n"
                        + 'for event in ' + repr(events) + ': print(json.dumps(event),flush=True)\n')
                    executable.chmod(0o700)
                    command = [str(executable),'exec','--json','--ephemeral','synthetic']
                    config = fixture.root / 'capture.json'
                    config.write_text(json.dumps({**fixture.config,'command':command}))
                    original_cleanup = cli.kill_process_group
                    def cleanup(process):
                        self.assertEqual(original_cleanup(process), 'gone')
                        return cleanup_state
                    with (patch.object(cli,'kill_process_group',side_effect=cleanup),
                          contextlib.redirect_stdout(io.TextIOWrapper(io.BytesIO(),encoding='utf-8'))):
                        with self.assertRaises(ValueError):
                            cli.run_task(fixture.repo,'native-collision',fixture.repo / 'outcome.json',command,
                                native_cli='codex',capture_config_file=config,vault_root=fixture.vault)
                    start = json.loads((fixture.repo / '.007/tasks/native-collision.task.json').read_bytes())
                    case = (fixture.vault / start['replay_ref']['manifest']).parent
                    self.assertEqual((fixture.repo / '.007/tasks/native-collision.telemetry.json').read_bytes(), b'{}')
                    self.assertFalse((fixture.repo / '.007/receipts/native-collision.receipt.json').exists())
                    self.assertEqual((case / 'result.json').exists(), cleanup_state == 'gone')
                    self.assertEqual((case / 'observation.json').exists(), cleanup_state == 'gone')
                    if cleanup_state == 'gone':
                        observation = json.loads((case / 'outputs/receipt.json').read_bytes())
                        self.assertEqual(observation['reason_code'],'native-telemetry-publication-failed')
                        self.assertEqual(observation['native_telemetry']['usage']['total_tokens'],6)
                        self.assertNotIn('status',observation)
                        self.assertIsNone(observation['cost_usd'])
                finally:
                    fixture.doCleanups()

    def test_stable_incomplete_candidates_reach_admission_curation_and_explicit_recheck(self):
        scenarios = {
            'unpriced': ("v=json.loads(Path('template.json').read_text()); v['task_id']=os.environ['FRAMEWORK_007_TASK_ID']; "
                         "v.update(cost_usd=None,cost_status='unavailable',cost_source='custom:flat',cost_unavailable_reason='fixture unpriced'); "
                         "Path(os.environ['FRAMEWORK_007_RECEIPT_PATH']).write_text(json.dumps(v))", True),
            'missing-receipt': ('pass', True),
            'executor-error': ('raise SystemExit(7)', True),
            'foreign-receipt': ("v=json.loads(Path('template.json').read_text()); v['task_id']='foreign'; "
                                "Path(os.environ['FRAMEWORK_007_RECEIPT_PATH']).write_text(json.dumps(v))", True),
            'wrong-candidate': ("Path('tracked.py').write_text('value = 8\\n'); raise SystemExit(7)", False),
        }
        for name, (tail, oracle_passes) in scenarios.items():
            with self.subTest(name=name):
                fixture = fixtures.ReplayCaptureTests(methodName='runTest')
                fixture.setUp()
                try:
                    (fixture.repo / 'task.txt').write_text('Set tracked.py to value = 9, preserve unrelated bytes.')
                    (fixture.repo / 'acceptance.json').write_text(json.dumps({
                        'schema':'007-framework/acceptance/v1','timeout_s':5,
                        'commands':[[sys.executable,'-c',"from pathlib import Path; assert Path('tracked.py').read_bytes() == b'value = 9\\n'"]]}))
                    cli, command, config = fixture.incomplete_run(name, tail)
                    if name in ('executor-error', 'wrong-candidate'):
                        self.assertEqual(cli.run_task(fixture.repo, name, fixture.repo / 'outcome.json', command,
                            capture_config_file=config, vault_root=fixture.vault), (7, None))
                    else:
                        with self.assertRaises(ValueError):
                            cli.run_task(fixture.repo, name, fixture.repo / 'outcome.json', command,
                                capture_config_file=config, vault_root=fixture.vault)
                    start = json.loads((fixture.repo / '.007/tasks' / (name + '.task.json')).read_bytes())
                    marker = json.loads((fixture.repo / '.007/project.json').read_bytes())
                    case = (fixture.vault / start['replay_ref']['manifest']).parent
                    result_before = (case / 'result.json').read_bytes()
                    observation_before = (case / 'outputs/receipt.json').read_bytes()
                    observation = json.loads(observation_before)
                    self.assertEqual(observation['observation_kind'], 'execution-incomplete')
                    self.assertNotIn('status', observation)
                    self.assertIsNone(observation['cost_usd'])
                    self.assertFalse((fixture.repo / '.007/receipts' / (name + '.receipt.json')).exists())
                    task = {'id':name,'source_task_id':name,'project_id':marker['project_id'],
                            'replay_ref':start['replay_ref'],'result_sha256':hashlib.sha256(result_before).hexdigest(),
                            'class':'implement','family':name,'split':'calibration'}
                    fixture.repo.rename(fixture.root / 'original-unavailable')
                    row = replay.admit_dataset([task], vault_root=fixture.vault)['cases'][0]
                    self.assertTrue(row['admitted'])
                    self.assertTrue(row['retained_case'])
                    self.assertFalse(row['replay_ready'])
                    checkpoint = fixture.root / 'curation/checkpoint.json'
                    first = replay.curate_dataset([task], vault_root=fixture.vault, checkpoint=checkpoint)
                    self.assertTrue(first['complete'])
                    self.assertEqual(first['delta_ids'], [name])
                    self.assertFalse(replay.curate_dataset([task], vault_root=fixture.vault, checkpoint=checkpoint)['changed'])
                    checked = replay.admit_dataset([task], vault_root=fixture.vault, recheck=True)['cases'][0]
                    self.assertEqual(checked['replay_ready'], oracle_passes)
                    self.assertEqual(checked['oracle_exits'], [[0],[0]] if oracle_passes else [[1],[1]])
                    self.assertFalse(checked['causal_eligible'])
                    self.assertFalse(checked['economic_eligible'])
                    self.assertEqual((case / 'result.json').read_bytes(), result_before)
                    self.assertEqual((case / 'outputs/receipt.json').read_bytes(), observation_before)
                finally:
                    fixture.doCleanups()

    def test_corrupted_incomplete_candidate_is_excluded_before_explicit_oracle(self):
        fixture = fixtures.ReplayCaptureTests(methodName='runTest')
        fixture.setUp()
        try:
            cli, command, config = fixture.incomplete_run('corrupt', 'raise SystemExit(7)')
            self.assertEqual(cli.run_task(fixture.repo, 'corrupt', fixture.repo / 'outcome.json', command,
                capture_config_file=config, vault_root=fixture.vault), (7,None))
            start = json.loads((fixture.repo / '.007/tasks/corrupt.task.json').read_bytes())
            marker = json.loads((fixture.repo / '.007/project.json').read_bytes())
            case = (fixture.vault / start['replay_ref']['manifest']).parent
            (case / 'outputs/files/tracked.py').write_bytes(b'corrupt')
            task = {'id':'corrupt','project_id':marker['project_id'],'replay_ref':start['replay_ref'],
                    'class':'implement','family':'corrupt','split':'calibration'}
            row = replay.admit_dataset([task], vault_root=fixture.vault,recheck=True)['cases'][0]
            self.assertFalse(row['admitted'])
            self.assertFalse(row['replay_ready'])
            self.assertEqual(row['oracle_exits'], [])
            self.assertIn('retained-source-invalid', row['exclusions'])
        finally:
            fixture.doCleanups()
