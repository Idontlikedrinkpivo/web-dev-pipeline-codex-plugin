import contextlib
import io
import json
from datetime import timedelta
from pathlib import Path
import os
import subprocess
import sys
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_close_iteration_stamp import RepoTest, ROOT, load

sessions = load('window_sessions', ROOT / 'dev-pipeline/skills/reflect/scripts/sessions.py')


class WindowTests(RepoTest):
    def setUp(self):
        super().setUp()
        self.home = self.root.parent / 'codex'
        self.home.mkdir()
        self.patch = mock.patch.object(sessions, 'HOME', self.home)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.start = sessions.utc('2026-11-05T10:00:00.123456Z')
        self.write('documentation/plans/1.0.1/iteration.json', json.dumps({
            'schema_version': 1, 'mode': 'normal', 'version': '1.0.1', 'started_at': sessions.iso(self.start)}))

    def record(self, start, end, **extra):
        return {'schema_version': 1, 'project': self.root.name, 'version': '1.0.1',
                'window': {'start': sessions.iso(start), 'end': sessions.iso(end)},
                'source_hash': 'a' * 64, 'event_cursor': {'count': 1}, 'completion': 'complete',
                'boundary': 'handoff', **extra}

    def blocks(self, records):
        return '\n'.join('```reflect-window\n' + json.dumps(r) + '\n```' for r in records)

    def test_contiguous_offset_seconds_property(self):
        cursor, rows = self.start, []
        for i in range(1, 30):
            end = cursor + timedelta(seconds=i, microseconds=i)
            row = self.record(cursor, end)
            row['window']['start'] = cursor.astimezone(sessions.timezone(timedelta(hours=3))).isoformat()
            rows.append(row)
            got, accepted, issues = sessions.read_windows(self.blocks(rows), self.root.name, '1.0.1', self.start)
            self.assertEqual(got, end)
            self.assertEqual(len(accepted), i)
            self.assertFalse(issues)
            cursor = end

    def test_partial_corrupt_other_project_version_and_gap_do_not_advance(self):
        end = self.start + timedelta(seconds=20)
        rows = [self.record(self.start, end, completion='partial'),
                self.record(self.start, end, project='foreign'),
                self.record(self.start, end, version='2.0.0'),
                self.record(self.start + timedelta(seconds=1), end),
                self.record(self.start, end, source_hash='broken'),
                self.record(self.start, end, boundary='checkpoint')]
        cursor, accepted, issues = sessions.read_windows(self.blocks(rows) + '\n```reflect-window\n{bad\n```', self.root.name, '1.0.1', self.start)
        self.assertEqual(cursor, self.start)
        self.assertFalse(accepted)
        self.assertGreaterEqual(len(issues), 4)
        self.assertEqual(sessions.read_windows('', self.root.name, '1.0.1', self.start)[0], self.start)
        self.assertIn('migration', sessions.read_windows('Окно: 2026-11-05 10:00 — 2026-11-05 10:01', self.root.name, '1.0.1', self.start)[2][0])

    def test_window_cli_sources_boundary_cursor_and_exact_filters(self):
        logs = self.home / 'sessions'
        logs.mkdir()
        data = [{'timestamp': sessions.iso(self.start), 'type': 'session_meta', 'payload': {'id': 'base', 'cwd': str(self.root)}},
                {'timestamp': '2026-11-05T10:00:01Z', 'type': 'event_msg', 'payload': {'type': 'user_message', 'message': 'one'}},
                {'timestamp': '2026-11-05T10:00:02+00:00', 'type': 'event_msg', 'payload': {'type': 'agent_message', 'message': 'two'}}]
        src = logs / 'rollout-main.jsonl'
        src.write_text('\n'.join(json.dumps(r) for r in data))
        result = subprocess.run([sys.executable, str(sessions.__file__), 'window', str(self.root), '--version', '1.0.1',
                                 '--until', '2026-11-05T10:00:03Z', '--boundary', 'handoff'],
                                env=dict(os.environ, CODEX_HOME=str(self.home)), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        row = json.loads(result.stdout)
        self.assertEqual(row['completion'], 'complete')
        self.assertEqual(row['window']['start'], sessions.iso(self.start))
        self.assertEqual(sessions.window_record(self.root, '1.0.1', boundary='checkpoint')['completion'], 'partial')
        path = sessions.feedback_path(self.root)
        path.parent.mkdir(parents=True)
        path.write_text(self.blocks([row]))
        self.assertFalse(sessions.reflect_coverage(self.root, '1.0.1', sessions.utc(row['window']['end']))[0])
        self.assertTrue(sessions.reflect_coverage(self.root, '1.0.1', sessions.utc('2026-11-05T10:00:02Z'))[0])
        output = self.root.parent / 'digest.md'
        with contextlib.redirect_stdout(io.StringIO()):
            sessions.cmd_digest(str(src), str(output), '2026-11-05T10:00:01Z', '2026-11-05T10:00:02Z')
        self.assertIn('USER: one', output.read_text())
        self.assertNotIn('CODEX: two', output.read_text())

    def test_iteration_history_fallback_not_folder_mtime_and_absent_logs(self):
        marker = self.root / 'documentation/plans/1.0.1/iteration.json'
        marker.unlink()
        self.git('switch', '-q', '-c', 'iteration/1.0.1')
        self.commit('fix: bounded change\n\nPlan-Unit: 1.0.1/chat-1')
        start, source = sessions.iteration_start(self.root, '1.0.1')
        self.assertEqual(int(start.timestamp()), int(self.git('log', '-1', '--format=%ct')))
        self.assertEqual(source, 'iteration-commit')
        with contextlib.redirect_stderr(io.StringIO()):
            row = sessions.window_record(self.root, '1.0.1', sessions.iso(start + timedelta(seconds=1)), 'stop')
        self.assertEqual(row['completion'], 'unavailable')


if __name__ == '__main__':
    import unittest
    unittest.main()
