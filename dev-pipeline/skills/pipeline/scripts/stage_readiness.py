"""Read-only dependency readiness from committed documents and stage closes."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

# key: number, label, skill, prerequisites, canonical artifact
STAGES = {
    'srs': (2, 'SRS', 'srs-writer', (), 'requirements/srs/srs.md'),
    'db': (3, 'схема БД', 'db-schema-design', ('srs',), 'db/schema.md'),
    'api': (4, 'API', 'openapi-spec-generator', ('srs', 'db'), 'api/openapi.yaml'),
    'arch': (5, 'архитектура', 'clean-architecture-design', ('srs', 'db', 'api'), 'architecture/architecture.md'),
    'scaffold': (6, 'каркас', 'repo-scaffold', ('arch',), 'project-map/project-map.md'),
    'design': (7, 'макеты', 'ui-design', ('srs',), 'ui/frames-register.md'),
    'specs': (8, 'ТЗ на экраны', 'screen-spec', ('design', 'api'), 'ui/screen-specs/S-*.md'),
    'cases': (9, 'тест-кейсы', 'ui-test-cases write', ('specs',), 'ui/test-cases/README.md'),
    'check': (10, 'сверка документов', 'docs-consistency', ('scaffold', 'cases'), ''),
}
CLOSE_WORDS = {'srs': r'\bSRS\b', 'db': r'схем\w* БД', 'api': r'\b(?:API|OpenAPI)\b',
               'arch': r'архитектур|доменн\w* модел|сценари', 'scaffold': r'scaffold|каркас|карта проекта',
               'design': r'макет|ui-design', 'specs': r'ТЗ на экран', 'cases': r'тест-кейс'}


def artifacts(root: Path, key: str) -> list[str]:
    import where_am_i as w
    if key in ('arch', 'specs'):
        paths = [d.rel for d in w.registry(root) if d.stage == STAGES[key][0]]
        if paths:
            return paths
    pattern = STAGES[key][4]
    paths = sorted((root / 'documentation').glob(pattern)) if pattern else []
    if key in ('design', 'cases'):
        paths += sorted((root / 'documentation').glob(pattern.replace('ui/', 'ui/*/', 1)))
    return [p.relative_to(root).as_posix() for p in paths] or ['documentation/' + pattern]


def closed(root: Path, key: str, version: str | None = None) -> bool:
    """A stamp/file alone is not a close; an empty explicit close is allowed."""
    import where_am_i as w
    if key == 'check':
        if not version:
            return False
        folder = root / 'documentation/plans' / version
        report = folder / 'docs-consistency.md'
        return (w.git_ok(root, 'cat-file', '-e', f'HEAD:{report.relative_to(root)}')
                and w.read(report).startswith('Verdict: PASS') and w.consistency(root, folder)[1] is None)
    paths = artifacts(root, key)
    if not all(w.git_ok(root, 'cat-file', '-e', f'HEAD:{p}') for p in paths):
        return False
    scopes = list(paths)
    scopes += {'srs': ['documentation/requirements/srs/areas'],
               'api': ['documentation/api/paths', 'documentation/api/components'],
               'db': ['documentation/db/migrations'],
               'arch': ['documentation/architecture/scenarios'],
               'specs': [':(glob)documentation/ui/**/screen-specs/**'],
               'design': [':(glob)documentation/ui/**/frames-register.md'],
               'cases': [':(glob)documentation/ui/**/test-cases/**']}.get(key, [])
    if w.git(root, 'status', '--porcelain', '--', *scopes):
        return False
    close_sha = ''
    log = w.git(root, 'log', '--format=%H%x09%s%x09%b%x00', '-n', '3000')
    for record in log.split('\0'):
        parts = record.strip('\n').split('\t', 2)
        if len(parts) < 3:
            continue
        sha, subject, body = parts
        explicit = re.search(rf'^Stage-Closed: {key} (\d+\.\d+\.\d+)\s*$', body, re.M)
        legacy = (subject.startswith(('docs: ', 'chore: ', 'chore(scaffold): ')) and re.search(CLOSE_WORDS[key], subject)
                  and (w.VERSION_RX.search(subject) or key == 'scaffold') and not w.NOT_CLOSE.search(subject))
        if explicit or legacy or w.ALL_CLOSE.search(subject):
            close_sha = sha
            break
    if not close_sha or not all(w.git_ok(root, 'cat-file', '-e', f'{close_sha}:{p}') for p in paths):
        return False
    # Changes since the close need their own closure, even if the old version text remains.
    return not w.git(root, 'diff', '--name-only', close_sha, 'HEAD', '--', *scopes)


def skips(root: Path) -> dict[str, str]:
    try:
        config = json.loads((root / 'documentation/.dev-pipeline.json').read_text())
    except (OSError, ValueError):
        config = {}
    caps = config.get('capabilities', {}) if isinstance(config, dict) else {}
    caps = caps if isinstance(caps, dict) else {}
    result = {}
    for capability, keys, reason in [('storage', ('db',), 'нет хранилища'),
                                      ('http', ('api',), 'нет HTTP'),
                                      ('screens', ('design', 'specs', 'cases'), 'нет экранов')]:
        if caps.get(capability) is False:
            result.update(dict.fromkeys(keys, reason))
    if isinstance(config, dict) and str(config.get('design', '')).lower().startswith('без макетов'):
        result['design'] = 'решение работать без макетов'
    return result


def session_rows(root: Path, version: str | None) -> list[dict]:
    """Use only the current parent's registry or a uniquely proven child owner."""
    if not version or not os.environ.get('CODEX_THREAD_ID'):
        return []
    import subsessions as s
    paths = s.resolve_paths(root, version, os.environ['CODEX_THREAD_ID'])
    parent, rows = s.read(paths.local / 'sessions.md')
    if rows and parent == paths.chat_key:
        return rows
    owner = s.owner_of(paths, paths.chat_key)
    if owner:
        owner_paths = s.resolve_paths(root, version, owner[0])
        return s.read(owner_paths.local / 'sessions.md')[1]
    return []


