"""Structural contracts for architecture routing; these do not exercise a writer."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / "dev-pipeline/skills"
ARCHITECTURE = ROOT / "clean-architecture-design"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class ArchitecturePolicyTests(unittest.TestCase):
    def test_increment_scope_agrees_at_both_entrypoints(self) -> None:
        for relative in (
            "clean-architecture-design/SKILL.md",
            "executor-catalog/references/design-writer-prompt.md",
        ):
            with self.subTest(path=relative):
                text = read(relative)
                self.assertIn("affected areas, types and operations", text)
                self.assertIn("referenced shared foundation/dependencies", text)
                self.assertIn("real dependency conflict", text)
                self.assertIn("explain the expansion", text)
                self.assertNotIn("every existing one and its diagrams", text)
                self.assertNotIn("for architecture every architecture document", text)

    def test_increment_reference_bounds_reads_before_mode_selection(self) -> None:
        text = (ARCHITECTURE / "references/increment.md").read_text(encoding="utf-8")
        self.assertIn("## Reading scope", text)
        self.assertLess(text.index("## Reading scope"), text.index("## Which modes run"))
        self.assertIn("do not read unrelated areas in advance", text)
        self.assertIn("referenced shared foundation/dependencies", text)
        self.assertIn("real dependency conflict", text)
        self.assertNotIn("Promote the level\n  only when", text)

    def test_explicit_level_choice_is_carried_to_the_writer(self) -> None:
        for relative in (
            "clean-architecture-design/SKILL.md",
            "executor-catalog/references/design-writer-prompt.md",
        ):
            with self.subTest(path=relative):
                text = read(relative)
                self.assertIn("explicit lighter level", text)
                self.assertIn("do not ask again", text)
                self.assertIn("real requirement conflict", text)

    def test_levels_keep_names_and_offer_a_durable_lighter_choice(self) -> None:
        text = (ARCHITECTURE / "references/architecture-level.md").read_text(encoding="utf-8")
        for level in ("Framework-first + one boundary", "Modest", "Full"):
            self.assertIn(f"**{level}**", text)
        self.assertIn("Modest is the CRUD recommendation", text)
        self.assertIn("explicit lighter level", text)
        self.assertIn("durable", text)
        self.assertIn("tradeoffs", text)
        self.assertIn("real requirement conflict", text)
        self.assertNotIn("Modest is the floor", text)
        self.assertNotIn("Never by your own judgment, and never for plain CRUD", text)

    def test_boundaries_follow_the_chosen_level(self) -> None:
        text = (ARCHITECTURE / "references/machine-checkable-boundaries.md").read_text(encoding="utf-8")
        self.assertIn("chosen level", text)
        self.assertIn("Do not impose the Modest or Full folder tree", text)
        self.assertIn("machine-checkable", text)

    def test_missing_renderer_keeps_honest_source_only_output(self) -> None:
        packet = read("executor-catalog/references/design-writer-prompt.md")
        self.assertIn("svg: missing", packet)
        self.assertIn("keep the `.d2` / `.puml` source", packet)
        self.assertIn("Do not install a renderer or fabricate an SVG", packet)


if __name__ == "__main__":
    unittest.main()
