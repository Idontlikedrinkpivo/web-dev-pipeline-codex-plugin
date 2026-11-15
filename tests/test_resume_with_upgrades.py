"""A fresh clone must find its iteration even when the default branch has pending upgrades."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PLUGIN = Path(__file__).resolve().parents[1] / 'dev-pipeline'
PIPELINE = PLUGIN / 'skills/pipeline/scripts'
FORMAT = PLUGIN / 'skills/upgrade-docs/scripts/project_format.py'


class ResumeWithUpgrades(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.source = root / 'source'
        self.clone = root / 'second computer'
        self.source.mkdir()
        self.env = dict(os.environ, CODEX_HOME=str(root / 'codex'), PYTHONDONTWRITEBYTECODE='1',
                        GIT_AUTHOR_NAME='Test', GIT_COMMITTER_NAME='Test',
                        GIT_AUTHOR_EMAIL='test@example.com', GIT_COMMITTER_EMAIL='test@example.com')
        self.cmd('git', 'init', '-qb', 'master', cwd=self.source)
        (self.source / 'documentation').mkdir()
        (self.source / 'documentation/readme.md').write_text('# Project\n')
        for name in ('docker-compose.prod.yml', 'docker-compose.test.yml'):
            (self.source / name).write_text('services: {}\n')
        self.commit('project')
        self.cmd('git', 'switch', '-qc', 'iteration/0.1.0', cwd=self.source)
        self.folder = Path('documentation/plans/0.1.0')
        (self.source / self.folder).mkdir(parents=True)
        (self.source / self.folder / 'resume.md').write_text('Следующий шаг: общее ревью\n')
        self.commit('saved step')
        self.cmd('git', 'switch', '-q', 'master', cwd=self.source)
        self.cmd('git', 'clone', '-q', str(self.source), str(self.clone), cwd=root)

    def cmd(self, *args, cwd=None, payload=None):
        return subprocess.run(args, cwd=cwd or self.clone, env=self.env, input=payload,
                              text=True, check=True, capture_output=True).stdout

    def commit(self, msg):
        self.cmd('git', 'add', '.', cwd=self.source)
        self.cmd('git', 'commit', '-qm', msg, cwd=self.source)

    def hook(self, source='startup'):
        return self.cmd('sh', PLUGIN / 'hooks/session-start.sh',
                        payload=json.dumps({'source': source, 'cwd': str(self.clone)}))

    def test_remote_iteration_then_saved_step_with_optional_updates(self):
        hook = self.hook()
        note = self.cmd(sys.executable, FORMAT, 'hook', '.').strip()
        self.assertEqual(len(note.splitlines()), 1)
        for command in ('upgrade-docs', 'upgrade-code'):
            self.assertIn(command, note)
        self.assertLess(hook.index('where_am_i.py'), hook.index(note))
        status = self.cmd(sys.executable, PIPELINE / 'where_am_i.py')
        self.assertIn('git show origin/iteration/0.1.0:documentation/plans/0.1.0/resume.md', status)
        self.assertNotIn('Документы:', status)  # master is not evidence for this iteration
        self.assertEqual(self.cmd('git', 'branch', '--show-current').strip(), 'master')
        pickup = self.cmd(sys.executable, PIPELINE / 'open_iteration.py', '0.1.0')
        self.assertIn('По желанию', pickup)
        self.assertIn('продолжить по documentation/plans/0.1.0/resume.md',
                      self.cmd(sys.executable, PIPELINE / 'where_am_i.py'))
        self.assertIn('общее ревью', (self.clone / self.folder / 'resume.md').read_text())
        self.assertFalse((self.clone / 'documentation/.dev-pipeline.json').exists())
        self.assertNotIn('upgrade-code', self.hook('resume'))
        self.cmd(sys.executable, FORMAT, 'born', '.')
        self.assertEqual(self.cmd(sys.executable, FORMAT, 'hook', '.'), '')

    def test_ambiguous_remote_iterations_offer_only_selection(self):
        self.cmd('git', 'branch', 'iteration/0.2.0', 'iteration/0.1.0', cwd=self.source)
        self.cmd('git', 'fetch', '-q', 'origin')
        status = self.cmd(sys.executable, PIPELINE / 'where_am_i.py')
        self.assertIn('Открытых веток итераций: 2', status)
        self.assertNotIn('open_iteration.py', status)
        self.assertEqual(self.cmd('git', 'status', '--porcelain'), '')
