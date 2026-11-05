"""Sanitized Codex source fixtures; never reads the developer's session logs."""
import contextlib
import gzip
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / 'dev-pipeline/skills/reflect/scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sessions = load('sessions')
with mock.patch.dict(sys.modules, {'sessions': sessions}):
    logs = load('codex_logs')
guard = load('guard_report')


def row(payload, kind='response_item', timestamp='2026-10-31T12:01:00Z'):
    return {'timestamp': timestamp, 'type': kind, 'payload': payload}


def message(role, text, encoding='response_item', **extra):
    if encoding == 'event_msg':
        payload = {'type': 'user_message' if role == 'user' else 'agent_message', 'message': text}
    else:
        payload = {'type': 'message', 'role': role,
                   'content': [{'type': 'input_text' if role == 'user' else 'output_text', 'text': text}]}
    payload.update(extra)
    return row(payload, encoding)


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / 'codex'
        self.home.mkdir()
        self.patch = mock.patch.object(sessions, 'HOME', self.home)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def write(self, name, data, archive=False):
        folder = self.home / ('archived_sessions' if archive else 'sessions')
        folder.mkdir(exist_ok=True)
        path = folder / f'rollout-{name}.jsonl'
        path.write_text('\n'.join(json.dumps(d) for d in data) + '\n', encoding='utf-8')
        return path

    def metadata(self, **extra):
        return row({'id': 'main', 'cwd': str(self.root / 'project'), **extra}, 'session_meta')

    def digest(self, path):
        out = self.root / 'digest.md'
        with contextlib.redirect_stdout(io.StringIO()):
            sessions.cmd_digest(str(path), str(out))
        return out.read_text(encoding='utf-8')

    def test_response_item_18_user_282_assistant(self):
        data = [message('user', f'fixture user {i}') for i in range(18)]
        data += [message('assistant', f'fixture assistant {i}') for i in range(282)]
        path = self.write('counts', data)
        digest = self.digest(path)
        self.assertEqual(digest.count('USER:'), 18)
        self.assertEqual(digest.count('CODEX:'), 282)
        self.assertEqual(len(sessions.typed(path)), 18)

    def test_equivalent_encodings_and_mixed_pairs(self):
        turns = [('user', '[stage-marker] begin'), ('assistant', 'working'), ('user', 'continue')]
        response = self.write('response', [message(*m) for m in turns])
        event = self.write('event', [message(*m, 'event_msg') for m in turns])
        mixed = self.write('mixed', [r for m in turns for r in (message(*m), message(*m, 'event_msg'))])
        self.assertEqual(self.digest(response), self.digest(event))
        self.assertEqual(self.digest(mixed), self.digest(event))
        self.assertEqual(sessions.typed(response), sessions.typed(mixed))
        canonical = sessions.messages(mixed)
        self.assertEqual(len(canonical), 3)
        self.assertEqual({p['encoding'] for p in canonical[0]['provenance']}, {'event_msg', 'response_item'})

    def test_identical_separate_turns_are_preserved(self):
        data = []
        for turn in ('a', 'b'):
            data += [row({'turn_id': turn}, 'turn_context'), message('user', 'again'),
                     message('user', 'again', 'event_msg'), message('assistant', 'done'),
                     message('assistant', 'done', 'event_msg')]
        path = self.write('turns', data)
        self.assertEqual(sessions.typed(path), ['again', 'again'])
        self.assertEqual(self.digest(path).count('CODEX: done'), 2)
        event_only = self.write('same-events', [message('user', 'again', 'event_msg')] * 2)
        self.assertEqual(sessions.typed(event_only), ['again', 'again'])
        response_only = self.write('same-responses', [message('user', 'again')] * 2)
        self.assertEqual(sessions.typed(response_only), ['again', 'again'])

    def test_text_blocks_ignore_nontext_and_untrusted_shapes(self):
        self.assertEqual(sessions.text_of([{'type': 'input_text', 'text': 'first'},
                                           {'type': 'image', 'text': 'fake'},
                                           {'type': 'output_text', 'text': 'second'},
                                           {'type': 'output_text', 'text': None}, None]), 'first\nsecond')

    def test_invalid_metadata_payload_is_explicit_and_skipped(self):
        for payload in ([], ['bad'], 'bad', 42, None):
            with self.subTest(payload=payload):
                path = self.write('bad-payload', [row(payload, 'session_meta')])
                diagnostics, stderr = [], io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    self.assertEqual(sessions.meta(path, diagnostics), {})
                self.assertEqual(len(diagnostics), 1)
                self.assertEqual(diagnostics[0]['path'], str(path))
                self.assertIn('payload', diagnostics[0]['reason'])
                self.assertIn('incomplete:', stderr.getvalue())

    def test_invalid_metadata_identifiers_are_explicit_and_discovery_survives(self):
        valid = self.write('valid', [self.metadata(id='valid')])
        cases = [('id', {'id': ['bad']}),
                 ('parent_thread_id', {'cwd': None, 'parent_thread_id': ['bad']}),
                 ('parent_session_id', {'cwd': None, 'parent_session_id': {'bad': 'id'}}),
                 ('resumed_from_id', {'cwd': None, 'resumed_from_id': ['bad']}),
                 ('resumed_from.thread_id', {'resumed_from': {'thread_id': ['bad']}}),
                 ('continuation_of.session_id', {'continuation_of': {'session_id': 1}}),
                 ('continued_from.id', {'continued_from': {'id': False}}),
                 ('forked_from_id', {'forked_from_id': 1}),
                 ('source.resume.id', {'source': {'resume': {'id': ['bad']}}}),
                 ('source.continuation.session_id', {'source': {'continuation': {'session_id': []}}}),
                 ('source.subagent.parent_thread_id', {'source': {'subagent': {'parent_thread_id': []}}}),
                 ('source.sub_agent.thread_spawn.parent_session_id',
                  {'source': {'sub_agent': {'thread_spawn': {'parent_session_id': []}}}})]
        for field, extra in cases:
            with self.subTest(field=field):
                bad = self.write('bad-id', [self.metadata(**extra)])
                diagnostics, stderr = [], io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    found = sessions.project_rollouts(str(self.root / 'project'), diagnostics=diagnostics)
                self.assertEqual([p for p, _ in found], [valid])
                self.assertEqual(len(diagnostics), 1)
                self.assertEqual(diagnostics[0]['path'], str(bad))
                self.assertIn(field, diagnostics[0]['reason'])
                self.assertIn('incomplete:', stderr.getvalue())

    def test_invalid_metadata_shapes_are_explicit(self):
        cases = [('cwd', {'cwd': []}), ('source', {'source': []}),
                 ('source.subagent', {'source': {'subagent': []}}),
                 ('source.sub_agent.thread_spawn', {'source': {'sub_agent': {'thread_spawn': []}}}),
                 ('resumed_from', {'resumed_from': []}),
                 ('source.resume', {'source': {'resume': []}}),
                 ('agent_role', {'agent_role': []}),
                 ('source.subagent.thread_spawn.agent_type',
                  {'source': {'subagent': {'thread_spawn': {'agent_type': []}}}})]
        for field, extra in cases:
            with self.subTest(field=field):
                path = self.write('bad-shape', [self.metadata(**extra)])
                diagnostics = []
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(sessions.meta(path, diagnostics), {})
                self.assertEqual(len(diagnostics), 1)
                self.assertIn(field, diagnostics[0]['reason'])

    def test_valid_legacy_metadata_shapes_and_lineage_are_preserved(self):
        variants = [{'source': 'cli', 'parent_thread_id': None},
                    {'source': 'subagent'}, {'source': {'subagent': 'review'}},
                    {'source': {'sub_agent': {'thread_spawn': {'parent_session_id': 'base'}}}},
                    *[{key: {'thread_id': 'base'}} for key in
                      ('resumed_from', 'continuation_of', 'continued_from', 'forked_from_id')],
                    {'source': {'resume': {'session_id': 'base'}}},
                    {'source': {'continuation': {'id': 'base'}}}]
        for extra in variants:
            with self.subTest(extra=extra):
                payload = self.metadata(**extra)['payload']
                path = self.write('legacy-meta', [row(payload, 'session_meta')])
                diagnostics, stderr = [], io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    self.assertEqual(sessions.meta(path), payload)
                    self.assertEqual(sessions.meta(path, diagnostics), payload)
                self.assertEqual(diagnostics, [])
                self.assertEqual(stderr.getvalue(), '')

    def test_common_roots_roles_and_project_readers(self):
        project, worktree, legacy = (self.root / n for n in ('project', 'worktree', 'legacy'))
        project.mkdir()
        link = self.root / 'alias'
        link.symlink_to(project, target_is_directory=True)
        git = subprocess.CompletedProcess([], 0, f'worktree {project}\n\nworktree {worktree}\n', '')
        with mock.patch.object(sessions.subprocess, 'run', return_value=git):
            expected = sorted(os.path.realpath(p) for p in (project, worktree, legacy))
            self.assertEqual(sessions.roots_of(str(link), [str(legacy)]), expected)
            self.assertEqual(logs.roots_of(str(link), [str(legacy)]), expected)
            for name, cwd in [('main', project), ('worktree', worktree), ('old', legacy)]:
                self.write(name, [self.metadata(id=name, cwd=str(cwd)), message('user', name)])
            agent = self.write('agent', [self.metadata(id='agent', cwd=str(worktree), source={
                'subagent': {'thread_spawn': {'parent_thread_id': 'main', 'agent_type': 'impl-medium'}}})])
            self.write('foreign', [self.metadata(id='foreign', cwd=str(self.root / 'unrelated'))])
            found = sessions.project_rollouts(str(link), [str(legacy)])
            self.assertEqual(len(found), 4)
            self.assertEqual(sessions.role_of(sessions.meta(agent)), 'impl-medium')
            self.assertEqual(logs.role_of(sessions.meta(agent)), 'impl-medium')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                sessions.cmd_list(str(link), None, [str(legacy)])
            self.assertEqual(len(output.getvalue().splitlines()), 3)
            self.assertNotIn(str(agent), output.getvalue())

    def test_role_parent_and_source_variants(self):
        for metadata in ({'parent_thread_id': 'p'}, {'parent_session_id': 'p'},
                         {'source': {'sub_agent': {'thread_spawn': {'parent_thread_id': 'p'}}}}):
            self.assertEqual(sessions.role_of(metadata), logs.role_of(metadata))
            self.assertIsNotNone(sessions.role_of(metadata))
        self.assertIsNone(sessions.role_of({'source': 'cli'}))
        self.assertIsNone(sessions.role_of({'resumed_from_id': 'p'}))

    def test_archives_compression_and_lineage(self):
        base = self.write('base', [self.metadata(id='base'), message('user', '[marker]')])
        continuation = self.write('continued', [row({'id': 'next', 'resumed_from_id': 'base'}, 'session_meta'),
                                               message('user', '[marker]'), message('user', 'next')], archive=True)
        compressed = continuation.with_suffix('.jsonl.gz')
        with gzip.open(compressed, 'wt', encoding='utf-8') as stream:
            stream.write(continuation.read_text())
        continuation.unlink()
        found = sessions.project_rollouts(str(self.root / 'project'))
        self.assertEqual({p for p, _ in found}, {base, compressed})
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            sessions.cmd_list(str(self.root / 'project'), None, [])
        self.assertIn(f'# повтор {sessions.sid(compressed)}:', output.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            sessions.cmd_mine(str(self.root / 'project'), '[marker]', str(self.root / 'mine.md'))
        self.assertIn('USER: next', (self.root / 'mine.md').read_text())

    def test_same_prefix_without_lineage_is_not_a_continuation(self):
        self.write('one', [self.metadata(id='one'), message('user', 'same', 'event_msg')])
        self.write('two', [self.metadata(id='two'), message('user', 'same', 'event_msg'),
                           message('user', 'different', 'event_msg')])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            sessions.cmd_list(str(self.root / 'project'), None, [])
        self.assertNotIn('# повтор', output.getvalue())

    def test_corruption_missing_decompressor_and_absent_home_are_explicit(self):
        path = self.write('truncated', [message('user', 'valid')])
        with path.open('a') as stream:
            stream.write('{"type":\n')
        diagnostics = []
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(len(list(sessions.records(path, diagnostics=diagnostics))), 1)
        self.assertTrue(diagnostics)
        self.assertIn('invalid', diagnostics[0]['reason'])
        zst = self.home / 'sessions/rollout-zstd.jsonl.zst'
        zst.write_bytes(b'sanitized compressed placeholder')
        diagnostics = []
        with mock.patch.object(sessions.shutil, 'which', return_value=None), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(list(sessions.records(zst, diagnostics=diagnostics)), [])
        self.assertIn('zstd', diagnostics[0]['reason'])
        broken = self.home / 'sessions/rollout-broken.jsonl.gz'
        broken.write_bytes(b'invalid gzip')
        diagnostics = []
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(list(sessions.records(broken, diagnostics=diagnostics)), [])
        self.assertTrue(diagnostics)
        diagnostics = []
        with mock.patch.object(sessions, 'HOME', self.root / 'absent'), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(sessions.rollouts(diagnostics=diagnostics), [])
        self.assertTrue(diagnostics)

    def test_mine_uses_response_marker_in_worktree_and_excludes_agents(self):
        worktree = self.root / 'worktree'
        self.write('main', [self.metadata(cwd=str(worktree)), message('user', '[marker] start')])
        self.write('agent', [self.metadata(parent_thread_id='main', cwd=str(worktree)),
                             message('user', '[marker] wrong')])
        git = subprocess.CompletedProcess([], 0, f'worktree {worktree}\n', '')
        with mock.patch.object(sessions.subprocess, 'run', return_value=git), contextlib.redirect_stdout(io.StringIO()):
            out = self.root / 'mine.md'
            sessions.cmd_mine(str(self.root / 'project'), '[marker]', str(out))
        self.assertIn('USER: [marker] start', out.read_text())
        self.assertNotIn('wrong', out.read_text())

    def test_guard_codex_only_sorted_timestamps_and_timezone_since(self):
        project = self.root / 'project'
        home = self.root / 'user'
        claude = home / '.claude/dev-pipeline-feedback/.guard'
        codex = self.home / 'dev-pipeline-feedback/.guard'
        for folder in (claude, codex):
            folder.mkdir(parents=True)
        (claude / 'project.jsonl').write_text(json.dumps({'ts': '2026-12-01T00:00:00Z', 'rule': 'other'}))
        rows = [{'ts': '2027-01-01T00:00:00Z', 'rule': 'other'},
                {'ts': '2026-12-01T00:00:00Z', 'rule': 'other'},
                {'ts': '2026-11-30T23:30:00-02:00', 'rule': 'other'},
                {'ts': '2026-01-01T00:00:00Z', 'rule': 'other'}]
        (codex / 'project.jsonl').write_text('\n'.join(map(json.dumps, rows)))
        with mock.patch.object(guard.Path, 'home', return_value=home), \
             mock.patch.dict(os.environ, {'CODEX_HOME': str(self.home)}), \
             mock.patch.object(sys, 'argv', ['guard_report.py', str(project), '--since', '2026-12-01T00:00:00Z']):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                guard.main()
        self.assertIn('Всего: 3 (2026-12-01 — 2027-01-01)', output.getvalue())


if __name__ == '__main__':
    unittest.main()
