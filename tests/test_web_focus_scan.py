"""The UI scan must not certify shadow-only focus as accessible in forced colours."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = (Path(__file__).resolve().parents[1] / "dev-pipeline/skills/"
          "web-design-guidelines/scripts/flag_antipatterns.py")


class WebFocusScanTests(unittest.TestCase):
    def scan(self, files):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, content in files.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            result = subprocess.run([sys.executable, "-I", str(SCRIPT), str(root)],
                                    capture_output=True, text=True)
            self.assertEqual(result.stderr, "")
            return result.returncode, result.stdout

    def test_shadow_does_not_hide_removed_css_focus(self):
        code, report = self.scan({"button.css": "button:focus-visible {\n"
                                 "  outline: none;\n  box-shadow: 0 0 0 2px blue;\n}\n"})
        self.assertEqual(code, 1)
        self.assertIn("button.css:2 — UX-63", report)

    def test_tailwind_focus_variant_does_not_hide_outline_removal(self):
        code, report = self.scan({"Button.tsx":
                                 '<button className="outline-none focus-visible:ring-2">Save</button>'})
        self.assertEqual(code, 1)
        self.assertIn("Button.tsx:1 — UX-63", report)

    def test_outline_offset_is_not_a_visible_outline(self):
        code, report = self.scan({"button.css":
                                 "button { outline: 0; outline-offset: 2px; }"})
        self.assertEqual(code, 1)
        self.assertIn("UX-63", report)

    def test_tailwind_outline_zero_is_reviewed(self):
        code, report = self.scan({"Button.tsx":
                                 '<button className="focus-visible:outline-0">Save</button>'})
        self.assertEqual(code, 1)
        self.assertIn("UX-63", report)

    def test_visible_or_transparent_outline_is_not_removed(self):
        for css in ("outline: 2px solid Highlight", "outline: 0.125rem solid transparent",
                    "outline: 0.5px solid CanvasText"):
            with self.subTest(css=css):
                code, report = self.scan({"button.css": f"button:focus-visible {{ {css}; }}"})
                self.assertEqual(code, 0, report)
        code, report = self.scan({"Button.tsx":
                                 '<button className="outline-hidden focus-visible:ring-2">Save</button>'})
        self.assertEqual(code, 0, report)

    def test_external_fallback_still_requires_human_confirmation(self):
        code, report = self.scan({
            "button.css": "button { outline: none; box-shadow: 0 0 0 2px blue; }",
            "theme.css": "@media (forced-colors: active) { button:focus-visible {"
                         " outline: 2px solid Highlight; } }",
        })
        self.assertEqual(code, 1)
        # A text scan cannot prove cascade/scope; this is a candidate, not a confirmed defect.
        self.assertIn("button.css:1 — UX-63", report)
        self.assertNotIn("theme.css:", report)

    def test_folder_scan_ignores_vendor_and_test_fixtures(self):
        code, report = self.scan({"node_modules/kit/button.css": "button { outline: none; }",
                                 "Button.test.tsx": '<button className="outline-none">Save</button>',
                                 "button.css": "button { outline: 2px solid transparent; }"})
        self.assertEqual(code, 0, report)


if __name__ == "__main__":
    unittest.main()
