"""Release evidence validation, isolated from Docker and Trivy."""
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'dev-pipeline/skills/security-audit/scripts/trivy_reports.py'


class TrivyReports(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def record(self, image, index=0):
        report = self.root / f'report-{index}.json'
        report.write_text(json.dumps({'SchemaVersion': 2, 'ArtifactName': image,
                                     'ArtifactType': 'container_image', 'Results': []}), encoding='utf-8')
        return {'image': image, 'report': report.name, 'exit_code': 0}

    def run_validator(self, expected, records):
        self.assertTrue(SCRIPT.is_file(), 'U17 validator CLI is not implemented')
        manifest = self.root / 'manifest.json'
        manifest.write_text(json.dumps({'expected': expected, 'records': records}), encoding='utf-8')
        return subprocess.run([sys.executable, str(SCRIPT), str(manifest)],
                              capture_output=True, text=True,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))

    def test_two_images_one_report_is_incomplete(self):
        result = self.run_validator(['api:v1', 'web:v1'], [self.record('api:v1')])
        self.assertEqual(result.returncode, 2)
        self.assertIn('incomplete', result.stderr)

    def test_complete_zero_findings_and_independent_reports(self):
        records = [self.record('api:v1'), self.record('web:v1', 1)]
        result = self.run_validator(['api:v1', 'web:v1'], records)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('complete', result.stdout)

    def test_missing_empty_corrupt_truncated_and_wrong_schema(self):
        record = self.record('api:v1')
        path = self.root / record['report']
        for payload in [None, '', '{broken', '{"Results":[', '{}',
                        '{"SchemaVersion":2,"ArtifactName":"api:v1","ArtifactType":"container_image","Results":null}',
                        '{"SchemaVersion":2,"ArtifactName":"api:v1","ArtifactType":"container_image","Results":[{}]}']:
            with self.subTest(payload=payload):
                if payload is None:
                    path.unlink()
                else:
                    path.write_text(payload, encoding='utf-8')
                self.assertEqual(self.run_validator(['api:v1'], [record]).returncode, 2)

    def test_duplicate_unexpected_wrong_identity_and_reused_report(self):
        api = self.record('api:v1')
        web = self.record('web:v1', 1)
        cases = [(['api:v1'], [api, api]), (['api:v1'], [web]),
                 (['api:v1', 'api:v1'], [api]),
                 (['api:v1', 'web:v1'], [api, dict(web, report=api['report'])])]
        for expected, records in cases:
            with self.subTest(expected=expected, records=records):
                self.assertEqual(self.run_validator(expected, records).returncode, 2)

    def test_report_artifact_name_must_match_record_image(self):
        record = self.record('api:v1', 7)
        path = self.root / record['report']
        payload = json.loads(path.read_text(encoding='utf-8'))
        payload['ArtifactName'] = 'web:v1'
        path.write_text(json.dumps(payload), encoding='utf-8')
        result = self.run_validator(['api:v1'], [record])
        self.assertEqual(result.returncode, 2)
        self.assertIn('incomplete', result.stderr)
        self.assertNotIn('complete:', result.stdout)

    def test_failed_scan_preserves_scanner_exit(self):
        for code in [1, 7]:
            record = dict(self.record('api:v1'), exit_code=code)
            result = self.run_validator(['api:v1'], [record])
            self.assertEqual(result.returncode, code)
            self.assertNotIn('complete:', result.stdout)

    def test_digest_and_findings_schema(self):
        record = dict(self.record('api:v1'), digest='sha256:abc')
        path = self.root / record['report']
        payload = json.loads(path.read_text(encoding='utf-8'))
        payload['ArtifactID'] = 'sha256:abc'
        payload['Results'] = [{'Target': 'alpine', 'Vulnerabilities': [
            {'VulnerabilityID': 'CVE-TEST', 'Severity': 'HIGH'}]}]
        path.write_text(json.dumps(payload), encoding='utf-8')
        self.assertEqual(self.run_validator(['api:v1'], [record]).returncode, 0)
        payload['ArtifactID'] = 'sha256:wrong'
        path.write_text(json.dumps(payload), encoding='utf-8')
        self.assertEqual(self.run_validator(['api:v1'], [record]).returncode, 2)

    def test_real_trivy_metadata_image_id_and_conflicting_ids(self):
        record = dict(self.record('api:v1'), digest='sha256:abc')
        path = self.root / record['report']
        payload = json.loads(path.read_text())
        payload['Metadata'] = {'ImageID': 'sha256:abc'}
        path.write_text(json.dumps(payload))
        self.assertEqual(self.run_validator(['api:v1'], [record]).returncode, 0)
        payload['ArtifactID'] = 'sha256:wrong'
        path.write_text(json.dumps(payload))
        self.assertEqual(self.run_validator(['api:v1'], [record]).returncode, 2)

    def test_success_iff_exact_complete_successful_records(self):
        images = ['api:v1', 'web:v1', 'extra:v1']
        for size in range(4):
            for selected in itertools.combinations(images, size):
                records = [self.record(image, i) for i, image in enumerate(selected)]
                for code in [0, 1]:
                    rows = [dict(record, exit_code=code) for record in records]
                    result = self.run_validator(images[:2], rows)
                    self.assertEqual(result.returncode == 0,
                                     set(selected) == set(images[:2]) and code == 0,
                                     (selected, code, result.stderr))


if __name__ == '__main__':
    unittest.main()
