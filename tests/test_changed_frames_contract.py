"""R routing and stable-ID contracts; not live Figma evidence."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "dev-pipeline/skills"


class ChangedFramesContractTests(unittest.TestCase):
    def test_consumers_link_delta_mode(self):
        for skill in ("ui-design", "screen-spec", "ui-test-cases"):
            text = (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("changed-frames.md", text, skill)
        text = (SKILLS / "ui-design/references/changed-frames.md").read_text(encoding="utf-8")
        for token in ("nodeIds", "added, changed", "unchanged, deleted", "S-n/M-n",
                      "never renumber or reuse", "Deleted/missing", "open question",
                      "affected screen-spec/case list", "Figma tool/login", "NOT_RUN",
                      "Изменённые", "макеты: <frames register path>"):
            self.assertIn(token, text)

    def test_existing_anti_renumber_gate_is_retained(self):
        text = (SKILLS / "ui-design/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("no `S-` or `M-` id was renumbered or reused", text)
        text = (SKILLS / "screen-spec/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("this skill never renumbers", text)


if __name__ == "__main__":
    unittest.main()
