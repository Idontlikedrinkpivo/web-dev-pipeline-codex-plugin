"""Continue a nested project from a second checkout with legacy documents at Git root."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'dev-pipeline/skills/pipeline/scripts'


class NestedContinue(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.top = Path(temp.name).resolve()
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                        GIT_AUTHOR_NAME='test', GIT_COMMITTER_NAME='test',
                        GIT_AUTHOR_EMAIL='test@example.com', GIT_COMMITTER_EMAIL='test@example.com')
        self.git('init', '-qb', 'master')
        self.write('documentation/requirements/requirements.md', '# old')
        self.commit('legacy project')
        self.git('switch', '-qc', 'iteration/0.1.0')
        self.docs = 'v2/documentation/'
        self.srs = self.docs + 'requirements/srs/srs.md'
        self.api = self.docs + 'api/openapi.yaml'
        self.write(self.srs, '---\nversion: 0.1.0\n---\n')
        self.commit('docs: SRS 0.1.0 · grill: прошёл · review: прошёл')
        self.write(self.docs + 'db/schema.md', '---\nversion: 0.1.0\n---\n')
        self.commit('docs: схема БД 0.1.0')
        self.write(self.api, 'info:\n  version: 0.1.0\n')
        self.commit('docs: API 0.1.0')
        self.write(self.api, 'info:\n  version: 0.1.0\n  x-reviewed: 2026-11-04\n')
        self.commit('review metadata')
        self.write(self.srs, (self.top / self.srs).read_text() + 'amendment\n')
        questions = '| Вопрос | Класс |\n|---|---|\n| Q | Можно решить при архитектуре |\n'
        self.write(self.docs + 'requirements/srs/open-questions.md', questions)
        self.write('documentation/requirements/open-questions.md', questions + '| R | Отложено |\n')
        self.commit('docs: решение изменено — уточнение')
        self.head = self.git('rev-parse', 'HEAD')

    def write(self, path, text):
        path = self.top / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def cmd(self, *args, cwd=None, ok=True):
        p = subprocess.run(args, cwd=cwd or self.top, env=self.env, capture_output=True, text=True)
        if ok:
            self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        return p

    def git(self, *args):
        return self.cmd('git', *args).stdout.strip()

    def commit(self, msg):
        self.git('add', '.')
        self.git('commit', '--allow-empty', '-qm', msg)

    def status(self, cwd=None):
        return self.cmd(sys.executable, SCRIPTS / 'where_am_i.py', cwd=cwd).stdout

    def test_read_only_status_from_both_roots_and_real_edit(self):
        for cwd in (self.top, self.top / 'v2'):
            report = self.status(cwd)
            self.assertIn(f'Проект: {self.top / "v2"}\n', report)
            self.assertIn('можно начать сейчас: архитектура', report)
            self.assertIn('можно начать сейчас: макеты', report)
            self.assertIn('архитектура: 1 —', report)
            self.assertNotIn('Отложено:', report)
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.head)
        self.assertFalse((self.top / '.gitignore').exists())
        self.write(self.api, (self.top / self.api).read_text() + 'paths: {}\n')
        self.commit('contract change')
        self.assertNotIn('можно начать сейчас: архитектура', self.status())
        self.commit('contract reviewed\n\nStage-Closed: api 0.1.0')
        self.assertIn('можно начать сейчас: архитектура', self.status())

    def test_pickup_when_project_only_exists_on_iteration_branch(self):
        self.git('switch', '-q', 'master')
        self.assertFalse((self.top / 'v2').exists())
        report = self.status()
        self.assertIn('v2/documentation/', report)
        self.assertIn('git switch iteration/0.1.0', report)
        self.cmd(sys.executable, SCRIPTS / 'open_iteration.py', '0.1.0')
        self.assertEqual(self.git('diff', '--name-only', self.head, 'HEAD'), 'v2/.gitignore')
        self.assertFalse((self.top / 'documentation/plans').exists())
        self.assertTrue((self.top / 'v2/documentation/plans/0.1.0/iteration.json').exists())

    def test_sibling_stage_close_is_project_specific(self):
        self.write(self.api, (self.top / self.api).read_text() + 'paths: {}\n')
        self.commit('unreviewed change')
        self.write('sibling/documentation/api/openapi.yaml', 'info: {}\n')
        self.write('sibling/documentation/.dev-pipeline.json', '{}')
        self.commit('docs: API 0.1.0')
        result = self.cmd(sys.executable, SCRIPTS / 'where_am_i.py', ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Уточните папку проекта', result.stderr)
        self.assertNotIn('можно начать сейчас: архитектура', self.status(self.top / 'v2'))
