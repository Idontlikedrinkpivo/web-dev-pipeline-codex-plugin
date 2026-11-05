"""Recipient debt survives document boundaries and legacy classifications."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'dev-pipeline/skills/doc-versioning/scripts'
sys.path.insert(0, str(SCRIPTS))
import open_questions as oq
import doc_check


class QuestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write('requirements/srs', [('Стоп?', 'Блокирует старт'),
                   ('Новая архитектура?', 'Решить при: архитектура'),
                   ('Старая архитектура?', oq.LEGACY), ('Уже ответили?', 'Решено: srs.md §3')])
        self.write('db', [('Статус?', 'Решить при: API'), ('Потом?', 'Отложено')])

    def write(self, folder, rows):
        p = self.root / 'documentation' / folder / 'open-questions.md'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('# Открытые вопросы\n\n| Вопрос | Класс |\n|---|---|\n' +
                     ''.join(f'| {q} | {c} |\n' for q, c in rows))
        return p

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / 'open_questions.py'), str(self.root), *args],
                              capture_output=True, text=True)

    def test_three_modes_and_unknown_stage(self):
        result = self.cli('--for', 'архитектура')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(result.stdout.index('Блокирует старт:'), result.stdout.index('архитектура:'))
        self.assertIn('Старая архитектура?', result.stdout)
        self.assertIn('documentation/requirements/srs/open-questions.md\tСтоп?', result.stdout)
        self.assertTrue(result.stdout.endswith('Всего открытых вопросов: 3\n'))
        pending = self.cli('--pending').stdout
        self.assertIn('архитектура: 2', pending)
        self.assertIn('API: 1', pending)
        self.assertIn('Отложено: 1', pending)
        all_rows = self.cli().stdout
        self.assertNotIn('Уже ответили?', all_rows)
        self.assertTrue(all_rows.endswith('Всего открытых вопросов: 5\n'))
        self.assertEqual(self.cli('--for', 'кухня').returncode, 2)

    def test_iteration_included_generated_site_excluded_and_classes_strict(self):
        self.write('plans/1.0.0', [('План?', 'Решить при: план')])
        self.write('_web-docs/copy', [('Копия?', 'Решить при: API')])
        self.assertEqual(len(oq.scan(self.root)), 7)
        out = []
        doc_check.check_questions(self.root, out)
        self.assertEqual(out, [])
        self.write('plans/1.0.0', [('Неизвестно?', 'Решить при: кухня'), ('Пусто?', '')])
        doc_check.check_questions(self.root, out)
        self.assertEqual(len(out), 2)
        self.assertIn('эксплуатация', out[0])
        self.assertIn('кухня', out[0])
        self.assertFalse(oq.valid_class('Решено: '))
        self.assertFalse(oq.valid_class('Отложено неверный хвост'))

    def test_where_points_precede_their_stage(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            points = doc_check.w.question_points(self.root, '1.0.0', ['этап 5 не закрыт: архитектура'])
        self.assertIn('Открытые вопросы по адресатам:', output.getvalue())
        self.assertIn('ответить до следующего этапа', points[0])
        self.assertLess(points.index('вопросы для этапа «архитектура»: 2 — решить на нём'),
                        points.index('этап 5 не закрыт: архитектура'))

    def test_customer_markers_and_escaped_pipes(self):
        p = self.write('requirements/business-requirements', [])
        p.write_text('<!-- ce-question: OQ-1; class: Решить при: API; source: chat -->\n## Как ответить?\n')
        rows = oq.read_file(self.root, p)
        self.assertEqual(rows[0].recipient, 'API')
        self.assertIn('Как ответить?', rows[0].text)
        self.write('plans/1.0.0', [(r'A \| B?', 'Решить при: план')])
        self.assertEqual(oq.groups(oq.scan(self.root))['план'][0].text, r'A \| B?')

    def test_question_change_invalidates_consistency_evidence(self):
        checked = doc_check.w.dc_checked
        report = self.root / 'report.md'
        report.write_text(checked.block(checked.doc_set(self.root)))
        self.assertEqual(checked.diff(self.root, report), [])
        self.write('db', [('Другой ответ?', 'Решить при: API')])
        self.assertIn(('changed', 'documentation/db/open-questions.md'), checked.diff(self.root, report))


if __name__ == '__main__':
    unittest.main()
