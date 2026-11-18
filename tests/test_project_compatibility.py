"""Legacy and nested pipeline projects, using the public commands."""
import json
import os
from pathlib import Path
import subprocess
import sys

from test_close_iteration_stamp import RepoTest, ROOT

PLUGIN = ROOT / 'dev-pipeline'


class Compatibility(RepoTest):
    def hook(self, name, **data):
        return subprocess.run(['sh', str(PLUGIN / 'hooks' / name)], input=json.dumps(data),
                              env=dict(os.environ, CODEX_HOME=str(self.root.parent / 'host')),
                              capture_output=True, text=True, check=True).stdout

    def test_legacy_nested_hooks_follow_same_project(self):
        path = 'v2/documentation/plans/1.0.0/progress.md'
        self.write(path, '# Progress\n')
        self.commit('old project with plans only')
        for where in (self.root, self.root / 'v2'):
            relative = (self.root / path).relative_to(where).as_posix()
            result = self.hook('guard.sh', cwd=str(where), tool_name='exec_command',
                               tool_input={'cmd': 'echo changed > ' + relative})
            self.assertEqual(json.loads(result)['hookSpecificOutput']['permissionDecision'], 'deny')
            stopped = self.hook('progress-stop.sh', cwd=str(where), last_assistant_message=f'[progress.md]({relative})')
            self.assertEqual(json.loads(stopped)['decision'], 'block')
        self.hook('progress-page.sh', cwd=str(self.root), tool_input={'file_path': path})
        self.assertTrue((self.root / path).with_suffix('.html').exists())

    def test_browser_migration_respects_existing_labels(self):
        script = PLUGIN / 'skills/upgrade-docs/scripts/project_format.py'
        for title, pending in [('Совместимость API', True), ('Совместимость браузеров', False),
                               ('Поддерживаемые браузеры', False), ('Поддерживаются браузеры', False)]:
            self.write('documentation/requirements/srs/srs.md', f'# SRS\n## НФТ\n| NFR-1 | {title} |\n')
            out = subprocess.check_output([sys.executable, script, 'list', self.root, '--kind', 'docs', '--json'])
            self.assertEqual('srs-browsers-row' in [row['id'] for row in json.loads(out)], pending)

    def test_auto_selection_and_conservative_fallback(self):
        script = PLUGIN / 'skills/ui-test-cases/scripts/acceptance_scope.py'
        casefile = 'documentation/ui/test-cases/booking.md'
        self.write(casefile, ''.join(f'## TC-{n}. Test\n**Экран:** S-{n}\n**Проверяет:** BR-{n}\n'
                                     f'<sub>Трассировка: `op{n}` → 200</sub>\n' for n in range(1, 6)))
        api = 'documentation/api/openapi.yaml'
        contract = 'paths:\n' + ''.join(f'  /p{n}:\n    get:\n      operationId: op{n}\n      summary: old{n}\n'
                                        for n in (1, 2))
        self.write(api, contract)
        srs = 'documentation/requirements/srs/srs.md'
        self.write(srs, '### BR-2\nformer\n')
        self.commit('base')
        base = self.git('rev-parse', 'HEAD')
        self.git('switch', '-qc', 'iteration/1.0.1')
        plan = 'documentation/plans/1.0.1/'
        self.write(plan + 'plan.md', '### U1. View\n| **Файлы** | `src/view.ts` |\n| **Документы** | S-3 |\n')
        self.write('src/view.ts', 'changed')
        self.write(api, contract.replace('old1', 'new1'))
        self.write(srs, '### BR-2\nchanged\n')
        self.write(plan + 'test-run.md', '## Прогон 1 — UI\n| TC | Статус |\n| TC-4 | ❌ |\n| TC-5 | ❌ |\n'
                   '## Прогон 1 · повтор 1\n| TC | Статус |\n| TC-5 | ✅ |\n')
        def selected():
            args = [sys.executable, script, 'select', self.root, '--base', base, '--out', plan + 'ui-acceptance.json']
            return json.loads(subprocess.check_output(args))['selected']
        result = selected()
        self.assertEqual(set(result), {'TC-1', 'TC-2', 'TC-3', 'TC-4'})
        self.assertIn('op1', result['TC-1'][0])
        self.assertIn('BR-2', result['TC-2'][0])
        self.assertIn('U1', result['TC-3'][0])
        self.assertEqual(result['TC-4'], ['previous failure'])
        self.write('unknown.ts', 'shared change')
        self.assertIn('conservative full set: uncertain mapping', selected()['TC-5'])

    def test_nested_report_commit_preserves_full_run_and_changed_case_scope(self):
        script = PLUGIN / 'skills/ui-test-cases/scripts/acceptance_scope.py'
        path = 'v2/documentation/ui/test-cases.md'
        original = '## TC-1. First\nS-1\n## TC-2. Other\nS-2\n'
        self.write(path, original)
        self.commit('base')
        base = self.git('rev-parse', 'HEAD')
        self.git('switch', '-qc', 'iteration/1.0.1')
        self.write(path, original.replace('First', 'Changed'))
        self.commit('change one case')
        project = self.root / 'v2'
        output = 'documentation/plans/1.0.1/ui-acceptance.json'
        def run(command, *args):
            return json.loads(subprocess.check_output([sys.executable, script, command, project, *args]))
        selection = run('select', '--base', base, '--out', output)
        self.assertEqual(selection['selected'], {'TC-1': ['added/changed case']})
        run('record', '--manifest', output, '--scope', 'full', '--status', 'pass',
            '--tool', 'fixture', '--stand', 'local', '--evidence', 'observed fixture')
        self.commit('acceptance report')
        self.assertTrue(run('check', '--manifest', output)['current'])

    def test_screen_writer_has_legacy_date_rule_and_gap_ownership(self):
        skills = PLUGIN / 'skills'
        screen = (skills / 'screen-spec/SKILL.md').read_text()
        self.assertIn('../srs-writer/references/date-time-contract.md', screen)
        rule = (skills / 'srs-writer/references/date-time-contract.md').read_text().split(
            '## Screen specs for an older SRS')[1].split('## Downstream ownership')[0]
        for invariant in ('format: date', 'instant', 'explicitly linked', 'display zone',
                          'against the SRS', 'against the API'):
            self.assertIn(invariant, rule)
