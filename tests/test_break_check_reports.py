"""New worker fields remain readable by the existing details alarm detector.

These checks validate report plumbing, not a model's adherence to the packet.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ALARM = ROOT / 'dev-pipeline/skills/work/scripts/report_alarm.py'


class BreakCheckReports(unittest.TestCase):
    def alarm(self, details, concerns='нет'):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'U1-details.md'
            path.write_text(details, encoding='utf-8')
            return subprocess.run(['python3.12', str(ALARM), str(path), '--concerns', concerns],
                                  text=True, capture_output=True)

    def test_rule_and_screen_evidence_fields_are_not_schema_errors(self):
        result = self.alarm('''TESTS: test_rounding.py, test_threshold.py
RED OBSERVED: test_threshold — AssertionError: expected 100
BREAK CHECK:
  rounding at .005 → test_rounding: AssertionError expected 1.01, got 1.00
  threshold >= 100 changed to > 100 → test_threshold: AssertionError
  all changed lines restored; final checks green
SCREEN CHECK:
  1366x768, long values/tall rows, horizontal and vertical scroll → ok; scroll.png
  1920x1080, edge menu/dialog → ok; menu.png, dialog.png
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('тревожных слов нет', result.stdout)

    def test_unverified_break_is_not_hidden_by_new_field(self):
        result = self.alarm('BREAK CHECK: rounding boundary not tested; runtime unavailable\n')
        self.assertEqual(result.returncode, 1)
        self.assertIn('BREAK CHECK', result.stdout)
        self.assertIn('CONCERNS пусты', result.stdout)

    def test_intentional_failure_remains_inspectable_and_does_not_mask_other_alarm(self):
        details = ('BREAK CHECK: test_rounding failed after changing the precision; restored\n'
                   'VERIFICATION: typecheck not run\n')
        result = self.alarm(details)
        self.assertEqual(result.returncode, 1)
        self.assertIn('BREAK CHECK', result.stdout)
        self.assertIn('VERIFICATION', result.stdout)
        # Reported concerns allow the existing flow; both lines are still printed for inspection.
        reported = self.alarm(details, concerns='typecheck unavailable; inspect details')
        self.assertEqual(reported.returncode, 0, reported.stderr)
        self.assertIn('VERIFICATION', reported.stdout)


if __name__ == '__main__':
    unittest.main()
