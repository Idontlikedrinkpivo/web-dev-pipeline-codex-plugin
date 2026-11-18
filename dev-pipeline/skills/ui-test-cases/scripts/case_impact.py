"""Derive case coverage from the same Markdown IDs used by check_trace."""
from __future__ import annotations

import difflib
import re
from pathlib import Path

from check_trace import CASE, OP, NODE

SCREEN = re.compile(r'\bS-\d+\b')
REQ = re.compile(r'\b(?:UC|BR|FR|NFR)-\d+(?:\.\d+)*\b')
MODAL = re.compile(r'\bM-?\d+\b')
METHOD = re.compile(r'^(\s*)(?:get|post|put|patch|delete|head|options|trace):\s*(?:#.*)?$')
OPERATION = re.compile(r"""^\s*operationId:\s*['"]?([\w.-]+)""")


def blocks(text):
    heads = list(CASE.finditer(text))
    return [(m[1], text[m.start():heads[i+1].start() if i+1 < len(heads) else None].strip())
            for i, m in enumerate(heads)]


def discover(root):
    docs = root / 'documentation/ui'
    frames = {}
    for register in docs.rglob('frames-register.md'):
        if not register.resolve().is_relative_to(root.resolve()):
            raise ValueError('frames register outside project')
        for line in register.read_text().splitlines():
            match = re.match(r'^\|\s*(S-\d+)\s*\|', line)
            if match:
                for token in NODE.findall(line) + MODAL.findall(line):
                    frames.setdefault(token, set()).add(match[1])
    cases = {}
    paths = sorted([*docs.glob('**/test-cases/*.md'), *docs.rglob('test-cases.md')])
    for path in paths:
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('case path outside project')
        for cid, body in blocks(path.read_text()):
            if cid in cases:
                raise ValueError('duplicate case id: ' + cid)
            screens = set(SCREEN.findall(body))
            for token in NODE.findall(body) + MODAL.findall(body):
                screens.update(frames.get(token, ()))
            cases[cid] = dict(id=cid, path=path.relative_to(root).as_posix(), screens=sorted(screens),
                              operations=sorted({op for op, _ in OP.findall(body)}),
                              requirements=sorted(set(REQ.findall(body))))
    mapping = {'cases': list(cases.values()), 'changes': {}, 'prior_failures': []}
    if not cases:
        mapping['unavailable'] = 'mapping unavailable'
    return mapping


def affected_lines(old, new):
    for action, i, j, k, m in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if action != 'equal':
            yield from ((old, n) for n in range(i, j))
            yield from ((new, n) for n in range(k, m))


def operation_at(lines, index):
    # Bound the method by indentation, including responses below operationId.
    for start in range(index, -1, -1):
        method = METHOD.match(lines[start])
        if method:
            for end in range(start + 1, len(lines) + 1):
                if end == len(lines) or (lines[end].strip() and
                        len(lines[end]) - len(lines[end].lstrip()) <= len(method[1])):
                    if index < end:
                        return {m[1] for line in lines[start:end] if (m := OPERATION.match(line))}
                    return set()
    return set()


def identifiers(path, before, after):
    if '/screen-specs/' in path and SCREEN.match(Path(path).name):
        return 'screens', {SCREEN.match(Path(path).name)[0]}
    old, new = before.splitlines(), after.splitlines()
    found = set()
    for lines, index in affected_lines(old, new):
        if not lines[index].strip():
            continue
        if path.endswith('/frames-register.md'):
            dimension, ids = 'screens', SCREEN.findall(lines[index])
        elif path.startswith('documentation/requirements/srs/'):
            heading = next((line for line in reversed(lines[:index+1]) if line.startswith('#')), '')
            dimension, ids = 'requirements', REQ.findall(lines[index] + ' ' + heading)
        elif path.startswith('documentation/api/'):
            dimension, ids = 'operations', operation_at(lines, index)
        else:
            return None, set()
        if not ids:
            return None, set()
        found.update(ids)
    return (dimension, found) if found else (None, set())


def plan_units(plan, cases):
    operations = {op for case in cases for op in case['operations']}
    for unit in re.split(r'^###\s+(?=U\d+\.)', plan, flags=re.M)[1:]:
        rows = '\n'.join(line for line in unit.splitlines()
                         if re.search(r'\*\*(?:Цель|Документы|Файлы):?\*\*', line))
        tokens = set(re.findall(r'[\w.-]+', rows))
        files = set()
        for line in rows.splitlines():
            if '**Файлы' in line:
                files.update(re.findall(r"`([^`]+)`", line))
        yield unit.split('.', 1)[0], set(SCREEN.findall(rows)) | set(REQ.findall(rows)) | (operations & tokens), files


def failures(report):
    result, status = set(), None
    for line in report.splitlines():
        if not line.startswith('|'):
            status = None
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if 'Статус' in cells:
            status = cells.index('Статус')
        elif status is not None and len(cells) > status and re.fullmatch(r'TC-\d+', cells[0]):
            if '❌' in cells[status] or '⛔' in cells[status]:
                result.add(cells[0])
            elif '✅' in cells[status]:
                result.discard(cells[0])
    return sorted(result)
