"""Plan economy is advice; unusable plans and unsafe waves remain errors."""
from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dev-pipeline/skills/plan/scripts/plan_lint.py"
WRITER = ROOT / "dev-pipeline/skills/plan/references/writer.md"


def unit(number: int, *, files: str = "`src/a.py`", goal: str = "Apply the settled naming rule",
         pattern: str = "`src/pattern.py`", parallel: str = "no", deps: str = "—",
         separate: str = "", executor: str = "impl-lite", grade: str = "Low") -> str:
    return f"""### U{number}. Apply naming

| | |
|---|---|
| **Документы** | settled naming rule |
| **Файлы** | {files} |
| **Образец** | {pattern} |
| **Зависит от** | {deps} |
| **Параллельно** | {parallel} |
| **Сложность** | {grade} |
| **Почему** | rule 5 — determined pattern |
| **Исполнитель** | {executor} |
| **Вложенный** | — |

**Цель** — {goal}

**Подход** — Follow the cited rule.

**Тестовые сценарии** — Given the old name, apply the rule, expect the new name.

**Проверка** — The naming assertion passes.

{separate}

"""


class PlanEconomyTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name)
        (self.repo / "src").mkdir()
        (self.repo / "documentation").mkdir()
        (self.repo / "src/pattern.py").write_text("# precedent\n", encoding="utf-8")

    def lint(self, text: str) -> subprocess.CompletedProcess[str]:
        plan = self.repo / "plan.md"
        plan.write_text(text, encoding="utf-8")
        return subprocess.run([sys.executable, str(SCRIPT), str(plan), "--repo", str(self.repo)],
                              cwd=self.repo, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                              text=True, capture_output=True, check=False)

    def test_empty_plan_is_an_error(self) -> None:
        result = self.lint("# Plan\nNo work units yet.\n")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("✗", result.stdout)
        self.assertIn("U", result.stdout)

    def test_related_micro_units_warn_but_pass(self) -> None:
        result = self.lint(unit(1) + unit(2, files="`src/b.py`"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r"⚠.*U1.*U2.*micro-slicing")
        self.assertNotIn("✗", result.stdout)

    def test_independent_small_fixes_do_not_warn(self) -> None:
        result = self.lint(unit(1) + unit(2, files="`src/b.py`", goal="Correct a separate timeout"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("⚠", result.stdout)

    def test_justified_serial_broad_overlap_is_accepted(self) -> None:
        result = self.lint(unit(1, files="`src/`", grade="Mid", executor="impl-medium") +
                           unit(2, files="`src/a.py`", deps="U1", goal="Integrate U1's public contract",
                                separate="**Отдельный коммит** — U1 establishes the independently green API."))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("✗", result.stdout)

    def test_explicit_green_commit_reason_resolves_micro_advice(self) -> None:
        reason = "**Отдельный коммит** — Independently green delivery to a separate consumer."
        result = self.lint(unit(1, separate=reason) + unit(2, files="`src/b.py`", separate=reason))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("micro-slicing", result.stdout)

    def test_disjoint_parallel_units_pass(self) -> None:
        result = self.lint(unit(1, parallel="yes") +
                           unit(2, files="`src/b.py`", parallel="yes", goal="Fix a separate rule"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("✗", result.stdout)

    def test_concurrent_overlap_is_an_error(self) -> None:
        for files in ("`src/a.py`", "`src/`", "`src/*.py`"):
            with self.subTest(files=files):
                result = self.lint(unit(1, parallel="yes", files=files) + unit(2, parallel="yes"))
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("✗ U1 и U2", result.stdout)

    def test_dependency_serializes_yes_pair(self) -> None:
        result = self.lint(unit(1, parallel="yes") + unit(2, parallel="yes", deps="U1"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("✗", result.stdout)

    def test_cycle_and_unknown_dependency_remain_errors(self) -> None:
        for text in (unit(1, deps="U2") + unit(2, deps="U1"), unit(1, deps="U99")):
            with self.subTest(text=text):
                result = self.lint(text)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("✗", result.stdout)

    def test_illegal_executor_and_grade_remain_errors(self) -> None:
        for text in (unit(1, executor="impl-critical"), unit(1, grade="Tiny")):
            with self.subTest(text=text):
                result = self.lint(text)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_large_measured_input_warns_without_spend_claim(self) -> None:
        (self.repo / "src/a.py").write_bytes(b"a" * (160 * 1024))
        result = self.lint(unit(1))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r"⚠.*U1.*input-footprint")
        expected_bytes = 160 * 1024 + (self.repo / "src/pattern.py").stat().st_size
        self.assertIn(f"файлы {expected_bytes} bytes", result.stdout)
        self.assertIn("bytes", result.stdout)
        self.assertNotRegex(result.stdout.lower(), r"\$|\d+\s*(?:tokens?|usd)|стоимость|spend")

    def test_large_cited_input_counts_even_when_owned_file_is_small(self) -> None:
        (self.repo / "src/pattern.py").write_bytes(b"a" * (160 * 1024))
        result = self.lint(unit(1))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("input-footprint", result.stdout)

    def test_duplicate_citations_do_not_inflate_footprint(self) -> None:
        (self.repo / "src/a.py").write_bytes(b"a" * (40 * 1024))
        text = unit(1, pattern="`src/a.py`").replace("settled naming rule", "`src/a.py`")
        result = self.lint(text)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("input-footprint", result.stdout)

    def test_directory_and_glob_footprint_deduplicates_files(self) -> None:
        (self.repo / "src/a.py").write_bytes(b"a" * (160 * 1024))
        result = self.lint(unit(1, files="`src/`; `src/*.py`"))
        expected_bytes = 160 * 1024 + (self.repo / "src/pattern.py").stat().st_size
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"файлы {expected_bytes} bytes", result.stdout)

    def test_plain_code_reference_contributes_to_input(self) -> None:
        (self.repo / "src/large.py").write_bytes(b"a" * (160 * 1024))
        result = self.lint(unit(1).replace("settled naming rule", "code:src/large.py"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("input-footprint", result.stdout)

    def test_missing_future_files_are_not_invented(self) -> None:
        result = self.lint(unit(1, files="`src/future.py`"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("input-footprint", result.stdout)

    def test_unmeasurable_input_is_advice_and_preserves_hard_errors(self) -> None:
        # An invalid recursive glob must not make the advisory scan crash.
        for executor, expected_code in (("impl-lite", 0), ("impl-critical", 1)):
            with self.subTest(executor=executor):
                result = self.lint(unit(1, files="`src/**oops.py`", executor=executor))
                self.assertEqual(result.returncode, expected_code, result.stdout + result.stderr)
                self.assertRegex(result.stdout, r"⚠.*input-footprint.*не измерен")
                self.assertNotIn("Traceback", result.stderr)

    def test_writer_toc_links_resolve_to_every_existing_section(self) -> None:
        text = WRITER.read_text(encoding="utf-8")
        toc = text.split("<!-- TOC -->", 1)
        self.assertEqual(len(toc), 2, "writer needs a bounded table of contents")
        toc_body, body = toc[1].split("<!-- /TOC -->", 1)
        links = re.findall(r"\]\(#([^)]*)\)", toc_body)
        # Template headings inside fenced examples are not document sections.
        prose = re.sub(r"^```[^\n]*\n.*?^```\s*$", "", body, flags=re.M | re.S)
        headings = re.findall(r"^#{2,3} (.+)$", prose, re.M)
        slugs = {re.sub(r"[^\w\s-]", "", h.lower()).replace(" ", "-") for h in headings}
        self.assertTrue(links)
        self.assertEqual(set(links), slugs)


if __name__ == "__main__":
    unittest.main()
