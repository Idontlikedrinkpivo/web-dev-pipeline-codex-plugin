"""R structural contracts only; no agent-compliance claim."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "dev-pipeline/skills"


class WorkStateContractTests(unittest.TestCase):
    def test_work_phase_and_scope_contract(self):
        text = (SKILLS / "work/SKILL.md").read_text(encoding="utf-8")
        for token in ("checkpoint-state.md", "unit", "wave", "low-fix", "final-checks",
                      "whole-review", "review-fix", "plan hash", "full HEAD", "BASE/ranges",
                      "Low batches/findings", "remaining gates", "R01", "R02",
                      "SKIPPED BY USER", "unsent packet", "mandatory checks remain"):
            with self.subTest(token=token):
                self.assertIn(token, text)

    def test_portable_report_and_local_detail_split(self):
        text = (SKILLS / "code-review-full/SKILL.md").read_text(encoding="utf-8")
        inputs = text.split("## Inputs", 1)[1].split("## Resume a review", 1)[0]
        self.assertIn("documentation/plans/<version>/work-run.md", inputs)
        self.assertNotIn("pipeline-work/<version>-run.md", inputs)
        self.assertIn("git-common-dir", inputs)
        self.assertIn("small iteration without a plan", inputs)
        self.assertIn("instead of\ninventing a plan", inputs)
        for path in ("work/references/run-state.md", "work/references/close.md"):
            text = " ".join((SKILLS / path).read_text(encoding="utf-8").split())
            for token in ("checkpoint-state.md", "Low", "remaining gates", "exact next action"):
                self.assertIn(token, text, path)

    def test_behavior_cases_do_not_claim_acceptance(self):
        text = (ROOT / "tests/behavior_cases/work-continuation.md").read_text(encoding="utf-8")
        for token in ("NOT_RUN", "21/21", "R01", "R02", "unknown"):
            self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()
