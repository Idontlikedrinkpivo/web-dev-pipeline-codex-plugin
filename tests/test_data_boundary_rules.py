"""R: structural policy checks; these do not measure agent compliance."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "dev-pipeline/skills/work/references/data-boundaries.md"
CASES = ROOT / "tests/behavior_cases/data-boundaries.md"
RULES = {
    "DBND-1": ("cookie", "state-changing", "CSRF", "SameSite"),
    "DBND-2": ("bound parameters", "identifiers", "allowlist", "safe composition"),
    "DBND-3": ("timeout", "cancellation", "operation budget"),
    "DBND-4": ("SQLSTATE", "constraint name", "named", "contract", "409"),
    "DBND-5": ("40001", "40P01", "whole transaction", "idempotency", "side effects"),
    "DBND-6": ("safe retry", "503", "Retry-After", "contract"),
    "DBND-7": ("unexpected", "500", "generic", "private cause"),
}


class DataBoundaryRulesTests(unittest.TestCase):
    def test_stack_consumers_link_applicable_rules(self) -> None:
        consumers = {
            "react/SKILL.md": ("DBND-1", "DBND-3"),
            "frontend/SKILL.md": ("DBND-1", "DBND-3"),
            "fastapi/SKILL.md": ("DBND-1", "DBND-3", "DBND-4", "DBND-5", "DBND-6", "DBND-7"),
            "fastapi/references/jwt-auth.md": ("DBND-1",),
            "typescript-fastify/SKILL.md": ("DBND-1", "DBND-3", "DBND-4", "DBND-5", "DBND-6", "DBND-7"),
            "typescript-fastify/references/auth.md": ("DBND-1",),
            "fastapi-sqlalchemy/SKILL.md": ("DBND-2", "DBND-4", "DBND-5", "DBND-6", "DBND-7"),
            "typescript-drizzle-orm/SKILL.md": ("DBND-2", "DBND-4", "DBND-5", "DBND-6", "DBND-7"),
            "typescript-drizzle-orm/references/repository-adapter.md": ("DBND-2", "DBND-4", "DBND-5", "DBND-6", "DBND-7"),
        }
        for relative, rules in consumers.items():
            with self.subTest(consumer=relative):
                path = ROOT / "dev-pipeline/skills" / relative
                text = path.read_text(encoding="utf-8")
                section = text.split("## Shared data boundaries", 1)[1]
                for rule in rules:
                    self.assertIn(rule, section)
                links = re.findall(r"\]\(([^)]+data-boundaries\.md)\)", section)
                self.assertTrue(links)
                for link in links:
                    self.assertEqual((path.parent / link).resolve(), POLICY.resolve())
                if "DBND-4" in rules:
                    self.assertIn("mapping/retry table", section)
                self.assertNotIn("attempts = 3", text)
                self.assertNotIn("three, with a short random", text)

    def policy(self) -> str:
        self.assertTrue(POLICY.is_file(), "missing shared data boundary rules")
        return POLICY.read_text(encoding="utf-8")

    def test_unique_rules_have_executor_and_reviewer_checks(self) -> None:
        rows = re.findall(r"^\| (DBND-\d+) \| (.+) \| (.+) \| (.+) \|$",
                          self.policy(), re.MULTILINE)
        self.assertEqual(len(rows), len(RULES))
        self.assertEqual({row[0] for row in rows}, set(RULES))
        for rule, contract, executor, reviewer in rows:
            with self.subTest(rule=rule):
                for token in RULES[rule]:
                    self.assertIn(token, contract)
                self.assertGreater(len(executor.split()), 5)
                self.assertGreater(len(reviewer.split()), 5)

    def test_error_mapping_is_named_and_conditional(self) -> None:
        policy = self.policy()
        mappings = {
            "DBND-4": ("named business error", "contract status", "never blanket SQLSTATE => 409"),
            "DBND-5": ("propagate unchanged", "fresh session", "no automatic retry when unsafe"),
            "DBND-6": ("safe retry exhausted", "contract 503 + Retry-After"),
            "DBND-7": ("unexpected / unclassified", "generic contract 500", "private cause in logs"),
        }
        for rule, tokens in mappings.items():
            with self.subTest(rule=rule):
                row = next((line for line in policy.splitlines()
                            if line.startswith(f"| {rule} mapping |")), "")
                for token in tokens:
                    self.assertIn(token, row)

    def test_retry_safety_and_no_invented_budgets(self) -> None:
        policy = self.policy()
        for token in ("load → decide → save", "never one statement", "repository never loops",
                      "external side effects", "idempotency proof", "attempts and duration",
                      "Do not invent", "unsafe retry", "contract gap"):
            with self.subTest(token=token):
                self.assertIn(token, policy)
        self.assertNotRegex(policy, r"(?i)\b(?:three|3) (?:attempts|retries)\b")
        self.assertNotRegex(policy, r"\b\d+\s*(?:ms|seconds|milliseconds)\b")

    def test_sql_examples_bind_values_and_allowlist_identifiers(self) -> None:
        samples = re.findall(r"```python\n(.*?)```", self.policy(), re.DOTALL)
        self.assertEqual(len(samples), 1)
        sample = samples[0]
        self.assertIn("WHERE email = %s", sample)
        self.assertIn("(email,)", sample)
        self.assertIn('columns = {"created": "created_at", "name": "display_name"}', sample)
        self.assertIn("columns[sort_key]", sample)
        self.assertNotRegex(sample, r"(?:f[\"'].*\{email\}|%\s*email|\+\s*email)")
        self.assertNotIn("{sort_key}", sample)

    def test_behavior_cases_are_separate_and_unmeasured(self) -> None:
        self.assertTrue(CASES.is_file(), "missing separate B cases")
        cases = CASES.read_text(encoding="utf-8")
        for rule in RULES:
            with self.subTest(rule=rule):
                self.assertIn(rule, cases)
        for token in ("Not run", "executor", "reviewer", "external side effect", "40001", "40P01"):
            self.assertIn(token, cases)
        self.assertIn("presence, not real behavior", self.policy())


if __name__ == "__main__":
    unittest.main()
