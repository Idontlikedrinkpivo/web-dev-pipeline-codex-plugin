"""Prove that a reviewed commit is followed only by portable report commits.

This validation does not change checkpoint restore's exact-HEAD contract.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPORT_NAMES = frozenset(('iteration.json', 'ui-acceptance.json', 'test-run.md',
                          'summary.md', 'progress.md', 'work-run.md', 'resume.md',
                          'context-handover.md', 'run-state.json'))


def report_path(path: str, version: str | None) -> bool:
    parts = path.split('/')
    if len(parts) < 4 or parts[:2] != ['documentation', 'plans'] or parts[2] != version or not re.fullmatch(r'\d+\.\d+\.\d+', parts[2]):
        return False
    if len(parts) == 4:
        return parts[3] in REPORT_NAMES
    if len(parts) not in (6, 7) or parts[3] != 'checkpoints' or not re.fullmatch(r'[0-9a-f]{32}', parts[4]):
        return False
    if len(parts) == 6:
        return parts[5] in ('manifest.json', 'staged.patch', 'unstaged.patch')
    return parts[5] == 'blobs' and bool(re.fullmatch(r'[0-9a-f]{64}', parts[6]))


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True)
    if result.returncode:
        raise ValueError(result.stderr.decode(errors='replace').strip() or 'Git proof unavailable')
    return result.stdout.decode(errors='surrogateescape')


def report_only_descendant(root: Path, tested: str, *, version: str | None,
                           protected: tuple[str, ...] = (),
                           allow_dirty: bool = False) -> tuple[bool, str]:
    """Keep the tested SHA; reject unknown history, source changes and dirty code.

    Every intervening commit is inspected, so changing and reverting source
    cannot masquerade as an unchanged tree. Empty commits are not report proof.
    allow_dirty is for recording an observed run, never a close/review gate.
    """
    try:
        if not isinstance(tested, str) or not re.fullmatch(r'[0-9a-f]{40,64}', tested):
            return False, 'reviewed SHA missing or malformed'
        head = _git(root, 'rev-parse', '--verify', 'HEAD^{commit}').strip()
        _git(root, 'merge-base', '--is-ancestor', tested, head)
        def allowed(path: str) -> bool:
            return report_path(path, version) and not any(path == p or path.startswith(p.rstrip('/') + '/') for p in protected)
        if not allow_dirty:
            dirty = set(_git(root, 'diff', '--name-only', '-z', 'HEAD', '--').split('\0'))
            dirty.update(_git(root, 'ls-files', '--others', '--exclude-standard', '-z').split('\0'))
            if any(path and not allowed(path) for path in dirty):
                return False, 'uncommitted code/cases/scope after review'
        if head == tested:
            return True, 'exact reviewed HEAD'
        for commit in _git(root, 'rev-list', tested + '..' + head).splitlines():
            paths = set(_git(root, 'diff-tree', '--root', '-r', '-m', '--no-renames',
                             '--no-commit-id', '--name-only', '-z', commit).split('\0')) - {''}
            if not paths or any(not allowed(path) for path in paths):
                return False, 'HEAD includes a non-report or reviewed-scope commit'
        return True, 'reviewed SHA preserved through report-only descendants'
    except (ValueError, OSError) as exc:
        return False, f'review ancestry unavailable: {exc}'
