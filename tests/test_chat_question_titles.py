"""Chat examples are copied by the skills; their progress counters must match the shared format."""
from pathlib import Path
import re
import unittest


SKILLS = Path(__file__).resolve().parents[1] / "dev-pipeline/skills"


class ChatQuestionTitleTests(unittest.TestCase):
    def test_chat_choice_examples_include_position_and_total(self):
        checked = set()
        for path in SKILLS.rglob("*.md"):
            for block in re.findall(r"^[ \t]*```(?:text)?[ \t]*\n(.*?)^[ \t]*```", path.read_text(), re.M | re.S):
                lines = block.strip().splitlines()
                if not (lines and lines[0].lstrip().startswith("**") and re.search(r"^\s*A\.", block, re.M)):
                    continue
                with self.subTest(file=str(path), title=lines[0]):
                    self.assertRegex(lines[0].strip(), r"^\*\*Вопрос (?:[1-9]\d* из [1-9]\d*|N из [XM])\. ")
                checked.add(path.relative_to(SKILLS).parts[0])
        self.assertTrue({"pipeline", "brainstorm", "grill-me"} <= checked)
