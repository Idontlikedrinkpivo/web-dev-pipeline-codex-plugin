"""Structural guards for bounded packets and paired review evidence, not an experiment."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / "dev-pipeline/skills"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class PacketPolicyTests(unittest.TestCase):
    def test_packet_selects_sections_instead_of_unconditional_full_read(self) -> None:
        packet = read("executor-catalog/references/worker-prompt.md")
        self.assertNotIn("read each file in full", packet)
        self.assertIn("main rules + named sections", packet)
        self.assertIn("mandatory conditional auth/security/reviewer anchors", packet)

    def test_routing_fixtures_retain_required_coverage(self) -> None:
        matrix = read("work/references/stack-skills.md")
        fixtures = {
            "Hook-only (`use*.ts`)": ("react", "The machine checks", "The reviewer checks"),
            "Auth by files or goal": ("references/auth.md", "references/jwt-auth.md", "Auth and configuration"),
            "Query/repository": ("Rules", "Session and unit of work", "Driver errors and install"),
            "Reviewer": ("The reviewer checks", "mandatory"),
        }
        for label, anchors in fixtures.items():
            with self.subTest(route=label):
                row = next((line for line in matrix.splitlines() if line.startswith(f"| {label} |")), "")
                self.assertTrue(row, f"Missing routing fixture: {label}")
                for anchor in anchors:
                    self.assertIn(anchor, row)
        self.assertIn("Do not split a short file artificially", matrix)

    def test_experiment_requires_pairs_and_quality_gate(self) -> None:
        policy = read("executor-catalog/references/model-economics.md")
        for required in ("same-task/same-diff", "material misses", "returns/re-review",
                         "mandatory high-risk", "at least 5 pairs", "10%", "rollback",
                         "sample size", "uncertainty", "null", "U13"):
            with self.subTest(required=required):
                self.assertIn(required, policy)
        self.assertIn("Do not run this experiment as part of U25", policy)
        self.assertIn("models.json and agents/*.toml remain unchanged", policy)

    def test_comparison_preserves_nullable_measurements(self) -> None:
        comparing = read("reflect/references/comparing.md")
        for required in ("same-task/same-diff", "U13", "null", "known units", "10%",
                         "mandatory high-risk", "rollback", "uncertainty"):
            with self.subTest(required=required):
                self.assertIn(required, comparing)


if __name__ == "__main__":
    unittest.main()
