"""Synthetic native/legacy transcripts and real hook stdin/stdout; no live agents."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HOOKS = Path(__file__).resolve().parents[1] / 'dev-pipeline/hooks'
sys.path.insert(0, str(HOOKS))
import guard
import progress_stop as stop

PROGRESS = 'documentation/plans/1.3.1/progress.md'
HTML = 'План: 1 из 2 · [progress.html](http://127.0.0.1:8790/progress.html)'
MD = '[progress.md](documentation/plans/1.3.1/progress.md)'


def user(text='Делай'):
    return {'type': 'user', 'message': {'content': text}}


def edit(path=PROGRESS, tool='Edit'):
    return {'type': 'assistant', 'message': {'content': [
        {'type': 'tool_use', 'name': tool, 'input': {'file_path': path, 'new_string': '✅ готово', 'content': '✅ готово'}}]}}


def call(name, args, custom=False):
    return {'type': 'response_item', 'payload': {
        'type': 'custom_tool_call' if custom else 'function_call', 'name': name,
        'input' if custom else 'arguments': args if custom else json.dumps(args)}}


def turn(identifier):
    return {'type': 'event_msg', 'payload': {'type': 'task_started', 'turn_id': identifier}}


class ProgressStopTests(unittest.TestCase):
    def decision(self, rows, text='Готово', **extra):
        return stop.decide({'cwd': '/project', 'last_assistant_message': text, **extra}, rows)

    def test_edit_or_write_without_link_blocks_with_action(self):
        for tool in ('Edit', 'Write'):
            with self.subTest(tool=tool):
                reason = self.decision([user(), edit(tool=tool)])
                self.assertIn('progress_link.py', reason)

    def test_printed_html_link_passes_for_all_progress_files(self):
        for name in ('progress', 'progress-design', 'test-run', 'security-audit'):
            with self.subTest(name=name):
                rows = [user(), edit(f'documentation/plans/1.3.1/{name}.md')]
                self.assertIsNone(self.decision(rows, f'[{name}.html](http://localhost/{name}.html)'))

    def test_md_link_blocks_even_without_changes_or_with_html(self):
        for text in (MD, MD + ' ' + HTML, '[План](http://localhost/progress.md)',
                     '[progress.html](http://localhost/progress.md)', '[test-run.md](test-run.md)'):
            with self.subTest(text=text):
                self.assertIsNotNone(self.decision([user()], text))

    def test_second_consecutive_stop_passes(self):
        for text in ('Готово', MD):
            self.assertIsNone(self.decision([user(), edit()], text, stop_hook_active=True))
        self.assertIsNotNone(self.decision([user(), edit()], stop_hook_active=False))

    def test_previous_turn_edit_and_previous_link_do_not_count(self):
        self.assertIsNone(self.decision([user('Старый ход'), edit(), user('Новый ход')]))
        rows = [user(), {'type': 'assistant', 'message': {'content': HTML}}, user(), edit()]
        self.assertIsNotNone(self.decision(rows))

    def test_codex_turn_id_overrides_user_steering_and_old_history(self):
        patch = f'*** Update File: {PROGRESS}\n@@\n-a\n+b'
        rows = [turn('old'), call('apply_patch', patch, custom=True), turn('now')]
        self.assertIsNone(self.decision(rows, turn_id='now'))
        rows += [call('functions.apply_patch', patch, custom=True),
                 {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': 'Ну как?'}}]
        self.assertIsNotNone(self.decision(rows, turn_id='now'))
        self.assertIsNone(self.decision(rows, turn_id='unseen'))

    def test_turn_context_does_not_reset_changes_on_compaction(self):
        context = {'type': 'turn_context', 'payload': {'turn_id': 'now'}}
        rows = [context, edit(), {'type': 'compacted'}, context]
        self.assertIsNotNone(self.decision(rows, turn_id='now'))

    def test_tool_result_is_not_a_user_turn(self):
        rows = [user(), edit(), {'type': 'user', 'message': {'content': [
            {'type': 'tool_result', 'content': 'ok', 'tool_use_id': '1'}]}}]
        self.assertIsNotNone(self.decision(rows))

    def test_native_commands_and_code_mode_calls(self):
        for script in ('progress_set.py', 'progress_e2e.py'):
            command = f'python3.12 "/plugin with spaces/{script}" {PROGRESS} 1 2'
            with self.subTest(script=script):
                self.assertIsNotNone(self.decision([turn('now'), call('exec_command', {'cmd': command})]))
                code = f'await tools.exec_command({json.dumps({"cmd": command})});'
                self.assertIsNotNone(self.decision([turn('now'), call('functions.exec', code, custom=True)]))
        patch = f'*** Update File: {PROGRESS}\n@@\n-a\n+b'
        code = f'await tools.apply_patch({json.dumps(patch)});'
        self.assertIsNotNone(self.decision([turn('now'), call('exec', code, custom=True)]))
        self.assertIsNotNone(self.decision([turn('now'), call('apply_patch', {'input': patch})]))

    def test_reads_mentions_and_other_files_do_not_trigger(self):
        for command in ('cat /plugin/progress_set.py', 'echo progress_e2e.py',
                        'echo python3 progress_set.py', 'python3 other.py progress_set.py',
                        'python3 other.py\necho progress_set.py',
                        'python3 progress_link.py progress.md'):
            self.assertIsNone(self.decision([user(), call('exec_command', {'cmd': command})]))
        self.assertIsNone(self.decision([user(), edit('notes.md')]))
        fake = '// await tools.exec_command({cmd:"python3 progress_set.py"});'
        self.assertIsNone(self.decision([user(), call('exec', fake, custom=True)]))
        self.assertIsNone(self.decision([user(), call('exec_command', '{broken', custom=True)]))

    def test_link_in_code_or_tool_output_is_not_an_answer(self):
        for text in ('`' + HTML + '`', '```text\n' + HTML + '\n```'):
            self.assertIsNotNone(self.decision([user(), edit()], text))
        rows = [user(), edit(), {'type': 'response_item', 'payload': {
            'type': 'function_call_output', 'output': HTML}}]
        self.assertIsNotNone(self.decision(rows))

    def test_answer_fallback_when_host_has_no_last_message(self):
        rows = [user(), edit(), {'type': 'response_item', 'payload': {
            'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': HTML}]}}]
        self.assertIsNone(stop.decide({'cwd': '/project'}, rows))

    def test_real_stop_hook_input_output_and_missing_transcript(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(['git', 'init', '-q', td], check=True)
            (root / 'documentation').mkdir()
            (root / 'documentation/.dev-pipeline.json').write_text('{}')
            transcript = root / 'synthetic.jsonl'
            transcript.write_text('\n'.join(json.dumps(row) for row in [turn('now'), edit()]))
            data = {'cwd': td, 'transcript_path': str(transcript), 'turn_id': 'now', 'last_assistant_message': 'Готово'}
            def run(**extra):
                result = subprocess.run(['sh', str(HOOKS / 'progress-stop.sh')], input=json.dumps(data | extra),
                                        text=True, capture_output=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout) if result.stdout else None
            self.assertEqual(run()['decision'], 'block')
            self.assertIsNone(run(last_assistant_message=HTML))
            self.assertIsNone(run(stop_hook_active=True))
            self.assertIsNone(run(transcript_path=str(root / 'missing.jsonl')))
            self.assertEqual(run(transcript_path='', last_assistant_message=MD)['decision'], 'block')


class ProgressBarGuardTests(unittest.TestCase):
    def test_edit_bar_threshold_and_path_scope(self):
        for cells, expected in ((19, False), (20, True), (100, True)):
            reason = guard.decide('Edit', {'file_path': PROGRESS, 'new_string': '█' * cells}, '/project')
            self.assertEqual(reason is not None, expected)
            if expected:
                self.assertIn('progress_set.py', reason)
        self.assertIsNone(guard.decide('Edit', {'file_path': 'notes.md', 'new_string': '░' * 100}, '/project'))
        self.assertIsNone(guard.decide('Write', {'file_path': PROGRESS, 'content': '░' * 100}, '/project'))

    def test_patch_only_checks_added_lines_in_updated_progress_file(self):
        old = '█' * 20 + '░' * 80
        patch = f'*** Update File: {PROGRESS}\n@@\n {old}\n-old\n+new'
        self.assertIsNone(guard.decide('apply_patch', patch, '/project'))
        for name in ('progress.md', 'test-run.md', 'security-audit.md'):
            patch = f'*** Update File: documentation/plans/1.3.1/{name}\n@@\n-old\n+{old}'
            self.assertIsNotNone(guard.decide('apply_patch', {'input': patch}, '/project'))
        patch = f'*** Update File: {PROGRESS}\n@@\n-old\n+new\n*** Update File: notes.md\n@@\n+{old}'
        self.assertIsNone(guard.decide('apply_patch', patch, '/project'))
        self.assertIsNone(guard.decide('apply_patch', f'*** Add File: {PROGRESS}\n+{old}', '/project'))

    def test_multi_edit_and_subdirectory_paths(self):
        value = {'file_path': '1.3.1/progress.md', 'edits': [{'new_string': '✅ готово'}, {'new_string': '░' * 20}]}
        self.assertIsNotNone(guard.decide('MultiEdit', value, '/project/documentation/plans'))

    def test_hooks_registered(self):
        config = json.loads((HOOKS / 'hooks.json').read_text())['hooks']
        self.assertIn('progress-stop.sh', config['Stop'][0]['hooks'][0]['command'])
        matcher = config['PreToolUse'][0]['matcher'].split('|')
        self.assertTrue({'Edit', 'apply_patch'} <= set(matcher))

    def test_real_guard_emits_pretooluse_denial(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(['git', 'init', '-q', td], check=True)
            (root / 'documentation').mkdir()
            (root / 'documentation/.dev-pipeline.json').write_text('{}')
            data = {'cwd': td, 'tool_name': 'Edit', 'tool_input': {
                'file_path': PROGRESS, 'new_string': '█' * 20}}
            result = subprocess.run(['sh', str(HOOKS / 'guard.sh')], input=json.dumps(data),
                                    capture_output=True, text=True,
                                    env=dict(os.environ, CODEX_HOME=str(root / 'home'), PYTHONDONTWRITEBYTECODE='1'))
            self.assertEqual(result.returncode, 0, result.stderr)
            decision = json.loads(result.stdout)['hookSpecificOutput']
            self.assertEqual(decision['hookEventName'], 'PreToolUse')
            self.assertEqual(decision['permissionDecision'], 'deny')
            self.assertIn('progress_set.py', decision['permissionDecisionReason'])


if __name__ == '__main__':
    unittest.main()
