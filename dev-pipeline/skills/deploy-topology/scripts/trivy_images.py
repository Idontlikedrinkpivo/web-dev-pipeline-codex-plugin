#!/usr/bin/env python3
"""Scan exact local images, retain complete evidence, enforce the hand-over gate.

trivy_images.py --out release/VERSION/scan [--trivy-image aquasec/trivy:VERSION] IMAGE...
trivy_images.py --check release/VERSION/scan/trivy-manifest.json [--risks accepted-risks.json]

Exit 0: complete/accepted; 1: scanner/evidence failure; 2: secrets or unaccepted CRITICAL.
Risks must identify image digest, vulnerability id, package, target, approver, reason,
accepted_on and expires (ISO dates). Never accepts a secret. No registry push or SBOM.
"""
from __future__ import annotations
import argparse
from datetime import date
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

VALIDATOR = Path(__file__).resolve().parents[2] / 'security-audit/scripts/trivy_reports.py'
spec = importlib.util.spec_from_file_location('trivy_evidence', VALIDATOR)
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


def gate(manifest_path: Path, risks_path: Path | None = None) -> int:
    if evidence.validate(manifest_path):
        raise ValueError('scanner failed; evidence incomplete')
    manifest = evidence.read_object(manifest_path)
    # A legacy completeness manifest is not proof that both scanners ran.
    if manifest.get('scanners') != ['vuln', 'secret'] or manifest.get('severities') != 'ALL':
        raise ValueError('both vuln and secret scans at all severities must be recorded')
    risks = json.loads(risks_path.read_text()) if risks_path else []
    if not isinstance(risks, list):
        raise ValueError('risks must be an array')
    allowed = set()
    for risk in risks:
        if not isinstance(risk, dict) or not all(isinstance(risk.get(k), str) and risk[k].strip()
                for k in ('digest', 'id', 'package', 'target', 'approved_by', 'reason', 'accepted_on', 'expires')):
            raise ValueError('incomplete risk acceptance')
        if not date.fromisoformat(risk['accepted_on']) <= date.today() <= date.fromisoformat(risk['expires']):
            raise ValueError('risk acceptance is future-dated or expired')
        allowed.add((risk['digest'], risk['id'], risk['package'], risk['target']))
    critical = secrets = high = 0
    for record in manifest['records']:
        report = evidence.read_object(manifest_path.parent / record['report'])
        for result in report['Results']:
            secrets += len(result.get('Secrets') or [])
            for finding in result.get('Vulnerabilities') or []:
                high += finding['Severity'] == 'HIGH'
                key = (record.get('digest'), finding['VulnerabilityID'], finding.get('PkgName'), result['Target'])
                critical += finding['Severity'] == 'CRITICAL' and key not in allowed
    print(f'HIGH {high}; unaccepted CRITICAL {critical}; secrets {secrets}')
    return 2 if critical or secrets else 0


def scan(images: list[str], out: Path, scanner: str) -> Path:
    if not images or len(images) != len(set(images)):
        raise ValueError('distinct nonempty image list required')
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ValueError('scan directory must be empty: do not reuse stale reports')
    records = []
    scanner_version = subprocess.run(['docker', 'run', '--rm', scanner, '--version'], capture_output=True, text=True, check=True).stdout
    for i, image in enumerate(images):
        info = json.loads(subprocess.run(['docker', 'image', 'inspect', image], capture_output=True,
                                        text=True, check=True).stdout)[0]
        command = ['docker', 'run', '--rm', '-v', '/var/run/docker.sock:/var/run/docker.sock',
                   '-v', 'pipeline-trivy-cache:/root/.cache/trivy', scanner,
                   'image', '--image-src', 'docker', '--scanners', 'vuln,secret',
                   '--image-config-scanners', 'secret', '--severity', 'UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL',
                   '--exit-code', '0', '--format', 'json', '--timeout', '5m', image]
        result = subprocess.run(command, capture_output=True, text=True, timeout=360)
        filename = f'trivy-{i+1}.json'
        # Trivy redacts secret matches itself; additionally discard excerpts in release reports.
        payload = result.stdout
        try:
            report = json.loads(payload)
            for target in report.get('Results') or []:
                for secret in target.get('Secrets') or []:
                    secret.pop('Code', None)
                    secret.pop('Match', None)
            # Image metadata may include the offending ENV/history command itself.
            metadata = report.get('Metadata', {})
            metadata.pop('ImageConfig', None)
            payload = json.dumps(report, ensure_ascii=False, indent=2)
        except (ValueError, TypeError, AttributeError):
            payload = ''  # malformed raw output may itself contain credentials
        path = out / filename
        path.write_text(payload); path.chmod(0o600)
        records.append({'image': image, 'digest': info['Id'], 'report': filename,
                        'exit_code': result.returncode, 'command': command})
        # Preserve partial progress, including a failed scan; never call it clean.
        manifest = out / 'trivy-manifest.json'
        manifest.write_text(json.dumps({'expected': images, 'records': records, 'scanners': ['vuln', 'secret'],
                                        'severities': 'ALL', 'scanner_version': scanner_version}, indent=2))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images', nargs='*'); parser.add_argument('--out', type=Path)
    parser.add_argument('--check', type=Path); parser.add_argument('--risks', type=Path)
    parser.add_argument('--trivy-image', default='aquasec/trivy:0.67.2')
    args = parser.parse_args()
    try:
        if args.check:
            if args.images or args.out: raise ValueError('--check cannot scan images')
            manifest = args.check
        else:
            if not args.out: raise ValueError('--out required')
            manifest = scan(args.images, args.out, args.trivy_image)
        return gate(manifest, args.risks)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'FAILED: {type(error).__name__}: scan/evidence unavailable or invalid', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
