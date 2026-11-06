"""Validate per-image Trivy evidence: python3 trivy_reports.py <manifest.json>.

Manifest paths are relative to the manifest. Exit 2 means incomplete evidence;
a recorded nonzero scanner exit is preserved. Completeness is not a severity verdict.
Standard library only.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys


def read_object(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'{path}: expected JSON object')
    return value


def validate(path: Path) -> int:
    manifest = read_object(path)
    expected, records = manifest.get('expected'), manifest.get('records')
    if (not isinstance(expected, list) or not expected
            or any(not isinstance(image, str) or not image.strip() for image in expected)
            or len(set(expected)) != len(expected) or not isinstance(records, list)):
        raise ValueError('invalid expected images or records')
    seen: set[str] = set()
    reports: set[Path] = set()
    scanner_exit = 0
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('invalid record')
        image, report, code = record.get('image'), record.get('report'), record.get('exit_code')
        if (not isinstance(image, str) or image not in expected or image in seen
                or not isinstance(report, str) or not report.strip()
                or type(code) is not int or not 0 <= code <= 255):
            raise ValueError('duplicate, unexpected or invalid image record')
        seen.add(image)
        report_path = (path.parent / report).resolve()
        if report_path in reports:
            raise ValueError('each image requires a separate report')
        reports.add(report_path)
        if code:
            scanner_exit = scanner_exit or code
            continue
        data = read_object(report_path)
        if (data.get('SchemaVersion') != 2 or data.get('ArtifactType') != 'container_image'
                or data.get('ArtifactName') != image):
            raise ValueError(f'{image}: report schema or artifact identity mismatch')
        if 'digest' in record:
            metadata = data.get('Metadata', {})
            if not isinstance(metadata, dict):
                raise ValueError(f'{image}: invalid metadata')
            identities = [value for value in (data.get('ArtifactID'), metadata.get('ImageID')) if value is not None]
            if (not isinstance(record['digest'], str) or not record['digest'] or not identities
                    or any(value != record['digest'] for value in identities)):
                raise ValueError(f'{image}: artifact digest mismatch')
        results = data.get('Results')
        if not isinstance(results, list):
            raise ValueError(f'{image}: Results must be an array')
        for result in results:
            if not isinstance(result, dict) or not isinstance(result.get('Target'), str):
                raise ValueError(f'{image}: invalid result')
            vulnerabilities = result.get('Vulnerabilities', [])
            if vulnerabilities is None:
                vulnerabilities = []  # Trivy may emit null for an empty optional field.
            if not isinstance(vulnerabilities, list) or any(
                not isinstance(vulnerability, dict)
                or not isinstance(vulnerability.get('VulnerabilityID'), str)
                or vulnerability.get('Severity') not in {'UNKNOWN', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'}
                for vulnerability in vulnerabilities
            ):
                raise ValueError(f'{image}: invalid vulnerabilities')
            secrets = result.get('Secrets', [])
            if secrets is None: secrets = []
            if not isinstance(secrets, list) or any(
                not isinstance(secret, dict) or not isinstance(secret.get('RuleID'), str)
                or secret.get('Severity') not in {'UNKNOWN', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'}
                for secret in secrets
            ):
                raise ValueError(f'{image}: invalid secrets')
    if scanner_exit:
        return scanner_exit
    if seen != set(expected):
        raise ValueError('expected image set does not match complete records')
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        sys.stderr.write('usage: trivy_reports.py <manifest.json>\n')
        return 2
    try:
        code = validate(Path(sys.argv[1]))
    except (OSError, ValueError) as error:
        sys.stderr.write(f'incomplete: {error}\n')
        return 2
    if code:
        sys.stderr.write(f'incomplete: scanner exited {code}\n')
        return code
    sys.stdout.write('complete: every expected image has successful matching evidence\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
