"""Codex rollout fixtures: direct MCP calls, code mode and injected delegation."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'dev-pipeline/skills/reflect/scripts/sessions.py'
spec = importlib.util.spec_from_file_location('codex_sessions', SCRIPT)
sessions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sessions)


def record(payload, minute='01', kind='response_item'):
    return {'timestamp': f'2026-10-31T12:{minute}:00Z', 'type': kind, 'payload': payload}


def call(name, args, minute='01'):
    return record({'type': 'function_call', 'name': name, 'arguments': json.dumps(args)}, minute)


def injected(name, message, title='', minute='01'):
    # Shape observed in Codex Desktop 0.166 rollouts, including name/namespace
    # and codex_delegation on a function_call_output with no matching call_id.
    return record({'type': 'function_call_output', 'name': name, 'namespace': 'codex_app',
                   'output': '<codex_delegation>\n<source_thread_id>parent-1</source_thread_id>\n'
                   f'<source_thread_title>{title}</source_thread_title>\n'
                   f'<input>{message}</input>\n</codex_delegation>'}, minute)


class DigestTests(unittest.TestCase):
    def digest(self, data, since=None):
        with tempfile.TemporaryDirectory() as td:
            src, out = Path(td)/'rollout.jsonl', Path(td)/'digest.md'
            src.write_text('\n'.join(json.dumps(d, ensure_ascii=False) for d in data))
            with contextlib.redirect_stdout(io.StringIO()):
                sessions.cmd_digest(str(src), str(out), since)
            return out.read_text()

    def test_direct_chat_lifecycle_and_existing_entries(self):
        data = [
            record({'type': 'user_message', 'message': 'продолжи'}, kind='event_msg'),
            injected('create_thread', 'Ты — этап SRS, версия 1.0'),
            injected('send_message_to_thread', 'начинай', 'iteration 1.0', '02'),
            call('mcp__codex_app__create_thread', {'title': '1.0 · план', 'model': 'gpt-6.1-sol',
                                               'prompt': 'Построй план'}, '03'),
            call('mcp__codex_app__send_message_to_thread', {'threadId': 'child-1', 'prompt': 'начинай'}, '04'),
            injected('send_message', 'ЭТАП SRS ЗАКРЫТ · дальше: план', '1.0 · SRS', '05'),
            injected('send_message_to_thread', 'ПЕРЕДАН · продолжать с U2', '1.0 · прогон', '06'),
            call('codex_app.set_thread_title', {'threadId': 'child-1', 'title': '1.0 · план · готов'}, '07'),
            call('mcp__codex_app__set_thread_archived', {'threadId': 'child-1', 'archived': True}, '08'),
            call('spawn_agent', {'agent_type': 'doc-typist', 'message': 'print'}, '09'),
            call('exec_command', {'cmd': 'cat /plugin/skills/plan/SKILL.md'}, '10'),
            record({'type': 'agent_message', 'message': 'Готово'}, '11', 'event_msg'),
            record({}, '12', 'compacted'),
        ]
        text = self.digest(data)
        expected = ['USER: продолжи', 'OPENED BY SESSION: Ты — этап SRS, версия 1.0',
                    'FROM SESSION «iteration 1.0»: начинай',
                    'OPENS SESSION «1.0 · план» (gpt-6.1-sol): Построй план',
                    'TO SESSION child-1: начинай',
                    'FROM SESSION «1.0 · SRS»: ЭТАП SRS ЗАКРЫТ · дальше: план',
                    'FROM SESSION «1.0 · прогон»: ПЕРЕДАН · продолжать с U2',
                    'RENAMES: child-1 → «1.0 · план · готов»', 'ARCHIVES: child-1',
                    'AGENT: doc-typist', 'SKILL: plan', 'CODEX: Готово', '=== CONTEXT COMPACTED ===']
        positions = [text.index(s) for s in expected]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(text.count('OPENED BY SESSION:'), 1)

    def test_code_mode_literal_calls_and_no_execution_or_false_matches(self):
        code = '''
text(await tools.mcp__codex_app__create_thread({target:{type:"projectless"},
title:"План",prompt:"Составь план: \\"A\\"",model:"gpt-6.1-sol"}));
await tools.mcp__codex_app__send_message_to_thread({threadId:'child', prompt:'начинай'});
await tools.mcp__codex_app__set_thread_title({threadId:"child",title:"Готово"});
await tools.mcp__codex_app__set_thread_archived({threadId:"child",archived:true});
// tools.mcp__codex_app__create_thread({prompt:"comment",title:"FAKE"})
await tools.exec_command({cmd:'tools.create_thread({prompt:"quoted",title:"FAKE"})'});
await tools.create_thread({prompt:dynamicVariable,title:"UNKNOWN"});
await tools.send_message({target:"agent",message:"not a chat"});
'''
        text = self.digest([record({'type': 'custom_tool_call', 'name': 'exec', 'input': code})])
        self.assertIn('OPENS SESSION «План» (gpt-6.1-sol): Составь план: "A"', text)
        self.assertIn('TO SESSION child: начинай', text)
        self.assertIn('RENAMES: child → «Готово»', text)
        self.assertIn('ARCHIVES: child', text)
        self.assertNotIn('FAKE', text)
        self.assertNotIn('UNKNOWN', text)
        self.assertNotIn('not a chat', text)

    def test_since_missing_title_malformed_input_and_multiline(self):
        data = [injected('create_thread', 'old', minute='00'),
                injected('send_message_to_thread', 'ЭТАП ЗАКРЫТ\nA &amp; B', minute='02'),
                call('create_thread', {'title': 'next', 'prompt': 'new'}, '03'),
                record({'type': 'function_call', 'name': 'create_thread', 'arguments': '{broken'}, '04'),
                record({'type': 'function_call_output', 'name': 'send_message_to_thread',
                        'output': 'quoted <codex_delegation><input>FAKE</input></codex_delegation>'}, '05')]
        text = self.digest(data, '2026-10-31T12:02')
        self.assertNotIn('OPENED BY SESSION', text)
        self.assertIn('FROM SESSION «parent-1»: ЭТАП ЗАКРЫТ\nA & B', text)
        self.assertIn('OPENS SESSION «next» (default): new', text)
        self.assertNotIn('FAKE', text)
        self.assertEqual(text.count('OPENS SESSION'), 1)

    def test_digest_cli(self):
        with tempfile.TemporaryDirectory() as td:
            src, out = Path(td)/'rollout.jsonl', Path(td)/'digest.md'
            src.write_text(json.dumps(injected('create_thread', 'этап'), ensure_ascii=False))
            result = subprocess.run([sys.executable, str(SCRIPT), 'digest', str(src), str(out)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('OPENED BY SESSION: этап', out.read_text())


if __name__ == '__main__':
    unittest.main()