def evaluate(root: Path, version: str | None, rows: list[dict] | None = None) -> list[dict]:
    import where_am_i as w
    rows = session_rows(root, version) if rows is None else rows
    skipped = skips(root)
    done = {key: closed(root, key, version) for key in STAGES if key not in skipped}
    busy = {r['stage']: r for r in rows if r.get('state') == 'идёт'}
    current = os.environ.get('CODEX_THREAD_ID', '')
    result = []
    for key, (number, label, skill, dependencies, _) in STAGES.items():
        if key == 'srs':
            continue
        row = dict(key=key, number=number, label=label, skill=skill, missing=[], inputs=[])
        if key in skipped:
            row.update(state='skipped', reason=skipped[key])
        elif key in busy:
            row.update(state='here' if busy[key].get('id') == current else 'busy', title=busy[key]['title'])
        elif done[key]:
            row.update(state='closed')
        else:
            for dep in dependencies:
                if dep in skipped:
                    continue
                name = STAGES[dep][1]
                if done[dep] and dep not in busy:
                    row['inputs'].append(name)
                    continue
                if dep in busy:
                    name += ' (идёт в соседнем чате)' if busy[dep].get('id') != current else ' (не закрыт здесь)'
                elif any((root / p).is_file() for p in artifacts(root, dep)):
                    name += ' (написан, этап не закрыт)'
                row['missing'].append(name)
            written = key != 'check' and any((root / p).is_file() for p in artifacts(root, key))
            row.update(state='waiting' if row['missing'] else 'here' if written else 'ready')
        result.append(row)
    return result


def lines(states: list[dict]) -> list[str]:
    out = []
    for r in states:
        label = r['label']
        if r['state'] == 'ready':
            out.append(f"можно начать сейчас: {label} ({r['skill']}) — входы на ветке: " + ', '.join(r['inputs']))
        elif r['state'] == 'waiting':
            out.append(f"ждёт входов: {label} — нет: " + ', '.join(r['missing']))
        elif r['state'] == 'busy':
            out.append(f"идёт в соседнем чате: {label} — «{r['title']}»")
        elif r['state'] == 'here':
            out.append(f'не закрыт здесь: {label} — дописать и закрыть этап')
        elif r['state'] == 'skipped':
            out.append(f"пропущен: {label} — {r['reason']}")
    if not any(r['state'] in ('ready', 'here') for r in states):
        out.append('Начать здесь нечего — ждать входов или остановиться.')
    return out
