"""Frozen public bytes: controller calibration, not native generation or ROI."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).parent))
import test_dataset_admission as fixtures
import test_roi_accounting as economics_fixtures
from replay_budget import ReplayBudget

FIXTURE = Path(__file__).parent / 'fixtures/semantic-replay.tar.gz'
FIXTURE_SHA = 'c15a598d5f09258aa8907d5725e446f19631af8b60f5a66a08954a775b89797c'


def corpus_bytes(payload):
    if hashlib.sha256(payload).hexdigest() != FIXTURE_SHA:
        raise ValueError('public replay corpus hash mismatch')
    with tarfile.open(fileobj=io.BytesIO(payload),mode='r:gz') as archive:
        return {member.name:archive.extractfile(member).read() for member in archive.getmembers()}


class PublicReplayCorpusTests(unittest.TestCase):
    def test_static_corpus_has_literal_controls_and_stable_full_decisions(self):
        payload = FIXTURE.read_bytes()
        members = corpus_bytes(payload)
        config = json.loads(members['set.json'])
        receipts = json.loads(members['receipts.json'])
        starts = json.loads(members['starts.json'])
        outputs = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for repetition in range(3):
                vault = root / f'vault-{repetition}'
                vault.mkdir(mode=0o700)
                for name,data in members.items():
                    if not name.startswith('project/'):
                        continue
                    destination = vault / name
                    fixtures.capture._private_dir(destination.parent)
                    fixtures.capture.write_bytes_no_replace(destination,data,'synthetic corpus')
                restored, exits = {}, {}
                for task in config['tasks']:
                    identifier = task['source_task_id']
                    inventories, task_exits = [], []
                    for index in range(2):
                        target = root / f'{repetition}-{identifier}-{index}'
                        fixtures.capture.restore_candidate(vault,'project',identifier,task['replay_ref'],target)
                        inventories.append({str(p.relative_to(target)):{
                            'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                            'mode':p.stat().st_mode & 0o777} for p in target.rglob('*') if p.is_file()})
                        contract = json.loads((target / 'acceptance.json').read_bytes())
                        task_exits.append([fixtures.replay.run(command,cwd=target,timeout=5).returncode
                                           for command in contract['commands']])
                    self.assertEqual(inventories[0],inventories[1])
                    restored[identifier], exits[identifier] = inventories[0], task_exits
                self.assertEqual(exits,{'task':[[0],[0]],'guarded':[[1],[1]]})
                admission = fixtures.replay.admit_dataset(config['tasks'],vault_root=vault)
                self.assertEqual(admission['counts']['retained'],2)
                self.assertEqual(admission['counts']['qualified-comparison'],0)
                schedule = list(fixtures.replay.experiment_schedule(
                    {'seed':config['seed'],'tasks':[config['tasks'][0]]},['OLD','NEW'],3).values())
                self.assertEqual(schedule,[['NEW','OLD'],['OLD','NEW'],['NEW','OLD']])
                budget = ReplayBudget.create(root / f'{repetition}.sqlite',
                    protocol_sha256=hashlib.sha256(members['set.json']).hexdigest(),cost_basis='api-equivalent',
                    prior_costs={'executor_cells':0,'independent_review':0,'contingency':0},
                    prior_costs_source_sha256=hashlib.sha256(b'synthetic prior spend = 0').hexdigest())
                cost_hash = hashlib.sha256(members['receipts.json']).hexdigest()
                for row in receipts:
                    budget.reserve(row['task_id'],'executor_cells',row['cost_usd'],bound_source_sha256=cost_hash)
                    budget.settle(row['task_id'],row['cost_usd'],cost_basis='api-equivalent',source_sha256=cost_hash)
                state = budget.snapshot()
                self.assertEqual((state['spent_usd'],state['remaining_usd']),(10,20))
                with self.assertRaises(ValueError):
                    budget.reserve('third','executor_cells',0.01,bound_source_sha256=cost_hash)
                economics = economics_fixtures.report.summarize_economics(receipts,starts=starts,
                    followups=[],cost_basis='api-equivalent',as_of=economics_fixtures.AS_OF)
                self.assertEqual(economics['cost_usd_per_declared_accepted'],10)
                self.assertIsNone(economics['cost_usd_per_reliable_declared'])
                outputs.append({'restored':restored,'oracle_exits':exits,'admission':admission,
                    'schedule':schedule,'budget':state,'economics':economics})
                changed = vault / 'project/task/outputs/files/tracked.py'
                changed.write_bytes(b'value = 9\n')
                rejected = fixtures.replay.admit_dataset([config['tasks'][0]],vault_root=vault,recheck=True)
                self.assertEqual(rejected['counts']['excluded'],1)
                self.assertEqual(rejected['cases'][0]['oracle_exits'],[])
        canonical = [json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False) for value in outputs]
        self.assertEqual(canonical,[canonical[0]] * 3)
        scope_fields = {'cost_scope_complete', 'cost_component_known_tasks', 'cost_scope_reasons',
                        'cost_usd_per_declared_accepted_with_overhead',
                        'cost_usd_per_reliable_with_overhead_declared'}
        for value in outputs:
            economics = value['economics']
            self.assertFalse(economics['cost_scope_complete'])
            self.assertEqual(economics['cost_component_known_tasks'], {
                'executor':0,'review':0,'retries':0,'verification':0,'infrastructure':0,'preparation':0})
            self.assertEqual(economics['cost_scope_reasons'], ['incomplete overhead cost scope'])
            self.assertIsNone(economics['cost_usd_per_declared_accepted_with_overhead'])
            self.assertIsNone(economics['cost_usd_per_reliable_with_overhead_declared'])
        legacy = {**outputs[0], 'economics': {k:v for k,v in outputs[0]['economics'].items() if k not in scope_fields}}
        legacy_canonical = json.dumps(legacy,sort_keys=True,separators=(',',':'),allow_nan=False)
        self.assertEqual(hashlib.sha256(legacy_canonical.encode()).hexdigest(),
                         'f68d412bf032303715aeda3f9b8a4713bc9ef2ba04357e19b38898b8eb2d8006')
        self.assertEqual(FIXTURE.read_bytes(),payload)
        print(json.dumps({'proof':'static-synthetic-controller-only','corpus_sha256':FIXTURE_SHA,
            'canonical_sha256':hashlib.sha256(canonical[0].encode()).hexdigest(),
            'repetitions':3,'economic_roi':None},sort_keys=True))

    def test_corrupt_corpus_is_rejected_before_decompression(self):
        payload = FIXTURE.read_bytes()
        with mock.patch.object(tarfile,'open',side_effect=AssertionError('decompression forbidden')):
            with self.assertRaisesRegex(ValueError,'corpus hash mismatch'):
                corpus_bytes(payload[:-1] + bytes([payload[-1] ^ 1]))

    def test_native_recheck_keeps_its_exact_runtime_requirement(self):
        members = corpus_bytes(FIXTURE.read_bytes())
        config = json.loads(members['set.json'])
        with tempfile.TemporaryDirectory() as temporary:
            vault = Path(temporary).resolve() / 'vault'
            vault.mkdir(mode=0o700)
            for name,data in members.items():
                if name.startswith('project/'):
                    path = vault / name
                    fixtures.capture._private_dir(path.parent)
                    fixtures.capture.write_bytes_no_replace(path,data,'synthetic corpus')
            with mock.patch.object(fixtures.replay,'run',side_effect=AssertionError('wrong runtime executed')):
                if sys.version.split()[0] != '3.11.15':
                    result = fixtures.replay.admit_dataset(config['tasks'],vault_root=vault,recheck=True)
                    for row in result['cases']:
                        self.assertEqual(row['oracle_exits'],[])
                        self.assertIn('runtime-version-mismatch',row['gaps'])
            if sys.version.split()[0] == '3.11.15':
                result = fixtures.replay.admit_dataset(config['tasks'],vault_root=vault,recheck=True)
                exits = {row['id']:row['oracle_exits'] for row in result['cases']}
                self.assertEqual(exits,{'case':[[0],[0]],'guarded':[[1],[1]]})
