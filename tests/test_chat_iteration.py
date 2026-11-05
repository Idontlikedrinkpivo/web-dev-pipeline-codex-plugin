import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_close_iteration_stamp import RepoTest, PIPE, close, load

opening = load('opening_small_tests', PIPE / 'open_iteration.py')


class SmallIterationTests(RepoTest):
    def open(self, *args):
        return subprocess.run([sys.executable, str(PIPE / 'open_iteration.py'), *args, str(self.root), '--small'],
                              capture_output=True, text=True)

    def test_no_plan_concrete_patch_trailer_and_idempotent_reuse(self):
        self.git('tag', 'v1.2.3')
        result = self.open()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Plan-Unit: 1.2.4/chat-1', result.stdout)
        marker = self.root / 'documentation/plans/1.2.4/iteration.json'
        original = marker.read_bytes()
        self.assertEqual(json.loads(original)['mode'], 'small')
        self.assertFalse((marker.parent / 'plan.md').exists())
        self.assertEqual(self.open().returncode, 0)
        self.assertEqual(marker.read_bytes(), original)
        self.assertEqual(self.git('tag'), 'v1.2.3')

    def test_conflicting_version_malformed_metadata_and_missing_base_no_mutation(self):
        before = self.git('status', '--porcelain')
        self.assertEqual(self.open().returncode, 2)
        self.assertEqual(self.git('status', '--porcelain'), before)
        self.assertEqual(self.open('1.0.1').returncode, 0)
        branch = self.git('branch', '--show-current')
        self.assertEqual(self.open('2.0.0').returncode, 2)
        self.assertEqual(self.git('branch', '--show-current'), branch)
        marker = self.root / 'documentation/plans/1.0.1/iteration.json'
        marker.write_text('{broken')
        before = self.git('status', '--porcelain')
        self.assertNotEqual(self.open('1.0.1').returncode, 0)
        self.assertEqual(self.git('status', '--porcelain'), before)
        self.assertEqual(marker.read_text(), '{broken')

    def test_small_requires_results_reviews_tests_and_ui_reason(self):
        self.assertEqual(self.open('1.0.1').returncode, 0)
        marker = self.root / 'documentation/plans/1.0.1/iteration.json'
        data = json.loads(marker.read_text())
        self.assertFalse(close.small_gate(self.root, data)[0])
        head = self.git('rev-parse', 'HEAD')
        data['result'] = {'scope': ['source.py'], 'head': head, 'affected_tests': ['unittest: PASS'],
                          'unit_review': {'head': head, 'status': 'PASS'},
                          'full_review': {'head': head, 'status': 'PASS'},
                          'ui': {'applicable': False, 'reason': 'command parser only'}}
        self.assertTrue(close.small_gate(self.root, data)[0])
        for key in ('affected_tests', 'unit_review', 'full_review'):
            copy = json.loads(json.dumps(data))
            del copy['result'][key]
            self.assertFalse(close.small_gate(self.root, copy)[0], key)
        data['result']['ui']['reason'] = ''
        self.assertFalse(close.small_gate(self.root, data)[0])

    def test_normal_iteration_reused_without_small_mode(self):
        self.git('switch', '-q', '-c', 'iteration/1.0.1')
        self.write('documentation/plans/1.0.1/plan.md', '# Real plan\n')
        result = self.open()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('normal planned iteration', result.stdout)
        self.assertFalse((self.root / 'documentation/plans/1.0.1/iteration.json').exists())

    def reviewed_metadata(self):
        self.write('source.py', 'reviewed source\n')
        self.commit('fix: settled small implementation')
        self.assertEqual(self.open('1.0.1').returncode, 0)
        marker = self.root / 'documentation/plans/1.0.1/iteration.json'
        data = json.loads(marker.read_text())
        head = self.git('rev-parse', 'HEAD')
        data['result'] = {'scope': ['source.py'], 'head': head, 'affected_tests': ['unittest: PASS'],
                          'unit_review': {'head': head, 'status': 'PASS'},
                          'full_review': {'head': head, 'status': 'PASS'},
                          'ui': {'applicable': False, 'reason': 'command parser only'}}
        marker.write_text(json.dumps(data))
        return data

    def test_committed_small_report_reuses_reviews_but_source_or_dirty_code_blocks(self):
        data = self.reviewed_metadata()
        tested = data['result']['head']
        self.write('documentation/plans/1.0.1/work-run.md', 'Both reviews and tests passed\n')
        self.commit('docs: preserve small result and reviews')
        self.assertNotEqual(self.git('rev-parse', 'HEAD'), tested)
        self.assertTrue(close.small_gate(self.root, data)[0])
        self.assertEqual(data['result']['unit_review']['head'], tested)
        self.write('unrelated.py', 'dirty code outside result scope\n')
        self.assertFalse(close.small_gate(self.root, data)[0])
        (self.root / 'unrelated.py').unlink()
        self.write('source.py', 'changed source\n')
        self.commit('fix: source changed after review')
        self.assertFalse(close.small_gate(self.root, data)[0])
        self.write('source.py', 'reviewed source\n')
        self.commit('fix: restored source is still new review history')
        self.assertFalse(close.small_gate(self.root, data)[0])

    def test_small_reviews_reject_identical_scope_on_sibling_history(self):
        data = self.reviewed_metadata()
        tested = data['result']['head']
        self.commit('docs: preserve result before switching fixture history')
        self.git('switch', '-q', '-c', 'other-history', tested + '^')
        self.git('checkout', tested, '--', '.')
        self.commit('fix: same reviewed source on unrelated history')
        self.assertFalse(close.small_gate(self.root, data)[0])


if __name__ == '__main__':
    import unittest
    unittest.main()
