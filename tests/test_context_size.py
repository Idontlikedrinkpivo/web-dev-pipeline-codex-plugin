"""Exact-chat telemetry: a busy sibling must never decide a run's checkpoint."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'dev-pipeline/skills/reflect/scripts/context_size.py'


class ContextSizeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.project = self.home / 'project'
        self.project.mkdir()

    def rollout(self, sid, tokens=1000, window=400000, *, cwd=None,
                archived=False, timestamp='2026-11-04T10:00:00Z', suffix='', source='cli'):
        folder = self.home / ('archived_sessions' if archived else 'sessions')
        folder.mkdir(exist_ok=True)
        path = folder / f'rollout-{sid}{suffix}.jsonl'
        meta = {'id': sid, 'cwd': str(cwd or self.project), 'source': source}
        events = [{'type': 'session_meta', 'payload': meta}]
        if tokens is not None:
            events += [{'type': 'event_msg', 'timestamp': timestamp, 'payload': {
                'type': 'token_count', 'info': {'last_token_usage': {'input_tokens': tokens},
                                              'model_context_window': window}}}]
        path.write_text('\n'.join(json.dumps(e) for e in events) + '\n')
        return path

    def run_reader(self, sid=None, *args):
        env = dict(os.environ, CODEX_HOME=str(self.home))
        env.pop('CODEX_THREAD_ID', None)
        if sid is not None:
            env['CODEX_THREAD_ID'] = sid
        run = subprocess.run(['python3.12', str(SCRIPT), str(self.project), '--json', *args],
                             env=env, text=True, capture_output=True)
        self.assertIn(run.returncode, (0, 2, 3), run.stderr)
        return run.returncode, json.loads(run.stdout)

    def test_current_chat_wins_over_newer_busy_sibling(self):
        self.rollout('current', 10000)
        self.rollout('sibling', 390000)
        code, data = self.run_reader('current')
        self.assertEqual((code, data['thread_id'], data['input_tokens']), (0, 'current', 10000))

    def test_explicit_id_overrides_environment_and_reads_archive(self):
        self.rollout('current', 10000)
        self.rollout('selected', 300000, archived=True)
        code, data = self.run_reader('current', '--thread-id', 'selected')
        self.assertEqual((code, data['thread_id']), (2, 'selected'))

    def test_ambiguous_project_is_unknown_not_latest(self):
        self.rollout('one')
        self.rollout('two')
        code, data = self.run_reader()
        self.assertEqual((code, data['status']), (3, 'UNKNOWN'))
        self.assertNotIn('input_tokens', data)

    def test_no_match_never_falls_back_to_another_project_or_chat(self):
        self.rollout('other')
        self.rollout('current', cwd=self.home / 'elsewhere')
        self.assertEqual(self.run_reader('current')[0], 3)

    def test_missing_or_invalid_telemetry_is_unknown(self):
        for value in (None, 0, -10, '40000', True):
            with self.subTest(value=value):
                self.rollout('current', value)
                self.assertEqual(self.run_reader('current')[0], 3)

    def test_window_headroom_threshold_includes_equality(self):
        self.rollout('current', 140000, 200000)
        code, data = self.run_reader('current')
        self.assertEqual((code, data['limit']), (2, 140000))
        self.rollout('current', 139999, 200000)
        self.assertEqual(self.run_reader('current')[0], 0)

    def test_large_or_missing_window_uses_300k_cap(self):
        for window in (1000000, None):
            self.rollout('current', 300000, window)
            code, data = self.run_reader('current')
            self.assertEqual((code, data['limit']), (2, 300000))

    def test_explicit_limit(self):
        self.rollout('current', 12000)
        code, data = self.run_reader('current', '--limit', '12000')
        self.assertEqual((code, data['limit']), (2, 12000))

    def test_old_usage_after_host_compaction_is_unknown(self):
        path = self.rollout('current', 390000)
        with path.open('a') as out:
            out.write(json.dumps({'type': 'compacted', 'timestamp': '2026-11-04T11:00:00Z',
                                  'payload': {}}) + '\n')
        self.assertEqual(self.run_reader('current')[0], 3)

    def test_resumed_rollout_uses_latest_event_not_file_mtime(self):
        old = self.rollout('current', 390000, timestamp='2026-11-04T09:00:00Z')
        self.rollout('current', 20000, timestamp='2026-11-04T10:00:00Z', suffix='-resumed')
        os.utime(old, (2100000000, 2100000000))
        code, data = self.run_reader('current')
        self.assertEqual((code, data['input_tokens']), (0, 20000))

    def test_single_main_chat_fallback_ignores_subagents(self):
        self.rollout('current', 10000)
        self.rollout('worker', 390000, source={'subagent': {'parent_thread_id': 'current'}})
        code, data = self.run_reader()
        self.assertEqual((code, data['thread_id']), (0, 'current'))


if __name__ == '__main__':
    unittest.main()
