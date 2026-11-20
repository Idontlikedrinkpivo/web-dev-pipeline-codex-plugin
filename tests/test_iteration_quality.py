"""Public Codex entry points for the 2.3.0 review findings, against a disposable project."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SKILLS = Path(__file__).resolve().parents[1] / 'dev-pipeline/skills'
UI = SKILLS / 'ui-test-cases/scripts'
PIPE = SKILLS / 'pipeline/scripts'


class IterationQuality(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                        GIT_OPTIONAL_LOCKS='0', CODEX_THREAD_ID='parent', PYTHONDONTWRITEBYTECODE='1')
        self.run_cmd('git', 'init', '-q', '-b', 'iteration/1.1.0')
        self.run_cmd('git', 'config', 'user.name', 'Fixture')
        self.run_cmd('git', 'config', 'user.email', 'test@example.invalid')

    def run_cmd(self, *argv, success=True):
        result = subprocess.run(argv, cwd=self.root, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def write(self, file, body):
        path = self.root / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)

    def commit(self):
        self.run_cmd('git', 'add', '.')
        self.run_cmd('git', 'commit', '-qm', 'fixture')

    def test_import_graph_and_both_case_selectors(self):
        self.write('web/tsconfig.json', '{"compilerOptions":{"paths":{"@/*":["src/*"]}}}')
        self.write('web/src/shared.ts', 'export const value = 1;')
        self.write('web/src/button.ts', 'export const button = 1;')
        self.write('web/src/layout.tsx', 'import "@/button";')
        for i in (1, 2):
            self.write(f'web/src/pages/p{i}.tsx', f'// S-{i}\nimport "@/shared";\n' +
                       ('import "@/button";' if i == 1 else ''))
        self.write('api/handler.py', 'value = 1')
        cases = 'documentation/ui/test-cases/cases.md'
        self.write(cases, '\n'.join(f'## TC-{i}. Case\n**Экран:** S-{i}\n' +
                                    ('**Сквозной:** да\n' if i == 3 else '') +
                                    '<sub>Трассировка: шаг 1</sub>\n' for i in range(1, 5)))
        self.commit()
        self.run_cmd('git', 'tag', 'v1.0.0')
        for path, expected in [('web/src/shared.ts', ['S-1', 'S-2']),
                               ('web/src/button.ts', ['S-1', 'каркас']),
                               ('api/handler.py', ['другой код'])]:
            result = self.run_cmd(sys.executable, UI / 'code_reach.py', '.', path)
            self.assertEqual([line.split('\t')[0] for line in result.splitlines()], expected)
        self.write('web/src/button.ts', 'export const button = 2;')
        self.write('api/handler.py', 'value = 2')
        self.write('documentation/ui/screen-specs/S-4-elsewhere.md', '# S-4\n')
        self.commit()
        for code_only, expected in [(False, {'TC-1', 'TC-3', 'TC-4'}), (True, {'TC-1', 'TC-3'})]:
            flag = ['--code-only'] if code_only else []
            output = self.run_cmd(sys.executable, UI / 'affected_cases.py', '.', '--since', 'v1.0.0', *flag)
            self.assertEqual({l.split('\t')[0] for l in output.splitlines() if l.startswith('TC-')}, expected)
            for label in ('каркас приложения', 'код вне экранов', 'сквозной'):
                self.assertIn(label, output)
            manifest = json.loads(self.run_cmd(sys.executable, UI / 'acceptance_scope.py', 'select', '.',
                                  '--base', 'v1.0.0', '--out', 'documentation/plans/1.1.0/ui-acceptance.json', *flag))
            self.assertEqual(set(manifest['selected']), expected)
            self.assertEqual(manifest['outside_screens'], ['api/handler.py'])
            self.assertEqual(manifest['shell'], ['web/src/button.ts'])
        self.run_cmd('git', 'tag', 'v1.1.0')
        output = self.run_cmd(sys.executable, UI / 'affected_cases.py', '.', '--since', 'v1.1.0', '--code-only')
        self.assertIn('всего: 1 из 4', output)
        self.assertIn('TC-3\tсквозной', output)

    def test_corrections_registry_and_chat_owned_close(self):
        self.write('documentation/.dev-pipeline.json', '{}')
        self.commit()
        cmd = [sys.executable, PIPE / 'subsessions.py', '.', '1.1.0']
        self.run_cmd(*cmd, 'plan', 'srs')
        self.run_cmd(*cmd, 'authorize', 'srs')
        self.run_cmd(*cmd, 'set', '1', 'local_ab1234')
        self.run_cmd(*cmd, 'mark', '1', 'закрыт')
        self.run_cmd(*cmd, 'add', 'srs')
        self.run_cmd(*cmd, 'add', 'srs')
        self.run_cmd(*cmd, 'set', '2', 'new-child', success=False)
        self.run_cmd(*cmd, 'authorize', 'srs')
        self.assertIn('правки закрытых этапов', self.run_cmd(*cmd, 'show'))
        self.run_cmd(*cmd, 'set', '2', 'new-child')
        self.assertIn('закрыт', self.run_cmd(*cmd, 'whoami', 'ab1234'))
        self.env['CODEX_THREAD_ID'] = 'ab1234'
        self.assertIn('родительская сессия — parent', self.run_cmd(*cmd, 'whoami', 'local_ab1234'))
        dir_ = Path(self.run_cmd(*cmd, 'handover-dir').strip())
        self.assertIn('проверки передачи не было', self.run_cmd(*cmd, 'closing', 'srs', 'db', success=False))
        (dir_ / 'handover-srs.md').write_text('Ответы пользователя')
        self.assertIn('нет отчёта', self.run_cmd(*cmd, 'closing', 'srs', 'db', success=False))
        (dir_ / 'handover-srs-report.md').write_text('STATUS MISSING')
        self.assertIn('коммита после', self.run_cmd(*cmd, 'closing', 'srs', 'db', success=False))
        (dir_ / 'handover-srs-report.md').write_text('STATUS ALL ON DISK')
        self.assertIn('ЭТАП SRS ЗАКРЫТ', self.run_cmd(*cmd, 'closing', 'srs', 'db'))
        self.env['CODEX_THREAD_ID'] = 'new-child'
        self.run_cmd(*cmd, 'closing', 'srs', 'db', success=False)

    def test_migrations_freeze_at_release_and_resolved_question_is_not_pending(self):
        migration = 'documentation/db/migrations/0001_base.sql'
        checker = SKILLS / 'doc-versioning/scripts/doc_check.py'
        self.write(migration, 'select 1;')
        self.commit()
        self.run_cmd('git', 'tag', 'v1.0.0')
        self.write('documentation/db/migrations/0002_new.sql', 'select 2;')
        self.commit()
        self.write('documentation/db/migrations/0002_new.sql', 'select 3;')
        self.assertIn('проблем 0', self.run_cmd(sys.executable, checker, '.'))
        self.write(migration, 'select 9;')
        self.assertIn('0001_base.sql', self.run_cmd(sys.executable, checker, '.', success=False))
        self.write('documentation/db/open-questions.md', '# Открытые вопросы\n| Вопрос | Класс | Сейчас |\n'
                   '|---|---|---|\n| Q1 | Блокирует старт | Решено: §2 |\n| Q2 | Отложено | — |\n')
        output = self.run_cmd(sys.executable, SKILLS / 'doc-versioning/scripts/open_questions.py', '.', '--pending')
        self.assertNotIn('Блокирует старт', output)
        self.assertIn('Отложено: 1', output)

    def test_tag_requires_finished_full_run_section(self):
        report = 'documentation/plans/1.1.0/test-run.md'
        self.write(report, '# Итоги\n')
        self.commit()
        def gate():
            output = self.run_cmd(sys.executable, PIPE / 'close_iteration.py', '.', success=False)
            return next(line for line in output.splitlines() if '3b полный набор' in line)
        self.assertTrue(gate().startswith('✗'))
        self.write(report, '## Полный набор перед меткой\n## Другой раздел\nПропущен — причина\n')
        self.assertTrue(gate().startswith('✗'))
        self.write(report, '## Полный набор перед меткой · завершён\n')
        self.assertTrue(gate().startswith('✅'))
        self.write(report, '## Полный набор перед меткой\nПропущен — пользователь отказался\n')
        self.assertTrue(gate().startswith('✅'))

    def test_hook_checks_each_git_target_and_scopes_packet_edits(self):
        self.write('documentation/.dev-pipeline.json', '{}')
        self.commit()
        stream = self.root / 'wt-one'
        self.run_cmd('git', 'worktree', 'add', '--detach', str(stream))
        guard = SKILLS.parent / 'hooks/guard.py'
        def invoke(tool, inp, cwd):
            result = subprocess.run([sys.executable, guard], input=json.dumps(dict(tool_name=tool,
                                    tool_input=inp, cwd=str(cwd))), text=True, capture_output=True, check=True)
            return result.stdout
        for command in ('git -C "wt-one" reset --hard', 'cd "wt-one" && git checkout -- . && git clean -f'):
            self.assertEqual(invoke('exec_command', {'cmd': command}, self.root), '')
        self.assertIn('deny', invoke('exec_command', {'cmd': 'git -C wt-one reset --hard && git clean -f'}, self.root))
        self.assertIn('deny', invoke('exec_command', {'cmd': f'git -C "{self.root}" reset --hard'}, stream))
        self.assertEqual(invoke('apply_patch', {'command': '*** Add File: ' + str(self.root / '.git/pipeline-work/U1.md')}, stream), '')
        self.assertIn('deny', invoke('apply_patch', {'command': '*** Add File: '+str(self.root/'foreign')}, stream))
