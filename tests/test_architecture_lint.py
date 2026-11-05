"""Finite terminology rules respect Markdown applicability and source bytes."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'dev-pipeline/skills/clean-architecture-design/scripts/architecture_lint.py'


class ArchitectureLintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'foundation.md'

    def lint(self, text):
        self.path.write_text(text, encoding='utf-8')
        before = self.path.read_bytes()
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.path), '--json'],
                                capture_output=True, text=True)
        self.assertEqual(before, self.path.read_bytes())
        return result.returncode, json.loads(result.stdout)

    def test_banned_active_heading_reports_precise_location(self):
        code, issues = self.lint('# Архитектура\n\n## Решение о стеке\n')
        self.assertEqual(code, 1)
        self.assertEqual((issues[0]['line'], issues[0]['rule']), (3, 'ARCH-H001'))

    def test_prescribed_headings_and_identifiers_are_allowed(self):
        code, issues = self.lint('# Архитектура\n## Описание системы\n## Журнал изменений\n'
                                 '| Версия | Изменение |\n## 1. Состав системы\n'
                                 '## 2. Модули и функциональные области\n`aggregate.py`\n')
        self.assertEqual((code, issues), (0, []))

    def test_wrapping_in_fence_quote_or_history_changes_only_applicability(self):
        bad = '## Сокращения\nагрегат = сущность\n'
        self.assertEqual(self.lint(bad)[0], 1)
        for wrapped in ('```markdown\n' + bad + '```\n',
                        '~~~\n' + bad + '~~~\n',
                        '> ## Сокращения\n> агрегат = сущность\n',
                        '## История\n### Сокращения\nагрегат = сущность\n## 1. Состав системы\n'):
            self.assertEqual(self.lint(wrapped), (0, []))

    def test_ambiguous_prose_requires_manual_review(self):
        code, issues = self.lint('Термин агрегат использован в старой переписке.\n')
        self.assertEqual(code, 0)
        self.assertEqual((issues[0]['rule'], issues[0]['severity']), ('ARCH-M001', 'warning'))

    def test_equation_and_foundation_duplicate_are_definite(self):
        code, issues = self.lint('## Данные\nАгрегат = сущность\n')
        self.assertEqual(code, 1)
        self.assertEqual({i['rule'] for i in issues}, {'ARCH-H002', 'ARCH-T001'})

    def test_unclosed_fence_and_unreadable_file_have_explicit_input_diagnostics(self):
        code, issues = self.lint('```python\n## Сокращения\n')
        self.assertEqual((code, issues[0]['rule']), (2, 'ARCH-INPUT'))
        self.path.unlink()
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.path), '--json'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)[0]['rule'], 'ARCH-INPUT')


if __name__ == '__main__':
    unittest.main()
