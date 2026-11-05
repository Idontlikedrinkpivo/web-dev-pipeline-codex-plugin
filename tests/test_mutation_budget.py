"""Validate bounded mutation scope before any config/manifest is generated."""
import copy
import importlib.util
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'dev-pipeline/skills/work/scripts/mutation_config.py'
SPEC = importlib.util.spec_from_file_location('budget_mutation_config', SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class MutationBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name).resolve()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        self.env = dict(os.environ, CODEX_HOME=str(self.repo / 'home'), CODEX_THREAD_ID='fixture',
                        PYTHONDONTWRITEBYTECODE='1')
        self.out = MOD.resolve_paths(self.repo, '1.0.0', 'fixture').local / 'mutation'

    def spec(self):
        return {'version': '1.0.0', 'budget': {'seconds': 60, 'workers': 2},
                'risk_scope': {'mandatory': ['src/rules.ts:10-20'], 'optional': ['src/ui.ts:1-50']},
                'parts': [{'name': 'Rules', 'mutate': ['src/rules.ts:10-20'], 'concurrency': 1}]}

    def cli(self, spec):
        path = self.repo / 'spec.json'
        path.write_text(json.dumps(spec))
        return subprocess.run([sys.executable, str(SCRIPT), str(path)], cwd=self.repo,
                              env=self.env, text=True, capture_output=True)

    def test_mandatory_skip_without_cancellation_refused_before_generation(self):
        spec = self.spec()
        spec['parts'][0]['skip'] = 'too slow'
        result = self.cli(spec)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('mandatory', result.stderr)
        self.assertFalse(self.out.exists())

    def test_optional_narrowing_never_removes_mandatory_union(self):
        for optional in ([], ['src/ui.ts:1-10'], ['src/ui.ts:1-50']):
            for cuts in ((10, 20), (10, 15, 16, 20), (10, 12, 13, 17, 18, 20)):
                spec = self.spec()
                scopes = [f'src/rules.ts:{start}-{end}' for start, end in zip(cuts[::2], cuts[1::2])]
                spec['parts'][0]['mutate'] = scopes + optional
                self.assertEqual(MOD.validate(spec)['status'], 'planned')
                self.assertEqual(MOD.uncovered(spec['risk_scope']['mandatory'], scopes), [])
        spec = self.spec()
        spec['parts'][0]['mutate'] = ['src/rules.ts:10-19']
        with self.assertRaisesRegex(ValueError, 'mandatory'):
            MOD.validate(spec)

    def test_user_cancellation_has_reason_uncovered_ranges_and_no_commands(self):
        spec = self.spec()
        spec['parts'][0].update(status='SKIPPED BY USER', user_cancelled=True, reason='User cancelled mutations')
        result = self.cli(spec)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((self.out / 'parts.json').read_text())
        self.assertEqual(manifest['policy']['status'], 'SKIPPED BY USER')
        self.assertEqual(manifest['policy']['uncovered_ranges'], ['src/rules.ts:10-20'])
        self.assertNotIn('budget exhausted', json.dumps(manifest))
        self.assertEqual(manifest['parts'][0]['skip'], 'User cancelled mutations')
        self.assertFalse(list(self.out.glob('*.stryker.mjs')))
        self.assertIn('remaining gates', manifest['policy']['next_action'])

    def test_budget_exhaustion_and_unavailable_runner_are_not_pass(self):
        for extra, status in (({'elapsed_seconds': 60}, 'incomplete'),
                              ({'runner_available': False}, 'not-run')):
            spec = self.spec()
            spec.update(extra)
            result = self.cli(spec)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((self.out / 'parts.json').read_text())
            self.assertEqual(manifest['policy']['status'], status)
            self.assertEqual(manifest['policy']['uncovered_ranges'], ['src/rules.ts:10-20'])
            self.assertTrue(manifest['policy']['next_action'])
            self.assertFalse(list(self.out.glob('*.stryker.mjs')))

    def test_malformed_budget_scope_status_and_equivalent_reason_refused(self):
        changes = [({'seconds': -1, 'workers': 1}, None), ({'seconds': 60, 'workers': 0}, None),
                   ({'seconds': True, 'workers': 1}, None), ({'seconds': 60, 'workers': 1}, 'PASS'),
                   (-1, None)]
        for budget, status in changes:
            spec = self.spec()
            spec['budget'] = budget
            if status:
                spec['parts'][0]['status'] = status
            with self.assertRaises(ValueError):
                MOD.validate(spec)
        for bad in ('src/rules.ts:-1-20', '../escape.ts:1-2', 'src/rules.ts:30-10'):
            spec = self.spec()
            spec['risk_scope']['mandatory'] = [bad]
            with self.assertRaises(ValueError):
                MOD.validate(spec)
        spec = self.spec()
        spec['equivalent_mutants'] = [{'id': 'M1', 'reason': ''}]
        with self.assertRaisesRegex(ValueError, 'evidence'):
            MOD.validate(spec)
        spec['equivalent_mutants'] = [{'id': 'M1', 'reason': 'Same result for all valid input', 'evidence': 'Proof in report §2'}]
        self.assertEqual(MOD.validate(spec)['status'], 'planned')

    def test_resource_budget_and_shared_test_database_checks_precede_outputs(self):
        spec = self.spec()
        spec['parts'][0]['concurrency'] = 3
        self.assertNotEqual(self.cli(spec).returncode, 0)
        self.assertFalse(self.out.exists())
        for urls in (('postgresql://a@localhost/app', 'postgresql://b@localhost/test_b'),
                     ('postgresql://a@localhost/app_test', 'postgresql://b@localhost/app_test')):
            spec = self.spec()
            spec['parts'].append(copy.deepcopy(spec['parts'][0]))
            for part, url in zip(spec['parts'], urls):
                part['env'] = {'TEST_DATABASE_URL': url}
            self.assertNotEqual(self.cli(spec).returncode, 0)
            self.assertFalse(self.out.exists())

    def test_legacy_spec_is_readable_but_unbounded_and_sandboxes_remain_isolated(self):
        spec = self.spec()
        spec.pop('risk_scope')
        spec['budget'] = 'legacy freeform budget'
        spec['parts'].append({'name': 'Second', 'mutate': ['src/b.ts:1-2']})
        result = self.cli(spec)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((self.out / 'parts.json').read_text())
        self.assertEqual(manifest['policy']['status'], 'legacy/unbounded')
        configs = [path.read_text() for path in self.out.glob('*.stryker.mjs')]
        self.assertEqual(len(configs), 2)
        self.assertTrue(all('"inPlace": false' in config for config in configs))
        self.assertNotEqual(manifest['parts'][0]['log'], manifest['parts'][1]['log'])

    def test_partial_user_cancellation_preserves_remaining_required_scope(self):
        spec = self.spec()
        spec['parts'][0]['mutate'] = ['src/rules.ts:10-15']
        spec['parts'].append({'name': 'Cancelled', 'mutate': ['src/rules.ts:16-20'],
                              'status': 'SKIPPED BY USER', 'user_cancelled': True, 'reason': 'Explicit cancellation'})
        self.assertEqual(MOD.validate(spec)['uncovered_ranges'], ['src/rules.ts:16-20'])
        spec['parts'][1].pop('user_cancelled')
        with self.assertRaisesRegex(ValueError, 'explicit'):
            MOD.validate(spec)


if __name__ == '__main__':
    unittest.main()
