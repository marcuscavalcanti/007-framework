"""Sanitized curation consumption; polling never reruns admission or an oracle."""
import hashlib
import json
from unittest import TestCase, mock
import test_dataset_admission as fixtures
import dashboard
import framework_cli as cli


class CurationDashboardTests(TestCase):
    def setUp(self):
        self.fixture = fixtures.DatasetTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.vault = self.fixture.root, self.fixture.vault
        self.checkpoint = self.root / 'curation/checkpoint.json'
        self.value = fixtures.replay.curate_dataset([self.fixture.task], vault_root=self.vault, checkpoint=self.checkpoint)

    def collector(self):
        self.assertTrue(hasattr(dashboard, 'CurationCollector'), 'curation projection is missing')
        return dashboard.CurationCollector(self.checkpoint, self.vault)

    def test_declared_followups_project_counts_without_source_text_or_live_recheck(self):
        refs = []
        for changes in ({"corrective_lines": 9, "escape_7d": "yes"},
                        {"corrective_lines": 0, "escape_7d": "no"}):
            event = {"project_id": "project", "task_id": "task",
                     "input_sha256": self.fixture.ref["sha256"],
                     "result_sha256": hashlib.sha256(self.fixture.result.read_bytes()).hexdigest(),
                     "observed_at": "2026-10-12T12:00:00Z", "description": "PRIVATE FOLLOWUP", **changes}
            payload = fixtures.capture._json_bytes(event)
            digest = hashlib.sha256(payload).hexdigest()
            name = f"followup-{digest}.json"
            fixtures.capture.write_bytes_no_replace(self.fixture.result.parent / name, payload, "fixture")
            refs.append({"manifest": f"project/task/{name}", "sha256": digest})
        task = {**self.fixture.task, "followup_refs": refs}
        fixtures.replay.curate_dataset([task], vault_root=self.vault, checkpoint=self.checkpoint)
        read = self.collector()
        with mock.patch.object(fixtures.replay, 'admit_dataset', side_effect=AssertionError('admission forbidden')):
            good = read()
            self.assertEqual(good, read())
        counts = good["counts"]
        self.assertEqual(counts.get("followup_sources"), 2)
        self.assertEqual(counts.get("followup_cases"), 1)
        self.assertEqual(counts.get("corrected_cases_declared"), 1)
        self.assertEqual(counts.get("escaped_cases_declared"), 1)
        self.assertEqual(good["by_project"]["project"], counts)
        serialized = json.dumps(good)
        for private in ("PRIVATE FOLLOWUP", "declared_followups", refs[0]["sha256"]):
            self.assertNotIn(private, serialized)
        self.checkpoint.write_bytes(b"broken")
        failed = read()
        self.assertTrue(failed["stale"])
        self.assertEqual(failed["counts"], counts)

    def test_proposals_project_only_kind_hash_and_keep_stale_and_project_scope(self):
        value = {"project_id":"project","task_id":"task","input_sha256":self.fixture.ref['sha256'],
            "result_sha256":hashlib.sha256(self.fixture.result.read_bytes()).hexdigest(),
            "kind":"gate","status":"proposed","mechanism":"PRIVATE MECHANISM",
            "evidence":"PRIVATE EVIDENCE","counterproof":"Private mutant",
            "positive_control":"Private control","experiment":"Private future experiment"}
        raw = fixtures.capture._json_bytes(value)
        digest = hashlib.sha256(raw).hexdigest()
        ref = {"manifest":f"project/task/hypothesis-{digest}.json","sha256":digest}
        fixtures.capture.write_bytes_no_replace(self.vault/ref['manifest'],raw,'fixture hypothesis')
        fixtures.replay.curate_dataset([{**self.fixture.task,'hypothesis_refs':[ref]}],
            vault_root=self.vault,checkpoint=self.checkpoint)
        read = self.collector()
        with mock.patch.object(fixtures.replay,'admit_dataset',side_effect=AssertionError('admission forbidden')):
            good = read()
            self.assertEqual(good,read())
        self.assertEqual(good.get('proposals'), [{'kind':'gate','source_sha256':digest}])
        self.assertEqual(good['counts']['gate_hypotheses_declared'],1)
        self.assertEqual(good['counts']['routing_hypotheses_declared'],0)
        self.assertNotIn('PRIVATE',json.dumps(good))
        self.assertNotIn('case_id',json.dumps(good))
        entries = [{'project_id':key,'name':'Fixture','path':str(self.fixture.repo),'registered_at':'x'}
                   for key in ('project','foreign')]
        registry = self.root/'registry.json'
        cli.write_json_atomic(registry,{'schema':cli.REGISTRY_SCHEMA,'projects':entries})
        snapshot = dashboard.build_snapshot(registry,lambda *_:dashboard.unknown_touch(30,'fixture'),
            lambda _: {'aggregate':{},'projects':{},'errors':[]},curation_provider=read)
        self.assertEqual(snapshot['projects'][0]['curation']['proposals'],good['proposals'])
        self.assertEqual(snapshot['projects'][1]['curation']['proposals'],[])
        self.assertNotIn('proposals_by_project',json.dumps(snapshot))
        forged = json.loads(self.checkpoint.read_bytes())
        shadow = {**forged['admission']['cases'][0],'id':'shadow','project_id':'foreign'}
        forged['admission']['cases'].append(shadow)
        forged['admission']['proposal_delta'][0]['case_id'] = 'shadow'
        forged['admission']['counts'] = fixtures.replay.dataset_counts(forged['admission']['cases'])
        content = {key:forged[key] for key in ('vault_sha256','verifier_sha256','admission')}
        forged['checkpoint_sha256'] = hashlib.sha256(fixtures.capture._json_bytes(content)).hexdigest()
        self.checkpoint.write_bytes(fixtures.capture._json_bytes(forged))
        rejected = read()
        self.assertTrue(rejected['stale'])
        self.assertEqual(rejected['proposals'],good['proposals'])
        self.assertEqual(rejected['counts'],good['counts'])
        self.checkpoint.write_bytes(b'broken')
        stale = read()
        self.assertTrue(stale['stale'])
        self.assertEqual(stale['proposals'],good['proposals'])

    def test_polling_reads_only_the_checkpoint_and_preserves_bounded_claims(self):
        before = self.checkpoint.read_bytes()
        read = self.collector()
        with (mock.patch.object(fixtures.replay, 'admit_dataset', side_effect=AssertionError('admission forbidden')),
              mock.patch.object(fixtures.capture, 'qualify_case', side_effect=AssertionError('corpus walk forbidden')),
              mock.patch.object(fixtures.replay, 'run', side_effect=AssertionError('oracle forbidden'))):
            first, second = read(), read()
        self.assertEqual(first, second)
        self.assertTrue(first['available'])
        self.assertFalse(first['stale'])
        self.assertEqual(first['counts']['retained'], 1)
        self.assertEqual(first['counts']['qualified-comparison'], 0)
        self.assertEqual(first['completed_at'], self.value['completed_at'])
        for private in ('"cases"', str(self.vault), str(self.fixture.repo), 'Preserve this fixture', 'value-fix'):
            self.assertNotIn(private, json.dumps(first))
        self.assertEqual(self.checkpoint.read_bytes(), before)

    def test_denial_and_corruption_keep_last_checkpoint_explicitly_stale(self):
        read = self.collector()
        good = read()
        before = self.checkpoint.read_bytes()
        self.checkpoint.write_bytes(b'broken')
        failed = read()
        self.assertFalse(failed['available'])
        self.assertTrue(failed['stale'])
        self.assertEqual(failed['completed_at'], good['completed_at'])
        self.assertEqual(failed['counts'], good['counts'])
        self.checkpoint.write_bytes(before)
        self.assertEqual(read(), good)

    def test_rehashed_claim_of_causal_promotion_is_not_consumed(self):
        read = self.collector()
        good = read()
        value = json.loads(self.checkpoint.read_bytes())
        row = value['admission']['cases'][0]
        row.update(state='qualified-comparison', causal_eligible=True)
        content = {k: value[k] for k in ('vault_sha256','verifier_sha256','admission')}
        value['checkpoint_sha256'] = hashlib.sha256(fixtures.capture._json_bytes(content)).hexdigest()
        self.checkpoint.write_bytes(fixtures.capture._json_bytes(value))
        result = read()
        self.assertTrue(result['stale'])
        self.assertEqual(result['counts']['qualified-comparison'], 0)
        self.assertEqual(result['checkpoint_sha256'], good['checkpoint_sha256'])

    def test_snapshot_scopes_curation_by_registered_project_not_project_name(self):
        registry = self.root / 'registry.json'
        marker = {'schema':cli.PROJECT_SCHEMA,'project_id':'project','name':'fixture','receipt_dir':'receipts'}
        cli.write_json_atomic(self.fixture.repo / '.007/project.json', marker)
        (self.fixture.repo / '.007/receipts').mkdir()
        entries = [{'project_id':name,'name':'same-name','path':str(self.fixture.repo),'registered_at':'2026-10-13T00:00:00Z'} for name in ('project','unrelated')]
        cli.write_json_atomic(registry, {'schema':cli.REGISTRY_SCHEMA,'projects':entries})
        activity = lambda _: {'aggregate':{}, 'projects':{}, 'errors':[]}
        read = self.collector()
        result = dashboard.build_snapshot(registry, lambda *_: dashboard.unknown_touch(30,'fixture'), activity, curation_provider=read)
        self.assertEqual(result['projects'][0]['curation']['counts']['retained'], 1)
        self.assertFalse(result['projects'][1]['curation']['in_scope'])
        self.assertIsNone(result['projects'][1]['curation']['counts'])
        self.assertNotIn('cases', result['curation'])

    def test_missing_or_unconfigured_checkpoint_is_unknown_not_zero(self):
        self.assertTrue(hasattr(dashboard, 'CurationCollector'), 'curation projection is missing')
        disabled = dashboard.CurationCollector()()
        self.assertFalse(disabled['configured'])
        self.assertIsNone(disabled['counts'])
        self.checkpoint.unlink()
        absent = self.collector()()
        self.assertFalse(absent['available'])
        self.assertIsNone(absent['counts'])

    def test_dashboard_cli_forwards_the_explicit_private_binding(self):
        args = ['dashboard','--no-open','--curation-checkpoint',str(self.checkpoint),'--curation-vault',str(self.vault)]
        with mock.patch.object(cli, 'run_dashboard', return_value=0) as server:
            self.assertEqual(cli.main(args), 0)
        self.assertEqual(server.call_args.kwargs['curation_checkpoint'], self.checkpoint)
        self.assertEqual(server.call_args.kwargs['curation_vault'], self.vault)
