import contextlib
import io
import json
from pathlib import Path
import sys
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_close_iteration_stamp import RepoTest, ROOT, load

SCRIPTS = ROOT / 'dev-pipeline/skills/reflect/scripts'
sessions = load('cost_sessions', SCRIPTS / 'sessions.py')
with mock.patch.dict(sys.modules, {'sessions': sessions}):
    logs = load('cost_logs', SCRIPTS / 'codex_logs.py')
measure = load('cost_measure', SCRIPTS / 'measure.py')
compare = load('cost_compare', SCRIPTS / 'compare.py')


def usage(total, tin=10, cached=2, out=1, stamp='2026-11-05T10:00:01Z'):
    return {'timestamp': stamp, 'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {
        'total_token_usage': {'total_tokens': total},
        'last_token_usage': {'input_tokens': tin, 'cached_input_tokens': cached, 'output_tokens': out}}}}


class CostTests(RepoTest):
    def setUp(self):
        super().setUp()
        self.home = self.root.parent / 'codex'
        self.home.mkdir()
        self.patch = mock.patch.object(sessions, 'HOME', self.home)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def log(self, name, role=None, records=None, **meta):
        folder = self.home / 'sessions'
        folder.mkdir(exist_ok=True)
        path = folder / f'rollout-{name}.jsonl'
        data = [{'type': 'session_meta', 'payload': {'id': name, 'cwd': str(self.root), **({'agent_type': role} if role else {}), **meta}}]
        data += records or []
        path.write_text('\n'.join(json.dumps(r) for r in data))
        return path

    def collect(self, since=None, until=None):
        return logs.collect(str(self.root), since, [], measure.Agent, measure.add_counts, measure.SESSION, until)

    def test_guardian_is_separate_and_known_totals_sum(self):
        self.log('main', records=[usage(11)])
        self.log('builder', 'impl-medium', [usage(11)])
        self.log('guardian', 'guardian', [usage(11)])
        session, agents, _, _ = self.collect()
        self.assertEqual(measure.group_of(agents[1].kind) if agents[1].kind == 'guardian' else measure.group_of(agents[0].kind), 'Guardian (billing unknown)')
        groups = {}
        for agent in [session, *agents]:
            key = measure.group_of(agent.kind)
            groups[key] = groups.get(key, 0) + agent.units
        self.assertAlmostEqual(sum(groups.values()), 39.6)
        self.assertEqual(groups['Guardian (billing unknown)'], 13.2)

    def test_archive_continuation_repeated_totals_and_resets(self):
        first = usage(11)
        path = self.log('base', 'impl-medium', [first, first, usage(22, stamp='2026-11-05T10:00:02Z'),
                                             usage(5, stamp='2026-11-05T10:00:03Z')])
        archive = self.home / 'archived_sessions'
        archive.mkdir()
        (archive / path.name).write_bytes(path.read_bytes())
        self.log('continued', 'impl-medium', [usage(11, stamp='2026-11-05T10:00:01Z'), usage(22, stamp='2026-11-05T10:00:02Z'),
                                              usage(5, stamp='2026-11-05T10:00:03Z'), usage(16, stamp='2026-11-05T10:00:04Z')], resumed_from_id='base')
        _, agents, _, _ = self.collect()
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0].calls, 4)

    def test_exact_window_and_missing_usage_are_unknown(self):
        broken = usage(33, stamp='2026-11-05T10:00:03Z')
        broken['payload']['info']['last_token_usage'] = None
        self.log('base', records=[usage(11), usage(22, stamp='2026-11-05T10:00:02+00:00'), broken])
        session, _, _, _ = self.collect('2026-11-05T10:00:02Z', '2026-11-05T10:00:03Z')
        self.assertEqual(session.calls, 1)
        self.assertEqual(session.unknown_usage, 0)
        self.assertEqual(self.collect()[0].unknown_usage, 1)

    def test_observed_attempt_evidence_and_unknown_prose(self):
        for name, acceptance in [('one', 'accepted'), ('two', 'rejected')]:
            self.log(name, 'impl-medium', [usage(11), {'type': 'event_msg', 'timestamp': '2026-11-05T10:00:02Z', 'payload': {
                'type': 'task_report', 'task_id': 'U1', 'grade': 'Mid', 'attempt': 1, 'review_acceptance': acceptance}}])
        self.log('unknown', 'impl-medium', [usage(11), {'type': 'event_msg', 'timestamp': '2026-11-05T10:00:02Z', 'payload': {
            'type': 'agent_message', 'message': 'accepted U1 grade High attempt 10'}}])
        _, agents, _, _ = self.collect()
        self.assertEqual({a.review_acceptance for a in agents}, {'accepted', 'rejected', None})
        observed = [a for a in agents if a.review_acceptance]
        self.assertTrue(all(a.task_id == 'U1' and a.grade == 'Mid' and a.attempt == 1 for a in observed))

    def test_zero_null_json_text_and_legacy_acceptance(self):
        self.log('zero', records=[usage(0, tin=0, cached=0, out=0)])
        data = self.collect()
        output = self.root.parent / 'report.json'
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            measure.report(['--json', str(output)], str(self.root), None, *data)
        report = json.loads(output.read_text())
        self.assertEqual(report['total'], 0)
        self.assertIsNone(report['accepted'])
        self.assertIsNone(report['currency'])
        data[0].unknown_usage = 1
        with contextlib.redirect_stdout(stdout):
            measure.report(['--json', str(output)], str(self.root), None, *data)
        self.assertIsNone(json.loads(output.read_text())['total'])
        self.assertIn('unknown', stdout.getvalue())
        self.assertIsNone(compare.value({'total': None}, 'total'))
        self.assertEqual(compare.value({'total': 0}, 'total'), 0)
        self.assertEqual(compare.ratio([10], [0]), 0)

    def test_compare_rejects_unequal_windows_baselines_and_legacy(self):
        base = {'schema_version': 2, 'complete': True, 'window': {'start': 'a', 'end': 'b'},
                'baseline': 'same tasks', 'unit_kind': 'conditional-token-units'}
        self.assertTrue(compare.comparison_status([base, dict(base)])[0])
        for key, value in [('window', {'start': 'a', 'end': 'c'}), ('baseline', 'different'), ('complete', False), ('schema_version', 1)]:
            self.assertFalse(compare.comparison_status([base, {**base, key: value}])[0])
        self.assertIn('legacy', compare.comparison_status([{'total': 12}])[1])


if __name__ == '__main__':
    import unittest
    unittest.main()
