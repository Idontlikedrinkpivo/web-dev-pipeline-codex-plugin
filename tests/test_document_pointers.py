"""R finite navigation fixtures, not broad claims about runtime behavior."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "dev-pipeline/skills"
CONSUMERS = ("python", "typescript", "react", "fastapi", "fastapi-sqlalchemy",
             "typescript-fastify", "typescript-drizzle-orm", "zod-skill", "vitest",
             "pytest-patterns", "frontend", "clean-architecture-design", "executor-catalog")


def anchor(heading):
    return re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")


class DocumentPointerTests(unittest.TestCase):
    def test_main_rule_anchors_resolve(self):
        for skill in CONSUMERS:
            with self.subTest(skill=skill):
                text = (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
                nav = text.split("## Главные правила\n", 1)[1].split("\n## ", 1)[0]
                links = re.findall(r"\[([^\]]+)\]\(#([^\)]+)\)", nav)
                headings = {anchor(h) for h in re.findall(r"^##+ (.+)$", text, re.M)}
                self.assertGreaterEqual(len(links), 2)
                for label, target in links:
                    self.assertIn(target, headings, label)
                self.assertIn("mandatory", nav)

    def test_obsolete_active_claims_are_removed(self):
        fixtures = {
            "pipeline/references/keep-after-compaction.md": ("exit 2 — hand over now",),
            "pipeline/references/service-version.md": ("folder is read and written in the main tree",),
            "pipeline/references/progress-files.md": ("held back by the plugin's hook (`hooks/watchers.py`)",),
            "work/references/run-hygiene.md": ("plugin's hook (`hooks/watchers.py`) keeps an agent",),
        }
        for path, forbidden in fixtures.items():
            text = (SKILLS / path).read_text(encoding="utf-8")
            for claim in forbidden:
                self.assertNotIn(claim, text, path)


if __name__ == "__main__":
    unittest.main()
