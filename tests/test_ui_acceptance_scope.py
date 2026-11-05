import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_close_iteration_stamp import RepoTest, ROOT, load, close

scope = load('ui_acceptance_tests', ROOT / 'dev-pipeline/skills/ui-test-cases/scripts/acceptance_scope.py')


class AcceptanceTests(RepoTest):
    def setUp(self):
        super().setUp()
        self.write('src/api.py', 'old\n')
        self.write('src/view.py', 'old\n')
        self.write('cases/one.md', 'one\n')
        self.write('cases/two.md', 'two\n')
        self.mapping = {'cases': [
            {'id': 'one', 'path': 'cases/one.md', 'screens': ['screen'], 'operations': ['op-one']},
            {'id': 'two', 'path': 'cases/two.md', 'screens': ['other'], 'operations': ['op-two']}],
            'changes': {'screens': {'src/view.py': ['screen']}, 'operations': {'src/api.py': ['op-one']}},
            'prior_failures': ['two']}
        self.save_mapping()
        self.commit('initial case universe and implementation')
        self.base = self.git('rev-parse', 'HEAD')
        self.git('switch', '-q', '-c', 'iteration/1.0.1')

    def save_mapping(self):
        self.write('documentation/ui/mapping.json', json.dumps(self.mapping))

    def select(self):
        return scope.select(self.root, self.base, 'documentation/ui/mapping.json')

    def passed(self):
        return scope.record(self.root, self.select(), 'full', 'pass', 'actual fixture run evidence', 'fixture-driver', 'http://fixture.invalid')

    def test_changed_operation_union_previous_failure_and_reasons(self):
        self.write('src/api.py', 'changed operation\n')
        manifest = self.select()
        self.assertEqual(set(manifest['selected']), {'one', 'two'})
        self.assertIn('operations', manifest['selected']['one'][0])
        self.assertEqual(manifest['selected']['two'], ['previous failure'])

    def test_monotone_union_and_added_case(self):
        before = set(self.select()['selected'])
        self.write('src/view.py', 'changed screen\n')
        after = self.select()
        self.assertTrue(before <= set(after['selected']))
        self.mapping['cases'].append({'id': 'three', 'path': 'cases/three.md'})
        self.write('cases/three.md', 'new\n')
        self.save_mapping()
        final = self.select()
        self.assertTrue(set(after['selected']) <= set(final['selected']))
        self.assertIn('three', final['selected'])
        self.assertTrue(all(final['selected'].values()))

    def test_unknown_mapping_expands_full_and_missing_mapping_blocks(self):
        self.write('src/unmapped.py', 'unknown\n')
        manifest = self.select()
        self.assertEqual(set(manifest['selected']), set(manifest['universe']))
        missing = scope.select(self.root, self.base, None)
        self.assertEqual(missing['blocked'], 'mapping unavailable')
        with self.assertRaises(ValueError):
            scope.record(self.root, missing, 'full', 'pass', 'evidence', 'tool', 'stand')

    def test_code_and_full_case_universe_invalidate_full(self):
        manifest = self.passed()
        self.assertTrue(scope.check(self.root, manifest)[0])
        self.write('src/api.py', 'new code\n')
        self.assertFalse(scope.check(self.root, manifest)[0])
        manifest = self.passed()
        self.write('cases/two.md', 'changed unselected case\n')
        self.assertFalse(scope.check(self.root, manifest)[0])
        manifest = self.passed()
        self.mapping['cases'].append({'id': 'new', 'path': 'cases/new.md'})
        self.save_mapping()
        self.assertFalse(scope.check(self.root, manifest)[0])

    def test_full_reuse_once_selected_insufficient_and_head_stale(self):
        manifest = self.select()
        scope.record(self.root, manifest, 'selected', 'pass', 'selected output', 'tool', 'stand')
        self.assertFalse(scope.check(self.root, manifest)[0])
        scope.record(self.root, manifest, 'full', 'pass', 'full output', 'tool', 'stand')
        scope.record(self.root, manifest, 'full', 'pass', 'full output', 'tool', 'stand')
        self.assertEqual(sum(r['scope'] == 'full' for r in manifest['runs']), 1)
        self.assertTrue(scope.check(self.root, manifest)[0])
        self.commit('new HEAD invalidates previous run')
        self.assertFalse(scope.check(self.root, manifest)[0])

    def test_malformed_legacy_no_ui_and_missing_prerequisites(self):
        for manifest in ({}, {'schema_version': 1}, {'legacy': 'PASS'}):
            self.assertFalse(scope.check(self.root, manifest)[0])
        manifest = self.select()
        with self.assertRaises(ValueError):
            scope.record(self.root, manifest, 'full', 'pass', 'evidence')
        scope.record(self.root, manifest, 'full', 'not-run', 'browser unavailable')
        self.assertFalse(scope.check(self.root, manifest)[0])
        scope.record(self.root, manifest, 'full', 'pass', 'parser-only scope reviewed', no_ui_reason='CLI project has no UI')
        self.assertTrue(scope.check(self.root, manifest)[0])
        manifest['applicability']['reason'] = ''
        self.assertFalse(scope.check(self.root, manifest)[0])

    def test_close_acceptance_gate_uses_manifest_and_fingerprint(self):
        folder = self.root / 'documentation/plans/1.0.1'
        folder.mkdir(parents=True)
        self.assertFalse(close.acceptance_gate(self.root, folder)[0])
        manifest = self.passed()
        (folder / 'ui-acceptance.json').write_text(json.dumps(manifest))
        self.assertTrue(close.acceptance_gate(self.root, folder)[0])
        self.write('src/view.py', 'changed again\n')
        self.assertFalse(close.acceptance_gate(self.root, folder)[0])

    def test_real_report_commit_preserves_tested_sha_but_source_history_does_not(self):
        manifest = self.passed()
        tested = manifest['head']
        folder = self.root / 'documentation/plans/1.0.1'
        self.write('documentation/plans/1.0.1/ui-acceptance.json', json.dumps(manifest))
        self.write('documentation/plans/1.0.1/work-run.md', 'Full acceptance observed\n')
        self.commit('docs: preserve acceptance report after checks')
        self.assertNotEqual(self.git('rev-parse', 'HEAD'), tested)
        self.assertTrue(scope.check(self.root, manifest)[0])
        self.assertTrue(close.acceptance_gate(self.root, folder)[0])
        self.assertEqual(manifest['head'], tested)
        self.assertEqual(manifest['runs'][0]['head'], tested)
        self.write('src/api.py', 'dirty source\n')
        self.assertFalse(scope.check(self.root, manifest)[0])
        self.commit('fix: source changed after acceptance')
        self.assertFalse(scope.check(self.root, manifest)[0])
        self.write('src/api.py', 'old\n')
        self.commit('fix: restore source bytes after intervening change')
        self.assertEqual(scope.fingerprints(self.root, manifest['mapping'])[0], manifest['fingerprints'])
        self.assertFalse(scope.check(self.root, manifest)[0])

    def test_identical_code_on_non_descendant_does_not_reuse_acceptance(self):
        manifest = self.passed()
        self.git('switch', '-q', '-c', 'unrelated-review', self.base + '^')
        self.git('checkout', self.base, '--', '.')
        self.commit('chore: identical source on a sibling history')
        self.assertEqual(scope.fingerprints(self.root, manifest['mapping'])[0], manifest['fingerprints'])
        self.assertFalse(scope.check(self.root, manifest)[0])

    def test_arbitrary_plan_files_and_other_iteration_reports_are_not_report_proof(self):
        for path in ('documentation/plans/1.0.1/source.py', 'documentation/plans/2.0.0/work-run.md'):
            with self.subTest(path=path):
                manifest = self.passed()
                self.write(path, 'not a report of the reviewed iteration\n')
                self.commit('docs: file outside recognized current report scope')
                self.assertEqual(scope.fingerprints(self.root, manifest['mapping'])[0], manifest['fingerprints'])
                self.assertFalse(scope.check(self.root, manifest)[0])


if __name__ == '__main__':
    import unittest
    unittest.main()
