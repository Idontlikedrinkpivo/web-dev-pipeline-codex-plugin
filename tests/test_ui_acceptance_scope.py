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


if __name__ == '__main__':
    import unittest
    unittest.main()
