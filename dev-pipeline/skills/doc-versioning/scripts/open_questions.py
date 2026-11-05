"""Read per-document question debt; no shared file, writes or third-party packages.

Usage: open_questions.py <project> [--for <stage> | --pending]
"""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import NamedTuple

STAGES = ('схема БД', 'API', 'архитектура', 'макеты', 'ТЗ на экраны',
          'тест-кейсы', 'план', 'разработка', 'релиз', 'эксплуатация')
BLOCKER = 'Блокирует старт'
DEFERRED = 'Отложено'
LEGACY = 'Можно решить при архитектуре'


class Question(NamedTuple):
    path: str
    line: int
    text: str
    classification: str

    @property
    def recipient(self) -> str | None:
        return recipient(self.classification)


def recipient(value: str) -> str | None:
    value = value.strip()
    if value == LEGACY:
        return 'архитектура'
    if value in (BLOCKER, DEFERRED):
        return value
    if value.startswith('Решить при: ') and value[12:] in STAGES:
        return value[12:]
    return None


def valid_class(value: str) -> bool:
    return recipient(value) is not None or bool(re.fullmatch(r'Решено:\s+\S.*', value.strip()))


def question_files(root: Path) -> list[Path]:
    docs = root / 'documentation'
    if docs.is_symlink():
        return []
    found = []
    for folder, dirs, files in os.walk(docs, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d != '_web-docs' and not (Path(folder) / d).is_symlink())
        if 'open-questions.md' in files:
            p = Path(folder) / 'open-questions.md'
            if not p.is_symlink():
                found.append(p)
    return sorted(found)


def cells(line: str) -> list[str]:
    return [c.strip() for c in re.split(r'(?<!\\)\|', line.strip().strip('|'))]


def read_file(root: Path, path: Path) -> list[Question]:
    rows, columns = [], None
    lines = path.read_text(encoding='utf-8').splitlines()
    rel = path.relative_to(root).as_posix()
    fenced = False
    for n, line in enumerate(lines, 1):
        if re.match(r'^\s*(```|~~~)', line):
            fenced = not fenced
        if fenced:
            continue
        marker = re.match(r'<!-- ce-question: ([^;]+); class: (.*?); source: .*?-->', line.strip())
        if marker:
            title = next((s.lstrip('# ').strip() for s in lines[n:] if s.strip()), marker[1])
            rows.append(Question(rel, n, f'{marker[1]}: {title}', marker[2].strip()))
        if not line.strip().startswith('|'):
            columns = None
            continue
        parts = cells(line)
        if 'Вопрос' in parts and 'Класс' in parts:
            columns = parts.index('Вопрос'), parts.index('Класс')
        elif columns and not all(re.fullmatch(r'[:\- ]+', c) for c in parts):
            text = parts[columns[0]] if len(parts) > columns[0] else ''
            classification = parts[columns[1]] if len(parts) > columns[1] else ''
            rows.append(Question(rel, n, text, classification))
    return rows


def scan(root: Path) -> list[Question]:
    return [q for path in question_files(root) for q in read_file(root, path)]


def groups(questions: list[Question]) -> dict[str, list[Question]]:
    return {name: [q for q in questions if q.recipient == name]
            for name in (BLOCKER, *STAGES, DEFERRED) if any(q.recipient == name for q in questions)}


def pending_lines(questions: list[Question]) -> list[str]:
    return [f'{name}: {len(rows)} — ' + ', '.join(dict.fromkeys(q.path for q in rows))
            for name, rows in groups(questions).items()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument('--for', dest='stage', choices=STAGES)
    choice.add_argument('--pending', action='store_true')
    args = parser.parse_args()
    questions = scan(args.project.resolve())
    if args.pending:
        print('\n'.join(pending_lines(questions)) or 'Открытых вопросов нет')
        return
    count = 0
    for name, rows in groups(questions).items():
        if args.stage and name not in (BLOCKER, args.stage):
            continue
        print(name + ':')
        for row in rows:
            print(f'{row.path}\t{row.text}')
            count += 1
    print(f'Всего открытых вопросов: {count}')


if __name__ == '__main__':
    main()
