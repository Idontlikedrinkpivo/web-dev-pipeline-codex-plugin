"""Proposals never become chat-creation consent through plan/show/resume."""
import importlib.util
import itertools
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'dev-pipeline/skills/pipeline/scripts/subsessions.py'
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location('selection_subsessions', SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class StageSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name).resolve()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        self.env = dict(os.environ, CODEX_HOME=str(self.repo / 'home'), CODEX_THREAD_ID='parent',
                        PYTHONDONTWRITEBYTECODE='1')
        self.path = MOD.resolve_paths(self.repo, '1.0.0', 'parent').local / 'sessions.md'

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), str(self.repo), '1.0.0', *args],
                              env=self.env, capture_output=True, text=True)

    def ok(self, *args):
        result = self.cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_plan_is_not_authorization_and_replan_never_expands_subset(self):
        self.ok('plan', 'work', 'srs', 'api')
        before = self.path.read_bytes()
        self.assertNotEqual(self.cli('set', '1', 'child').returncode, 0)
        self.assertEqual(self.path.read_bytes(), before)
        self.ok('authorize', 'api', 'work')
        selected = self.path.read_bytes()
        for command in (('plan', 'srs', 'api', 'work'), ('show',), ('show',)):
            result = self.ok(*command)
            self.assertIn('srs', result.stdout)
            self.assertEqual(self.path.read_bytes(), selected)
        _, rows = MOD.read(self.path)
        self.assertEqual([r['stage'] for r in rows if r['authorized']], ['api', 'work'])
        self.ok('set', '2', 'child-api')
        self.ok('authorize')
        _, rows = MOD.read(self.path)
        self.assertEqual(rows[1]['id'], 'child-api')
        self.assertFalse(any(r['authorized'] for r in rows))

    def test_plan_refuses_peer_git_environment_without_registry_writes(self):
        peer = self.repo / 'peer'
        subprocess.run(['git', 'init', '-q', str(peer)], check=True)
        for repo in (self.repo, peer):
            (repo / 'file.txt').write_bytes(b'base\n')
            subprocess.run(['git', '-C', str(repo), 'add', 'file.txt'], check=True)
            subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Test',
                            '-c', 'user.email=test@example.com', 'commit', '-qm', 'fixture'], check=True)
        self.ok('plan', 'work')
        peer_registry = MOD.resolve_paths(peer, '1.0.0', 'parent').local / 'sessions.md'
        MOD.write(peer_registry, '1.0.0', 'parent', MOD.rows_for('1.0.0', 'srs'))

        def snapshot():
            return {p.relative_to(self.repo).as_posix(): p.read_bytes()
                    for p in self.repo.rglob('*') if p.is_file()}

        before = snapshot()
        self.env.update(GIT_DIR=str(peer / '.git'), GIT_WORK_TREE=str(peer))
        result = self.cli('plan', 'audit')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Git repository overrides', result.stderr)
        self.assertEqual(snapshot(), before)

    def test_every_subset_preserves_canonical_numbers_order_and_roundtrip(self):
        keys = ('srs', 'api', 'work', 'audit')
        for size in range(len(keys) + 1):
            for subset in itertools.combinations(keys, size):
                rows = [dict(MOD.rows_for('1.0.0', key)[0], authorized=key in subset,
                             id='', state='не открыта') for key in keys]
                MOD.write(self.path, '1.0.0', 'parent', rows)
                _, actual = MOD.read(self.path)
                self.assertEqual([r['stage'] for r in actual if r['authorized']], list(subset))
                self.assertEqual([r['title'].split(' · ')[1][:2] for r in actual], ['02', '04', '12', '14'])

    def test_legacy_opened_facts_survive_without_granting_unopened_consent(self):
        self.ok('plan', 'srs', 'work')
        self.ok('authorize', 'srs')
        self.ok('set', '1', 'old-child')
        text = self.path.read_text(encoding='utf-8')
        text = '\n'.join(line for line in text.splitlines() if not line.startswith('Authorized stages: ')) + '\n'
        self.path.write_text(text, encoding='utf-8')
        self.ok('show')
        self.ok('plan', 'work', 'audit')
        _, rows = MOD.read(self.path)
        self.assertEqual(rows[0]['id'], 'old-child')
        self.assertFalse(any(r['authorized'] for r in rows))
        self.assertNotEqual(self.cli('set', '2', 'new-child').returncode, 0)

    def test_foreign_document_author_does_not_remove_work_proposal(self):
        doc = self.repo / 'documentation/architecture/foundation.md'
        doc.parent.mkdir(parents=True)
        doc.write_text('---\nversion: 1.0.0\nauthor: Someone Else\n---\n# Architecture\n')
        self.ok('plan', 'work')
        self.assertEqual(MOD.read(self.path)[1][0]['stage'], 'work')

    def test_invalid_selection_and_corrupt_header_preserve_registry(self):
        self.ok('plan', 'work')
        before = self.path.read_bytes()
        self.assertNotEqual(self.cli('authorize', 'srs').returncode, 0)
        self.assertEqual(self.path.read_bytes(), before)
        self.path.write_text(self.path.read_text(encoding='utf-8') + 'Authorized stages: ["work"]\n', encoding='utf-8')
        self.assertNotEqual(self.cli('show').returncode, 0)


if __name__ == '__main__':
    unittest.main()
