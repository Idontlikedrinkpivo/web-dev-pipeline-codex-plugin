"""Locate the pipeline documents inside a Git checkout without scanning dependency trees."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from state_paths import checkout_root, contained_path

MARKERS = ('documentation/.dev-pipeline.json', 'documentation/requirements/srs/srs.md',
           'documentation/requirements/business-requirements/business-requirements.md')


def marked_folders(filenames: bytes) -> set[Path]:
    folders = set()
    for filename in os.fsdecode(filenames).split('\0'):
        for marker in MARKERS:
            if filename == marker or filename.endswith('/' + marker):
                parent = Path(filename.removesuffix(marker))
                if 'documentation' not in parent.parts:
                    folders.add(parent)
                break
    return folders


def project_root(given: Path) -> Path:
    top = checkout_root(given)
    start = given.resolve()
    for parent in (start, *start.parents):
        if parent == top:
            break
        if any((parent / marker).is_file() for marker in MARKERS):
            return contained_path(top, parent)
    # Git lists canonical artifacts only. A legacy documentation/ folder or a stray
    # plans/ created by an older pickup is not stronger evidence than those artifacts.
    result = subprocess.run(['git', '-C', str(top), 'ls-files', '-z', '--',
                             *(':(glob)**/' + marker for marker in MARKERS)],
                            check=True, capture_output=True)
    candidates = {top} if any((top / marker).is_file() for marker in MARKERS) else set()
    for rel in marked_folders(result.stdout):
        folder = top / rel
        if any((folder / marker).is_file() for marker in MARKERS):
            candidates.add(contained_path(top, folder))
    if len(candidates) > 1:
        if start != top and top in candidates and top / 'documentation' in (start, *start.parents):
            return top
        raise ValueError('Уточните папку проекта: ' + ', '.join(str(p) for p in sorted(candidates)))
    return next(iter(candidates), top)


def plans_folder(project: Path, version: str = '') -> Path:
    return contained_path(project, project / 'documentation' / 'plans' / version)


def ref_folder(top: Path, project: Path, ref: str) -> Path:
    files = subprocess.run(['git', '-C', str(top), 'ls-tree', '-rz', '--name-only', ref],
                           check=True, capture_output=True).stdout
    folders = marked_folders(files)
    selected = project.relative_to(top)
    if selected != Path('.') or not folders:
        return selected
    if len(folders) == 1:
        return folders.pop()
    raise ValueError('На ветке несколько проектов: ' + ', '.join(str(p) for p in sorted(folders)))


if __name__ == '__main__':
    try:
        print(project_root(Path(sys.argv[1])))
    except ValueError as exc:
        sys.exit(str(exc))
