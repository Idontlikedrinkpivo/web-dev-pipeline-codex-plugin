import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_close_iteration_stamp import load, ROOT

sessions = load('error_sessions', ROOT / 'dev-pipeline/skills/reflect/scripts/sessions.py')


class ErrorTests(unittest.TestCase):
    def test_nested_fulfilled_exec_is_one_failure(self):
        result = [{'status': 'fulfilled', 'value': {'content': [{'type': 'text', 'text':
                  json.dumps({'exit_code': 2, 'output': 'compiler failed', 'chunk_id': 'one'})}]}}]
        self.assertEqual([r['status'] for r in sessions.command_results(result)], ['failed'])

    def test_supported_statuses_and_duplicates(self):
        failure = {'metadata': {'exit_code': 1}, 'output': 'bad', 'call_id': 'a'}
        result = [failure, failure, {'exit_code': 0, 'output': ''},
                  {'status': 'rejected', 'reason': 'denied'}, {'exit_code': None, 'session_id': 1}]
        statuses = [r['status'] for r in sessions.command_results(result)]
        self.assertEqual(statuses.count('failed'), 2)
        self.assertEqual(statuses.count('success'), 1)
        self.assertEqual(statuses.count('unknown'), 1)

    def test_nesting_property_never_executes_code(self):
        for depth in range(20):
            value = {'exit_code': 3, 'output': '__import__("os").abort()'}
            for _ in range(depth):
                value = {'result': [value]}
            self.assertEqual(len(sessions.command_results(value)), 1)
            self.assertEqual(sessions.command_results(value)[0]['status'], 'failed')
        for value in ('', '{truncated', None, {'exit_code': 'not a number'}):
            self.assertEqual(sessions.command_results(value)[0]['status'], 'unknown')

    def test_quotes_not_commands_and_unknown_not_complete_zero(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src, out = root / 'rollout.jsonl', root / 'errors.md'
            rows = [{'type': 'message', 'payload': {'role': role, 'text': 'Exit code: 1'}} for role in ('user', 'assistant')]
            rows += [{'type': 'response_item', 'payload': {'type': 'function_call_output',
                      'call_id': 'a', 'output': '{truncated'}}]
            src.write_text('\n'.join(json.dumps(r) for r in rows))
            with mock.patch.object(sessions, 'project_rollouts', return_value=[(src, {'id': 'one'})]), contextlib.redirect_stdout(io.StringIO()):
                sessions.cmd_errors(str(root), str(out), None, [])
            self.assertIn('Вызовов с ошибкой: 0', out.read_text())
            self.assertIn('incomplete/UNKNOWN', out.read_text())

    def test_duplicate_outputs_and_unfinished_call(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src, out = root / 'rollout.jsonl', root / 'errors.md'
            result = {'type': 'response_item', 'payload': {'type': 'function_call_output',
                      'call_id': 'a', 'output': json.dumps([{'status': 'fulfilled', 'value': {'exit_code': 2, 'output': 'bad'}}])}}
            rows = [result, result, {'type': 'response_item', 'payload': {'type': 'function_call', 'call_id': 'pending', 'name': 'exec'}}]
            src.write_text('\n'.join(json.dumps(r) for r in rows))
            with mock.patch.object(sessions, 'project_rollouts', return_value=[(src, {'id': 'one'})]), contextlib.redirect_stdout(io.StringIO()):
                sessions.cmd_errors(str(root), str(out), None, [])
            self.assertIn('Вызовов с ошибкой: 1', out.read_text())
            self.assertIn('unknown: 1', out.read_text())


if __name__ == '__main__':
    unittest.main()
