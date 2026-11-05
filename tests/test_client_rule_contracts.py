"""R client policy checks; B scenarios remain unmeasured."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "dev-pipeline/skills"


class ClientRuleContractTests(unittest.TestCase):
    def test_hook_only_core_coverage(self):
        text = (SKILLS / "react/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("every affected detail/list/aggregate", text)
        self.assertIn("list-only invalidation", text)
        text = (SKILLS / "work/references/stack-skills.md").read_text(encoding="utf-8")
        self.assertIn("use*.ts", text)
        self.assertIn("detail/list/aggregate", text)

    def test_lint_api_names_live_in_version_reference(self):
        text = (SKILLS / "react/SKILL.md").read_text(encoding="utf-8")
        table = text.split("## The machine checks", 1)[1].split("## The reviewer checks", 1)[0]
        self.assertNotIn("react-hooks v7", table)
        self.assertNotIn("`static-components`", table)
        text = (SKILLS / "frontend/references/version-checks.md").read_text(encoding="utf-8")
        for token in ("## React lint", "`purity`", "`static-components`", "does not require upgrading"):
            self.assertIn(token, text)

    def test_request_response_compatibility_is_directional(self):
        for path in ("typescript/SKILL.md", "zod-skill/SKILL.md"):
            text = " ".join((SKILLS / path).read_text(encoding="utf-8").split())
            for token in ("accepted request set", "output enum/union", "exhaustive consumers",
                          "schema validators", "compatibility action/version"):
                self.assertIn(token, text, path)
            self.assertNotIn("Additive changes are safe", text)


if __name__ == "__main__":
    unittest.main()
