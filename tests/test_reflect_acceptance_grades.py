"""Acceptance grades survive cleanup and do not confuse escalation with difficulty."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('grade_measure', ROOT / 'dev-pipeline/skills/reflect/scripts/measure.py')
measure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure)


class AcceptanceGradesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'
        self.progress = self.root / 'documentation/plans/1.0.0/progress.md'
        self.progress.parent.mkdir(parents=True)
        self.store = Path(self.temp.name) / 'outside-project/.acceptance'
        self.saved = self.store / 'project/1.0.0.txt'
        self.patcher = patch.object(measure, 'STORE', self.store)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def write(self, rows):
        self.progress.write_text('| U | Цель | Исполнитель | Статус | Ревью |\n|---|---|---|---|---|\n' +
            ''.join(f'| U{i} | Возвращает оплату → ✅ | {role} | {status} | {review} |\n'
                    for i, (role, status, review) in enumerate(rows, 1)))

    def fixture(self):
        self.write([
            ('impl-lite', '✅ готово', 'COMMIT'),
            ('impl-lite', '✅ готово', 'FIX_THEN_COMMIT'),
            ('impl-lite', '✅ готово', 'исправлено после ревью (FIX_THEN_COMMIT)'),
            ('impl-medium', '✅ готово', 'COMMIT'),
            ('impl-hard (эскалация → impl-critical)', '✅ готово', 'RETURN_TO_EXECUTOR ×2 → COMMIT'),
            ('impl-ui', '✅ готово', 'COMMIT'),
            ('mechanical-worker', '⏳ ждёт', 'COMMIT')])

    def read(self):
        grades = {}
        result = measure.acceptance([self.progress], '', str(self.root), by_grade=grades)
        return result, grades

    def test_example_and_cache_round_trip(self):
        self.fixture()
        result, grades = self.read()
        self.assertEqual(result[:3], (6, 3, 3))
        self.assertEqual(grades, {
            'Low — простая': {'accepted': 3, 'first': 1, 'fixed': 2, 'redone': 0},
            'Mid — средняя': {'accepted': 1, 'first': 1, 'fixed': 0, 'redone': 0},
            'High — сложная': {'accepted': 1, 'first': 0, 'fixed': 0, 'redone': 1},
            'UI — экран': {'accepted': 1, 'first': 1, 'fixed': 0, 'redone': 0}})
        self.assertEqual(self.saved.read_text().splitlines()[0], '6 3 3')
        self.assertIn('Low — простая 3 1 2 0', self.saved.read_text())
        self.progress.unlink()
        self.assertEqual(self.read(), (result, grades))

    def test_old_single_line_copy_remains_valid_without_invented_grades(self):
        self.saved.parent.mkdir(parents=True)
        self.saved.write_text('7 5 2\n')
        result, grades = self.read()
        self.assertEqual(result[:3], (7, 5, 2))
        self.assertEqual(grades, {})

    def test_all_grades_and_executor_escalation_do_not_change_review_outcome(self):
        self.write([(role, '✅ готово', 'COMMIT') for role in (
            'impl-ui', 'impl-hard (эскалация → impl-critical)', 'impl-medium',
            'impl-lite', 'mechanical-worker', 'impl-critical', 'unknown-worker')])
        result, grades = self.read()
        self.assertEqual(result[:3], (7, 7, 0))
        self.assertEqual(grades['High — сложная']['first'], 1)
        self.assertEqual(grades['не указана']['accepted'], 2)

    def test_review_precedence_and_multi_digit_rounds(self):
        reviews = ['COMMIT', 'FIX_THEN_COMMIT', 'исправлено после ревью',
                   'RETURN_TO_EXECUTOR → FIX_THEN_COMMIT', 'COMMIT ×10', 'COMMIT ×20',
                   'возвращено, COMMIT', 'эскалация, COMMIT', 'переделано, COMMIT', 'COMMIT ×1']
        self.write([('impl-medium', '✅ готово', review) for review in reviews])
        result, grades = self.read()
        self.assertEqual(result[:3], (10, 2, 8))
        self.assertEqual(grades['Mid — средняя'], {'accepted': 10, 'first': 2, 'fixed': 2, 'redone': 6})

    def report(self):
        out = self.root / 'report.json'
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            measure.report(['--progress', str(self.progress), '--json', str(out)], str(self.root),
                           None, measure.Agent(measure.SESSION, measure.SESSION), [], 0, [])
        return stdout.getvalue(), json.loads(out.read_text())

    def test_markdown_json_and_grade_warning_survive_cleanup(self):
        self.fixture()
        text, data = self.report()
        self.assertIn('| Low — простая | 3 | 1 | 2 | 0 | 33% |', text)
        self.assertIn('задачи сложности Low — простая: с первого ревью 33% (1 из 3)', text)
        self.assertNotIn('задачи сложности High — сложная:', text)  # only one task
        self.assertLess(text.index('| Mid — средняя'), text.index('| High — сложная'))
        self.assertEqual((data['accepted'], data['first_review'], data['sent_back']), (6, 3, 3))
        self.assertEqual(data['by_grade']['Low — простая']['fixed'], 2)
        self.progress.unlink()
        restored_text, restored_data = self.report()
        self.assertEqual(restored_text, text)
        self.assertEqual(restored_data['by_grade'], data['by_grade'])

    def test_several_versions_sum_without_cumulative_cache_counts(self):
        self.fixture()
        second = self.root / 'documentation/plans/1.0.1/progress.md'
        second.parent.mkdir()
        second.write_text('| U1 | X | impl-lite | ✅ готово | COMMIT |\n')
        grades = {}
        result = measure.acceptance([self.progress, second], '', str(self.root), by_grade=grades)
        self.assertEqual(result[:3], (7, 4, 3))
        self.assertEqual(grades['Low — простая']['accepted'], 4)
        self.assertEqual((self.store / 'project/1.0.1.txt').read_text().splitlines()[0], '1 1 0')
        self.progress.unlink()
        second.unlink()
        cached = {}
        self.assertEqual(measure.acceptance([self.progress, second], '', str(self.root), by_grade=cached), result)
        self.assertEqual(cached, grades)

    def test_old_cache_has_no_fabricated_table_or_grade_json(self):
        self.saved.parent.mkdir(parents=True)
        self.saved.write_text('7 5 2\n')
        text, data = self.report()
        self.assertIn('Задач принято: 7', text)
        self.assertNotIn('**По сложности задач**', text)
        self.assertEqual(data['by_grade'], {})

    def test_git_fallback_keeps_totals_without_guessing_grades(self):
        with patch('subprocess.run') as git:
            git.return_value.stdout = 'Plan-Unit: 1.0/U1\nPlan-Unit: 1.0/U2\nPlan-Unit: 1.0/U2\n'
            grades = {}
            result = measure.acceptance([], 'base..HEAD', str(self.root), by_grade=grades)
        self.assertEqual(result[:3], (2, 1, 1))
        self.assertTrue(result[3].startswith('git '))
        self.assertEqual(grades, {})


if __name__ == '__main__':
    unittest.main()
