"""Self-contained stamp regressions; never reads installed plugin patch files."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PIPE = ROOT / 'dev-pipeline/skills/pipeline/scripts'


def load(name, path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


close = load('close_for_stamp_tests', PIPE / 'close_iteration.py')


class RepoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'
        self.root.mkdir()
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('commit', '-q', '--allow-empty', '-m', 'initial release base')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], capture_output=True,
                              text=True, check=True).stdout.strip()

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def commit(self, message):
        self.git('add', '.')
        self.git('commit', '-q', '--allow-empty', '-m', message)


class StampTests(RepoTest):
    def setUp(self):
        super().setUp()
        self.path = 'documentation/requirements/srs/srs.md'
        self.body = '---\nversion: 1.0.0\nsources:\n  - requirements/business-requirements/business-requirements.md@1.0.0\n---\n# SRS\nBody\n'
        self.write(self.path, self.body)
        self.commit('docs: SRS 1.0.0 · review: passed')
        self.git('switch', '-q', '-c', 'iteration/1.0.1')

    def pins(self):
        self.body = self.body.replace('@1.0.0', '@1.0.1')
        self.write(self.path, self.body)
        self.commit('docs: refresh source pins because source advanced')

    def test_changed_pins_without_stamp_block(self):
        self.pins()
        ok, why = close.stamp_gate(self.root)
        self.assertFalse(ok)
        self.assertIn('SRS', why)

    def test_no_row_close_preserves_version_and_passes_only_stamp(self):
        self.pins()
        self.commit('docs: SRS 1.0.0 · review: passed')
        self.assertTrue(close.stamp_gate(self.root)[0])
        self.assertIn('version: 1.0.0', (self.root / self.path).read_text())
        result = subprocess.run([sys.executable, str(PIPE / 'close_iteration.py'), str(self.root)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('✅ 1 штамп', result.stdout)
        self.assertIn('✗ 4 метка', result.stdout)

    def test_uncommitted_body_after_stamp_blocks(self):
        self.write(self.path, self.body + 'uncommitted body\n')
        self.assertFalse(close.stamp_gate(self.root)[0])

    def test_new_committed_decision_blocks_until_next_stamp(self):
        self.write(self.path, self.body + 'new accepted decision\n')
        self.commit('docs: accepted decision changes body')
        self.assertFalse(close.stamp_gate(self.root)[0])
        self.commit('docs: SRS 1.0.0 · review: passed')
        self.assertTrue(close.stamp_gate(self.root)[0])

    def test_launch_failure_and_unrecognized_nonzero_fail_closed(self):
        with mock.patch.object(close.subprocess, 'run', side_effect=OSError('launch refused')):
            self.assertEqual(close.stamp_gate(self.root), (False, 'doc_state dirty unavailable: launch refused'))
        result = subprocess.CompletedProcess([], 7, 'unexpected format', 'checker unavailable')
        with mock.patch.object(close.subprocess, 'run', return_value=result):
            ok, why = close.stamp_gate(self.root)
        self.assertFalse(ok)
        self.assertIn('exit 7', why)
        self.assertIn('unexpected format', why)


if __name__ == '__main__':
    unittest.main()
