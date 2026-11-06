"""Readable progress, scoped timestamps and diagnostics on representative files."""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'dev-pipeline'
SCRIPTS = ROOT / 'skills/pipeline/scripts'
sys.path.insert(0, str(SCRIPTS))
import progress_page as page
import progress_link as link
import progress_set as setter
import progress_e2e as e2e


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = load('progress_checker', ROOT / 'check_plugin.py')
measure = load('progress_measure', ROOT / 'skills/reflect/scripts/measure.py')
where = load('progress_where', SCRIPTS / 'where_am_i.py')


def section(title, rows, state='Состояние: идёт работа', count='Готово: 0 из 2'):
    return (f'{title}\n\n```text\n' + '░' * 100 + ' 0%\n```\n\n' + count + '\n\n'
            '| № | Статус |\n|---|---|\n' +
            ''.join(f'| {i} | {status} |\n' for i, status in enumerate(rows, 1)) +
            f'\n{state} · обновлено 2000-01-01 00:00\n')


class ProgressViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def md(self, name, text):
        path = self.folder / name
        path.write_text(text)
        return path

    def test_link_warns_unknown_status_stamps_and_rebuilds_before_printing(self):
        md = self.md('progress.md', section('# План', ['✅ закоммичен', '⏳ ждёт']))
        out, err = io.StringIO(), io.StringIO()
        with patch.object(sys, 'argv', ['progress_link.py', str(md)]), \
             patch.object(link, 'start', return_value='http://127.0.0.1:8790/'), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            link.main()
        self.assertIn('неизвестный статус', err.getvalue())
        self.assertIn('✅ закоммичен', err.getvalue())
        self.assertRegex(err.getvalue(), r'progress\.md:\d+:')
        self.assertEqual(len(out.getvalue().splitlines()), 1)
        self.assertTrue(out.getvalue().startswith('План:'))
        self.assertNotIn('2000-01-01', md.read_text())
        html = md.with_suffix('.html').read_text()
        self.assertIn('<div class="stage">План</div>', html)
        self.assertIn('доля готовых задач', html)
        self.assertIn('<strong>Состояние:</strong>', html)
        self.assertNotIn('2000-01-01', html)

    def test_derived_deploy_separates_skips(self):
        md = self.md('progress-deploy.md', section('# Релиз', ['✅ готово · release/1.3.1'] * 6 +
                                                  ['⏭ пропущено: не нужно'] * 5))
        self.assertEqual(page.derived(md.read_text()), (100, 'Готово: 6 из 11 · пропущено 5'))
        page.page(md)
        html = md.with_suffix('.html').read_text()
        self.assertIn('Готово: 6 из 11 · пропущено 5', html)
        self.assertIn('✅ готово: 6', html)
        self.assertIn('по строкам: готово и пропущено', html)
        self.assertEqual(link.warnings(md), [])

    def test_setter_stamps_only_its_section_and_keeps_others(self):
        top = section('# План', ['⏳ ждёт'])
        fixes = section('## Исправления', ['⏳ ждёт'], state='Состояние: вердикт RETURN_TO_UNIT')
        tail = section('## e2e', ['⏳ ждёт'])
        md = self.md('progress.md', top + fixes + tail)
        with patch.object(sys, 'argv', ['progress_set.py', str(md), '1', '2', '--section', '## Исправления']), \
             contextlib.redirect_stdout(io.StringIO()):
            setter.main()
        text = md.read_text()
        self.assertTrue(text.startswith(top))
        self.assertTrue(text.endswith(tail))
        changed = text[len(top):-len(tail)]
        self.assertIn('Готово: 1 из 2', changed)
        self.assertIn('█' * 50 + '░' * 50 + ' 50%', changed)
        self.assertNotIn('2000-01-01', changed)
        html = md.with_suffix('.html').read_text()
        self.assertIn('доля исправленных замечаний', html)
        self.assertIn('доля успешных тестов', html)

    def test_setter_does_not_stamp_a_later_section_when_state_absent(self):
        top = section('# План', ['⏳ ждёт']).split('Состояние:')[0]
        tail = section('## e2e', ['⏳ ждёт'])
        md = self.md('progress.md', top + tail)
        with patch.object(sys, 'argv', ['progress_set.py', str(md), '1', '2']), \
             contextlib.redirect_stdout(io.StringIO()):
            setter.main()
        self.assertTrue(md.read_text().endswith(tail))

    def test_status_details_and_ui_outcomes_are_valid(self):
        statuses = ['✅ прошёл', '❌ не прошёл', '⛔ заблокирован: API', '⏭ не автоматизирован: позже',
                    '✅ тест исправлен, прошёл', '⛔ тест не удалось исправить', '❌ дефект приложения',
                    '🖼 расхождение с макетом', '❓ пробел в ТЗ', '🔍 разбор · TC-3']
        md = self.md('test-run.md', section('# UI', statuses, state='Verdict: DEFECTS'))
        self.assertEqual(link.warnings(md), [])
        page.page(md)
        self.assertIn('<strong>Verdict:</strong>', md.with_suffix('.html').read_text())
        self.assertEqual(page.status_word('✅ готово · release/1.3.1: details'), '✅ готово')

    def test_each_bar_needs_count_except_derived(self):
        text = section('# План', ['⏳ ждёт']) + section('## Исправления', ['⏳ ждёт'], count='')
        md = self.md('progress.md', text)
        self.assertEqual(len(link.warnings(md)), 1)
        self.assertIn('Исправления', link.warnings(md)[0])
        md = self.md('progress-deploy.md', text)
        self.assertEqual(link.warnings(md), [])

    def test_stamp_respects_start_and_initializes_template(self):
        text = 'обновлено 2000-01-01 00:00\nобновлено …\nобновлено 2001-01-01 00:00'
        first, rest = text.split('\n', 1)
        result = page.stamp(text, len(first) + 1)
        self.assertTrue(result.startswith(first + '\n'))
        self.assertTrue(result.endswith('обновлено 2001-01-01 00:00'))
        self.assertNotIn('…', result)

    def test_audit_state_does_not_use_its_machine_verdict(self):
        text = 'Verdict: идёт аудит\n' + section('# Аудит', ['⏳ ждёт'])
        self.assertTrue(page.lines_of(text)[1].startswith('Состояние:'))

    def test_setter_does_not_stamp_a_table_detail(self):
        md = self.md('progress.md', section('# План', ['✅ готово: обновлено 1999-01-01 00:00']))
        with patch.object(sys, 'argv', ['progress_set.py', str(md), '1', '1']), \
             contextlib.redirect_stdout(io.StringIO()):
            setter.main()
        self.assertIn('1999-01-01 00:00', md.read_text())
        self.assertNotIn('2000-01-01', md.read_text())

    def test_closed_work_recognizes_new_state_and_legacy_review_line(self):
        import stage_readiness as ready
        stage = next(name for name, number in where.QUESTION_STAGES.items() if number == 12)
        for state in ('Финальное ревью: PASS',
                      'Состояние: готово · финальное ревью PASS · BASE abc · обновлено …',
                      'Состояние: финальное ревью не запускалось · обновлено …'):
            with self.subTest(state=state), patch.object(where.oq, 'scan', return_value=[]), \
                 patch.object(where.oq, 'pending_lines', return_value=[]), \
                 patch.object(where.oq, 'groups', return_value={stage: ['question']}), \
                 patch.object(ready, 'skips', return_value=set()), patch.object(ready, 'closed', return_value=False), \
                 patch.object(where, 'progress', return_value=[('progress.md', 'work', '', 1, 1, 0)]), \
                 patch.object(where, 'read', return_value=state):
                points = where.question_points(self.folder, '1.3.1', [])
                self.assertEqual(bool(points), 'PASS' not in state)

    def test_e2e_skips_use_detail_separator_and_state(self):
        text = e2e.section({('', 'a.spec.ts', '1:1', 'case'): 'skip'}, 1, 'local', True)
        self.assertIn('✅ прошёл: есть пропуски', text)
        self.assertIn('Состояние: прогон закончен · стенд: local · обновлено', text)
        md = self.md('progress.md', text)
        self.assertEqual(link.warnings(md), [])

    def test_checker_reports_mismatches_and_missing_keys(self):
        self.assertEqual(checker.progress_labels(ROOT), [])
        scripts = self.folder / 'skills/pipeline/scripts'
        scripts.mkdir(parents=True)
        (scripts / 'progress_page.py').write_text("FILES = {'progress.md': 'Код', 'extra.md': 'X'}")
        (scripts / 'progress_link.py').write_text("LABEL = {'progress.md': 'План', 'missing.md': 'Y'}")
        errors = checker.progress_labels(self.folder)
        self.assertEqual(len(errors), 3)

    def test_reflect_reads_review_codes_and_escalation_but_not_goal_words(self):
        reviews = ['принято с первого ревью (COMMIT)',
                   'исправлено после ревью (FIX_THEN_COMMIT: проверка)',
                   'принято после двух кругов (review-hard ×2: COMMIT)',
                   'переделано (RETURN_TO_EXECUTOR ×2 → COMMIT)', 'возвращено, принято', 'COMMIT']
        rows = ''.join(f'| U{i} | Возвращает оплату | impl-hard{" (эскалация)" if i == 6 else ""} | ✅ готово | {r} |\n'
                       for i, r in enumerate(reviews, 1))
        md = self.md('progress.md', rows)
        with patch.object(measure, 'STORE', self.folder / 'store'):
            self.assertEqual(measure.acceptance([md], '', str(self.folder))[:3], (6, 1, 5))


if __name__ == '__main__':
    unittest.main()
