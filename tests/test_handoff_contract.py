"""R prose contracts; actual human handoff remains separate B evidence."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "dev-pipeline/skills"


class HandoffContractTests(unittest.TestCase):
    def test_pause_uses_verified_checkpoint_not_destructive_recipe(self):
        text = (SKILLS / "pipeline/references/pause-and-resume.md").read_text(encoding="utf-8")
        for forbidden in ("git reset -q", "git add --intent-to-add", "git apply", "git diff --binary >"):
            self.assertNotIn(forbidden, text)
        for token in ("checkpoint-state.md", "local-only", "portable", "remote",
                      "stopped", "Unknown", "general request to code", "Main/merge/tag/release"):
            self.assertIn(token, text)

    def test_selected_stages_are_not_all_proposals(self):
        text = (SKILLS / "continue/SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("open **every**", text)
        for token in ("explicitly selected", "authorize", "never expand", "regardless"):
            self.assertIn(token, text)
        text = (SKILLS / "pipeline/references/parent-session.md").read_text(encoding="utf-8")
        for token in ("proposed stages only", "empty revokes", "historical facts",
                      "Canonical stage numbers/order", "сразу запиши"):
            self.assertIn(token, text)

    def test_current_checkout_and_cleanup_scope(self):
        text = (SKILLS / "pipeline/references/service-version.md").read_text(encoding="utf-8")
        self.assertIn("plans are read and written in that checkout", text)
        self.assertNotIn("folder is read and written in the main tree", text)
        text = (SKILLS / "pipeline/references/closing-cleanup.md").read_text(encoding="utf-8")
        self.assertIn("never the shared common-dir", text)
        self.assertIn("verified portability", text)


if __name__ == "__main__":
    unittest.main()
