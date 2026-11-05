"""Real Git closes, parallel ownership and the API dependency queue."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'dev-pipeline/skills/pipeline/scripts'
sys.path.insert(0, str(SCRIPTS))
import stage_readiness as ready
import subsessions


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.test')
        self.git('commit', '--allow-empty', '-qm', 'base')
        self.git('switch', '-qc', 'iteration/1.0.0')
        self.env = dict(os.environ, CODEX_THREAD_ID='parent', PYTHONDONTWRITEBYTECODE='1')
        self.write('requirements/srs/srs.md', '---\nversion: 1.0.0\n---\n# SRS\n')
        self.commit('docs: SRS 1.0.0 · grill: прошёл · review: прошёл')
        self.write('ui/frames-register.md', '# Frames\n')
        self.commit('docs: макеты 1.0.0')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True, text=True).stdout

    def write(self, path, content):
        p = self.root / 'documentation' / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    def commit(self, message):
        self.git('add', '.')
        self.git('commit', '--allow-empty', '-qm', message)

    def cli(self, *args, ok=True):
        p = subprocess.run([sys.executable, str(SCRIPTS / 'subsessions.py'), str(self.root),
                            '1.0.0', *args], env=self.env, capture_output=True, text=True)
        if ok:
            self.assertEqual(p.returncode, 0, p.stderr)
        return p

    def test_parallel_branch_waits_then_api_then_arch_and_specs(self):
        self.write('db/schema.md', '---\nversion: 1.0.0\n---\n# Schema\n')
        self.commit('docs: схема БД 1.0.0 — написана, этап не закрыт')
        rows = [dict(stage='db', state='идёт', title='1.0.0 · схема БД', id='db-child')]
        self.assertFalse(ready.closed(self.root, 'db', '1.0.0'))
        with patch.dict(os.environ, self.env):
            states = ready.evaluate(self.root, '1.0.0', rows)
        text = '\n'.join(ready.lines(states))
        self.assertIn('Начать здесь нечего', text)
        self.assertIn('ждёт входов: API — нет: схема БД (идёт в соседнем чате)', text)
        self.assertIn('ждёт входов: ТЗ на экраны — нет: API', text)
        self.assertIn('идёт в соседнем чате: схема БД', text)
        self.commit('docs: схема БД 1.0.0 · review: прошёл')
        states = ready.evaluate(self.root, '1.0.0', [])
        self.assertEqual([r['key'] for r in states if r['state'] == 'ready'], ['api'])
        self.write('api/openapi.yaml', 'info:\n  version: 1.0.0\n')
        self.commit('docs: API 1.0.0 · review: прошёл')
        states = ready.evaluate(self.root, '1.0.0', [])
        self.assertEqual([r['key'] for r in states if r['state'] == 'ready'], ['arch', 'specs'])

    def test_queue_wait_release_and_where_child_owner(self):
        self.cli('plan', 'db', 'api', 'specs')
        self.cli('authorize', 'db', 'api', 'specs')
        self.cli('set', '1', 'db-child')
        self.cli('set', '2', 'api-child')
        self.cli('set', '3', 'specs-child')
        self.cli('mark', '1', 'идёт')
        self.assertIn('ждёт входа:', self.cli('show').stdout)
        self.assertIn('«начинай» после API', self.cli('show').stdout)
        self.assertNotEqual(self.cli('mark', '3', 'идёт', ok=False).returncode, 0)
        self.assertNotEqual(self.cli('when', '3', 'clear', ok=False).returncode, 0)
        self.write('db/schema.md', '---\nversion: 1.0.0\n---\n')
        self.commit('docs: схема БД 1.0.0 · review: прошёл')
        self.cli('mark', '1', 'закрыт')
        self.write('api/openapi.yaml', 'info:\n  version: 1.0.0\n')
        self.commit('docs: API 1.0.0 · review: прошёл')
        self.assertIn('теперь можно: «1.0.0 · 08 ТЗ на экраны»', self.cli('mark', '2', 'закрыт').stdout)
        self.cli('when', '3', 'api')
        self.cli('when', '3', 'clear')
        self.cli('mark', '3', 'идёт')
        with patch.dict(os.environ, dict(self.env, CODEX_THREAD_ID='specs-child')):
            states = ready.evaluate(self.root, '1.0.0')
        self.assertEqual(next(r for r in states if r['key'] == 'specs')['state'], 'here')
        result = subprocess.run([sys.executable, str(SCRIPTS / 'where_am_i.py'), str(self.root)],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Готовность этапов', result.stdout)
        self.assertIn('идёт в соседнем чате: ТЗ на экраны', result.stdout)
        self.assertNotIn('этап 8 ТЗ на экраны: можно начать', result.stdout)

    def test_file_or_registry_mark_alone_is_not_closure_and_skips_are_explicit(self):
        self.write('db/schema.md', '---\nversion: 1.0.0\n---\n')
        self.commit('written only')
        self.assertFalse(ready.closed(self.root, 'db', '1.0.0'))
        states = ready.evaluate(self.root, '1.0.0', [dict(stage='db', state='закрыт', title='db')])
        self.assertEqual(next(r for r in states if r['key'] == 'api')['state'], 'waiting')
        self.write('.dev-pipeline.json', '{"capabilities":{"storage":false,"http":false,"screens":false}}')
        states = ready.evaluate(self.root, '1.0.0', [])
        self.assertEqual([r['key'] for r in states if r['state'] == 'ready'], ['arch'])
        self.assertIn('пропущен: API — нет HTTP', '\n'.join(ready.lines(states)))

    def test_split_api_change_reopens_input_and_explicit_close_restores_it(self):
        self.write('api/openapi.yaml', 'info:\n  version: 1.0.0\n')
        self.write('api/paths/items.yaml', 'get: {}\n')
        self.commit('docs: API 1.0.0 · review: прошёл')
        self.assertTrue(ready.closed(self.root, 'api', '1.0.0'))
        self.write('api/paths/items.yaml', 'post: {}\n')
        self.assertFalse(ready.closed(self.root, 'api', '1.0.0'))
        self.commit('draft API body')
        self.assertFalse(ready.closed(self.root, 'api', '1.0.0'))
        self.commit('docs: reviewed contract\n\nStage-Closed: api 1.0.0')
        self.assertTrue(ready.closed(self.root, 'api', '1.0.0'))

    def test_legacy_architecture_and_scaffold_close_subjects(self):
        self.write('architecture/architecture.md', '---\nversion: 1.0.0\n---\n')
        self.commit('docs: архитектура 1.0.0 · review: прошёл')
        self.assertFalse(ready.closed(self.root, 'arch', '1.0.0'))
        self.write('architecture/domain.md', '---\nversion: 1.0.0\n---\n')
        self.commit('docs: доменная модель 1.0.0 · review: прошёл')
        self.assertTrue(ready.closed(self.root, 'arch', '1.0.0'))
        self.write('project-map/project-map.md', '# Map\n')
        self.commit('chore(scaffold): каркас репозитория')
        self.assertTrue(ready.closed(self.root, 'scaffold', '1.0.0'))


if __name__ == '__main__':
    unittest.main()
