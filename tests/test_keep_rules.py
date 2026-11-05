"""Durable stage recovery must beat the last transcript skill read."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'dev-pipeline/skills/pipeline/scripts'
SCRIPT = SCRIPTS / 'keep_rules.py'
HOOK = ROOT / 'dev-pipeline/hooks/session-start.sh'
sys.path.insert(0, str(SCRIPTS))
import checkpoint
import subsessions


class KeepRulesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name).resolve() / 'project'
        self.repo.mkdir()
        self.env = dict(os.environ, CODEX_HOME=str(Path(self.temp.name) / 'home'),
                        CODEX_THREAD_ID='current', PYTHONDONTWRITEBYTECODE='1')
        for args in (('init', '-q', '-b', 'main'), ('config', 'user.name', 'Fixture'),
                     ('config', 'user.email', 'fixture@example.com')):
            self.git(*args)
        self.plans = self.repo / 'documentation/plans/1.0.0'
        self.plans.mkdir(parents=True)
        (self.plans / 'plan.md').write_text('# Plan\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')
        self.transcript = Path(self.temp.name) / 'transcript.jsonl'
        self.transcript.write_text('/skills/work/SKILL.md\n/skills/pipeline/SKILL.md\n')

    def git(self, *args):
        result = subprocess.run(['git', '-C', str(self.repo), *args], env=self.env,
                                text=True, capture_output=True, check=True)
        return result.stdout.strip()

    def capture(self, stage='work'):
        head = self.git('rev-parse', 'HEAD')
        state = {'run_id': 'logical-run', 'source_id': 'logical-source', 'unit': 'U6',
                 'phase': 'unit', 'next_action': 'review U6', 'review': {'base': head, 'head': head},
                 'low_batches': [], 'findings': [], 'decisions': [],
                 'reports': {name: '# Saved\n' for name in ('work-run.md', 'resume.md', 'context-handover.md')}}
        return checkpoint.capture(self.repo, '1.0.0', 'current', state, [], runtime={'stage': stage})

    def cli(self, thread='current', transcript=True):
        args = [sys.executable, str(SCRIPT)]
        if transcript:
            args.append(str(self.transcript))
        return subprocess.run([*args, '--checkout', str(self.repo), '--version', '1.0.0',
                               '--thread-id', thread], env=self.env, text=True, capture_output=True)

    def test_actual_checkpoint_stage_beats_last_pipeline_read(self):
        self.capture()
        pointer = (self.plans / 'run-state.json').read_bytes()
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('in this stage (work,', result.stdout)
        self.assertNotIn('Legacy transcript hint', result.stdout)
        self.assertEqual(pointer, (self.plans / 'run-state.json').read_bytes())

    def test_wrong_thread_unknown_stage_and_corrupt_state_fallback(self):
        self.capture()
        self.assertIn('stage recovery required', self.cli('sibling').stdout)
        self.capture('unrecognized')
        self.assertIn('in this stage (pipeline,', self.cli().stdout)
        (self.plans / 'run-state.json').write_text('{')
        self.assertIn('stage recovery required', self.cli().stdout)

    def test_exact_active_subsession_without_checkpoint_is_durable(self):
        paths = subsessions.resolve_paths(self.repo, '1.0.0', 'parent')
        row = dict(subsessions.rows_for('1.0.0', 'work')[0], id='current', state='идёт', authorized=True)
        subsessions.write(paths.local / 'sessions.md', '1.0.0', 'parent', [row])
        self.assertIn('in this stage (work,', self.cli().stdout)
        self.assertIn('in this stage (pipeline,', self.cli('other').stdout)

    def test_conflicting_checkpoint_and_active_subsession_fallback(self):
        self.capture('audit')
        paths = subsessions.resolve_paths(self.repo, '1.0.0', 'parent')
        row = dict(subsessions.rows_for('1.0.0', 'work')[0], id='current', state='идёт', authorized=True)
        subsessions.write(paths.local / 'sessions.md', '1.0.0', 'parent', [row])
        self.assertIn('contradictory', self.cli().stdout)

    def test_legacy_missing_transcript_is_safe_and_hint_is_not_stage(self):
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.transcript)],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('Legacy transcript hint only', result.stdout)
        self.assertIn('in this stage (pipeline,', result.stdout)
        self.transcript.unlink()
        self.assertIn('in this stage (pipeline,', self.cli().stdout)

    def test_hook_uses_real_input_checkout_and_thread_without_transcript(self):
        self.capture()
        result = subprocess.run(['sh', str(HOOK)], cwd=self.repo, env=self.env,
                                input=json.dumps({'cwd': str(self.repo), 'source': 'compact', 'thread_id': 'current'}),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('in this stage (work,', result.stdout)
        syntax = subprocess.run(['sh', '-n', str(HOOK)], capture_output=True)
        self.assertEqual(syntax.returncode, 0)


if __name__ == '__main__':
    unittest.main()
