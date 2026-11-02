"""Readable BRD question views retain one canonical text and unresolved state."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1]/'dev-pipeline/skills/brainstorm/scripts/question_projection.py'
# The release builds this shared script before running the Codex tests.
spec = importlib.util.spec_from_file_location('question_projection', SCRIPT)
projection = importlib.util.module_from_spec(spec)
if SCRIPT.is_file():
    spec.loader.exec_module(projection)

REGISTER = '''# Открытые вопросы
Варианты не согласованы.

<!-- ce-question: OQ-7; class: Отложено; source: discussion -->
## Вопрос 7. Какие данные использовать?

Например, задача выполнена на 50%.

**A. Оценка исполнителя.** Нужна актуальная оценка.

**B. Прогноз.** Нужно согласовать правило.

<!-- ce-question: OQ-9; class: Блокирует старт; source: discussion -->
## Вопрос 9. Кто видит проект?

Ответ пока не выбран.
'''
DOC = '''# Требования
<!-- ce-requirement: R1; open: OQ-7 -->
## Сроки
<!-- ce-question-include: OQ-7; level: 3 -->
<!-- /ce-question-include -->
## Доступ
<!-- ce-question-include: OQ-9; level: 4 -->
<!-- /ce-question-include -->
'''


class QuestionProjectionTests(unittest.TestCase):
    def test_shared_script_is_shipped(self):
        self.assertTrue(SCRIPT.is_file(), str(SCRIPT))

    def test_refresh_keeps_options_and_blocking_status_in_context(self):
        result = projection.project(DOC, REGISTER)
        self.assertIn('### Вопрос 7. Какие данные использовать?', result)
        self.assertIn('#### Вопрос 9. Кто видит проект?', result)
        self.assertIn('class: Блокирует старт', result)
        self.assertIn('class: Отложено', result)
        self.assertIn('**B. Прогноз.** Нужно согласовать правило.', result)
        self.assertIn('<!-- ce-requirement: R1; open: OQ-7 -->', result)
        self.assertLess(result.index('Например'), result.index('## Доступ'))
        self.assertEqual(projection.project(result, REGISTER), result)

    def test_canonical_edit_and_resolution_replace_old_text(self):
        initial = projection.project(DOC, REGISTER)
        changed = REGISTER.replace('Ответ пока не выбран.', 'Согласовано: только руководитель.')
        result = projection.project(initial, changed)
        self.assertNotIn('Ответ пока не выбран.', result)
        self.assertIn('Согласовано: только руководитель.', result)
        self.assertEqual(result.count('## Вопрос'), 2)

    def test_invalid_sources_and_markers_fail_instead_of_leaving_stale_text(self):
        cases = [(DOC, REGISTER.replace('OQ-9', 'OQ-10')),
                 (DOC, REGISTER + '\n' + REGISTER),
                 (DOC + DOC, REGISTER),
                 (DOC.replace('<!-- /ce-question-include -->', '', 1), REGISTER),
                 (DOC.replace('level: 3', 'level: 99'), REGISTER),
                 (DOC.replace('<!-- ce-question-include: OQ-7; level: 3 -->',
                              '<!-- /ce-question-include -->'), REGISTER)]
        for document, register in cases:
            with self.subTest(document=document[:60], register=register[-40:]):
                with self.assertRaises(ValueError):
                    projection.project(document, register)

    def test_cli_check_is_read_only_and_update_preserves_register(self):
        with tempfile.TemporaryDirectory() as td:
            doc = Path(td)/'business-requirements.md'; doc.write_text(DOC)
            register = Path(td)/'open-questions.md'; register.write_text(REGISTER)
            def run(*args):
                return subprocess.run([sys.executable, str(SCRIPT), str(doc), *args],
                                      capture_output=True, text=True)
            self.assertEqual(run('--check').returncode, 1)
            self.assertEqual(doc.read_text(), DOC)
            self.assertEqual(run().returncode, 0)
            self.assertEqual(register.read_text(), REGISTER)
            self.assertEqual(run('--check').returncode, 0)
            before = doc.read_text(); register.write_text('missing question')
            self.assertEqual(run().returncode, 2)
            self.assertEqual(doc.read_text(), before)

    def test_legacy_document_without_projections_does_not_need_register(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/'business-requirements.md'; p.write_text('# Старый документ\n')
            result = subprocess.run([sys.executable, str(SCRIPT), str(p), '--check'],capture_output=True)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(p.read_text(), '# Старый документ\n')


if __name__ == '__main__':
    unittest.main()
