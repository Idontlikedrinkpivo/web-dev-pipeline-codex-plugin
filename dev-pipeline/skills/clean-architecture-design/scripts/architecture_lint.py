#!/usr/bin/env python3
"""Read-only finite architecture terminology checks; semantic review stays human.

architecture_lint.py FILE... [--json] returns 1 for definite errors, 0 for
clean/manual-warning output, 2 for unreadable/malformed Markdown input.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


DENIED_HEADINGS = frozenset({
    'правила по виду', 'dto или сущность', 'путь одного запроса', 'кольцо',
    'сокращения', 'решение о глубине', 'решение о стеке', 'порядок реализации',
    'предположения', 'допущения',
})
FOUNDATION_DUPLICATES = frozenset({'данные', 'каналы', 'ограничения'})
HISTORY = frozenset({'журнал изменений', 'история', 'история изменений', 'history', 'changelog'})
AGGREGATE = re.compile(r'\bагрегат(?:а|у|ом|е|ы|ов|ам|ами|ах)?\b', re.I)
EQUATION = re.compile(r'\bагрегат\s*[»"`]*\s*(?:=|—|это)\s*[«"`]*сущность\b', re.I)


def lint(path: Path) -> list[dict]:
    text = path.read_text(encoding='utf-8')
    issues = []
    fence = None
    history_level = None

    def issue(line: int, rule: str, severity: str, message: str) -> None:
        issues.append({'file': str(path), 'line': line, 'rule': rule,
                       'severity': severity, 'message': message})

    for number, line in enumerate(text.splitlines(), 1):
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence is not None:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= fence[1] and not marker[2].strip():
                fence = None
            continue
        if marker:
            fence = (marker[1][0], len(marker[1]), number)
            continue
        if line.lstrip().startswith('>'):
            continue  # cited material, not the live design
        heading = re.match(r'^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$', line)
        if heading:
            level = len(heading[1])
            title = re.sub(r'^\d+[.)]?\s*', '', heading[2]).strip().casefold()
            if history_level is not None and level <= history_level:
                history_level = None
            if title in HISTORY:
                history_level = level
            if history_level is not None:
                continue
            if title in DENIED_HEADINGS:
                issue(number, 'ARCH-H001', 'error', 'Forbidden active heading; use the template home.')
            if path.name == 'foundation.md' and title in FOUNDATION_DUPLICATES:
                issue(number, 'ARCH-H002', 'error', 'Duplicate foundation fact heading; use §1 tables.')
            if AGGREGATE.fullmatch(title):
                issue(number, 'ARCH-T001', 'error', 'Use the canonical entity term: сущность.')
        if history_level is not None:
            continue
        prose = re.sub(r'`+[^`]*`+', '', line)
        prose = re.sub(r'\[[^\]]*\]\([^)]*\)', '', prose)
        if EQUATION.search(prose):
            issue(number, 'ARCH-T001', 'error', 'Forbidden aggregate/entity equation.')
        elif AGGREGATE.search(prose):
            issue(number, 'ARCH-M001', 'warning', 'Manual review: distinguish active synonym from explanatory mention.')
    if fence:
        issue(fence[2], 'ARCH-INPUT', 'error', 'Unclosed Markdown fence; remaining applicability is unknown.')
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+', type=Path)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    issues = []
    for path in args.files:
        try:
            issues.extend(lint(path))
        except (OSError, UnicodeError) as exc:
            issues.append({'file': str(path), 'line': 1, 'rule': 'ARCH-INPUT',
                           'severity': 'error', 'message': str(exc)})
    if args.json:
        print(json.dumps(issues, ensure_ascii=False))
    else:
        for item in issues:
            print('{file}:{line}: {rule} {severity}: {message}'.format(**item))
    if any(item['rule'] == 'ARCH-INPUT' for item in issues):
        return 2
    return int(any(item['severity'] == 'error' for item in issues))


if __name__ == '__main__':
    raise SystemExit(main())
