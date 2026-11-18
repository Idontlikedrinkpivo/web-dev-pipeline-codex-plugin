"""The native compaction setting belongs only to the selected project."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dev-pipeline/skills/pipeline/scripts"))
from project_compaction import KEY, iteration_offer, project_limit


class ProjectCompactionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        subprocess.run(["git", "init", "-q", self.root], check=True)
        self.project = self.root / "nested project"
        self.project.mkdir()
        self.config = self.project / ".codex/config.toml"

    def test_inspect_then_enable_only_in_selected_folder(self):
        self.assertIsNone(project_limit(self.project))
        self.assertFalse(self.config.parent.exists())
        self.assertEqual(project_limit(self.project, 300000), 300000)
        self.assertEqual(tomllib.loads(self.config.read_text()), {KEY: 300000})
        self.assertFalse((self.root / ".codex").exists())

    def test_nested_project_inherits_threshold_but_ignores_a_sibling(self):
        sibling = self.root / "sibling"
        sibling.mkdir()
        project_limit(sibling, 42000)
        self.assertIn("300 000", iteration_offer(self.project))
        project_limit(self.root, 120000)
        self.assertIsNone(iteration_offer(self.project))

    def open_iteration(self, version, *flags):
        script = ROOT / "dev-pipeline/skills/pipeline/scripts/open_iteration.py"
        return subprocess.run([sys.executable, str(script), version, str(self.root), *flags],
                              check=True, text=True, capture_output=True).stdout

    def prepare_main(self):
        for args in (("symbolic-ref", "HEAD", "refs/heads/main"),
                     ("config", "user.name", "Test"), ("config", "user.email", "test@example.org"),
                     ("commit", "--allow-empty", "-qm", "initial")):
            subprocess.run(["git", "-C", str(self.root), *args], check=True)

    def test_normal_open_offers_once_per_new_iteration_until_enabled(self):
        self.prepare_main()
        self.assertIn("автосжатие", self.open_iteration("1.0.0"))
        self.assertNotIn("автосжатие", self.open_iteration("1.0.0"))
        self.assertIn("автосжатие", self.open_iteration("1.0.1", "--allow-open", "--allow-unmerged"))
        self.assertFalse((self.root / ".codex/config.toml").exists())
        project_limit(self.root, 150000)
        self.assertNotIn("автосжатие", self.open_iteration("1.0.2", "--allow-open", "--allow-unmerged"))

    def test_small_open_uses_same_rule_and_reuse_is_quiet(self):
        self.prepare_main()
        self.assertIn("автосжатие", self.open_iteration("1.0.0", "--small"))
        self.assertNotIn("автосжатие", self.open_iteration("1.0.0", "--small"))

    def test_keep_tables_comments_and_existing_choice(self):
        self.config.parent.mkdir()
        original = b'# local\r\n[plugins."a@b"]\r\nenabled = true\r\n'
        self.config.write_bytes(original)
        project_limit(self.project, 18000)
        saved = self.config.read_bytes()
        self.assertTrue(saved.endswith(original))
        self.assertEqual(tomllib.loads(saved.decode())["plugins"]["a@b"], {"enabled": True})
        self.assertEqual(project_limit(self.project, 18000), 18000)
        with self.assertRaisesRegex(ValueError, "already sets"):
            project_limit(self.project, 300000)
        self.assertEqual(self.config.read_bytes(), saved)

    def test_fail_closed_on_invalid_config_competing_write_and_global_alias(self):
        self.config.parent.mkdir()
        self.config.write_text("[invalid")
        with self.assertRaises(tomllib.TOMLDecodeError):
            project_limit(self.project, 300000)
        self.assertEqual(self.config.read_text(), "[invalid")
        self.config.write_text("")
        self.config.with_suffix(".toml.lock").write_text("writer")
        with self.assertRaises(FileExistsError):
            project_limit(self.project, 300000)
        with patch.dict(os.environ, CODEX_HOME=str(self.config.parent)):
            with self.assertRaises(ValueError):
                project_limit(self.project, 300000)
        with self.assertRaises(ValueError):
            project_limit(self.project, 0)
        self.assertEqual(self.config.read_text(), "")

    def test_reject_symlink_to_other_config(self):
        other = self.root / "other.toml"
        other.write_text("# original")
        self.config.parent.mkdir()
        self.config.symlink_to(other)
        with self.assertRaises(ValueError):
            project_limit(self.project, 18000)
        self.assertEqual(other.read_text(), "# original")
