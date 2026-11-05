#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Write each share of a mutation run its own Stryker config, the progress page's parts.json and the commands to run —
so the details that broke real runs are decided here, not remembered (work → references/health.md → Mutation runs).

    python3 mutation_config.py <spec.json>

Bounded specs require budget={seconds: positive integer, workers: positive integer}
and risk_scope={mandatory: [file:start-end], optional: [...]}. Record explicit
cancellation per part with status='SKIPPED BY USER', user_cancelled=true,
reason and mutate ranges. Exhaustion/unavailable runners are incomplete/not-run;
generation never establishes PASS or actual executed coverage. The caller must
enforce the recorded time budget while supervising the printed commands.

Legacy spec.json (still readable, explicitly marked legacy/unbounded):

    {"version": "2.3.0", "budget": "8 потоков из 10 ядер",
     "parts": [
       {"name": "Доменные правила", "dir": "backend", "base": "backend/stryker.config.mjs",
        "mutate": ["src/domain/booking.ts:40-72", "src/domain/slot.ts:10-31"], "concurrency": 4,
        "mutants": 412},
       {"name": "Защиты на базе · доля 1", "dir": "backend", "base": "backend/stryker.config.mjs",
        "mutate": ["src/guards/a.ts:1-80"], "concurrency": 1,
        "env": {"TEST_DATABASE_URL": "postgresql://…/app_test_mut_1", "S3_BUCKET": "app-test-mut-1"}},
       {"name": "Извлечение текста", "skip": "отдельный процесс — Stryker его не запускает"}]}

For each share it writes, under <git dir>/pipeline-work/<version>/mutation/:
  <slug>.stryker.mjs  the project's own config (`base`, imported) with: one `mutate` list (a repeated --mutate keeps
                      only the last), `inPlace: false` (an interrupted in-place run leaves instrumented files in src),
                      its own `tempDirName` and `incrementalFile` (two processes sharing them remove each other's
                      sandbox and overwrite each other's results), the reporters progress-append-only, clear-text and
                      json with the report in this folder, and its concurrency;
  parts.json          for pipeline/scripts/progress_mutation.py — names, ranges, workers, logs, dry-run counts;
and prints one command per share — its environment, `npx stryker run <config>`, the output to its log — to start in
the background, then the progress command. It refuses a share whose database is shared with another share or whose
database name has no «test». Standard library only.
"""
from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'pipeline' / 'scripts'))
from state_paths import contained_path, resolve_paths
import os


def ranges(values: object) -> dict[str, list[tuple[int, int]]]:
    if not isinstance(values, list):
        raise ValueError('risk ranges must be a list')
    result: dict[str, list[tuple[int, int]]] = {}
    for value in values:
        match = re.fullmatch(r'([^:]+):(\d+)-(\d+)', value) if isinstance(value, str) else None
        if not match or int(match[2]) <= 0 or int(match[3]) < int(match[2]):
            raise ValueError('expected file:positive-start-end range')
        path = Path(match[1])
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('risk range must be checkout-relative')
        result.setdefault(match[1], []).append((int(match[2]), int(match[3])))
    return result


def uncovered(required: list[str], executed: list[str]) -> list[str]:
    actual = ranges(executed)
    result = []
    for path, spans in ranges(required).items():
        for start, end in spans:
            cursor = start
            for left, right in sorted(actual.get(path, [])):
                if right < cursor or left > end:
                    continue
                if left > cursor:
                    result.append(f'{path}:{cursor}-{left - 1}')
                cursor = max(cursor, right + 1)
            if cursor <= end:
                result.append(f'{path}:{cursor}-{end}')
    return result


def validate(spec: dict) -> dict:
    """Validate the whole request before generating any files or commands."""
    if not isinstance(spec, dict) or not isinstance(spec.get('parts'), list) or not spec['parts']:
        raise ValueError('spec requires nonempty parts')
    if 'budget' in spec and not isinstance(spec['budget'], (dict, str)):
        raise ValueError('budget must be numeric bounds or a legacy descriptive string')
    bounded = isinstance(spec.get('budget'), dict) or 'risk_scope' in spec
    budget = spec.get('budget', {}) if bounded else {}
    risk = spec.get('risk_scope', {})
    if bounded:
        if not isinstance(budget, dict) or any(type(budget.get(k)) is not int or budget[k] <= 0
                                               for k in ('seconds', 'workers')):
            raise ValueError('budget requires positive integer seconds and workers')
        if not isinstance(risk, dict) or not risk.get('mandatory'):
            raise ValueError('risk_scope requires mandatory ranges')
        ranges(risk['mandatory'])
        ranges(risk.get('optional', []))
    used = spec.get('elapsed_seconds', 0)
    if type(used) is not int or used < 0:
        raise ValueError('elapsed_seconds must be a nonnegative integer')
    if 'runner_available' in spec and type(spec['runner_available']) is not bool:
        raise ValueError('runner_available must be boolean')
    for equivalent in spec.get('equivalent_mutants', []):
        if not isinstance(equivalent, dict) or any(not isinstance(equivalent.get(key), str) or not equivalent[key].strip()
                                                 for key in ('id', 'reason', 'evidence')):
            raise ValueError('equivalent mutant requires id, reason and evidence')
    executed, cancelled, dbs, workers = [], [], {}, 0
    for part in spec['parts']:
        if not isinstance(part, dict) or not isinstance(part.get('name'), str) or not part['name'].strip():
            raise ValueError('each part requires a name')
        scope = part.get('mutate', [])
        if bounded:
            ranges(scope)
            if uncovered(scope, risk['mandatory'] + risk.get('optional', [])):
                raise ValueError('mutate exceeds declared risk scope')
        status = part.get('status', 'planned')
        if status not in ('planned', 'incomplete', 'not-run', 'SKIPPED BY USER'):
            raise ValueError('invalid part status; generated configs cannot declare PASS')
        if status == 'SKIPPED BY USER':
            if part.get('user_cancelled') is not True or not isinstance(part.get('reason'), str) or not part['reason'].strip() or not scope:
                raise ValueError('SKIPPED BY USER requires explicit user_cancelled, reason and ranges')
            cancelled.extend(scope)
            continue
        if part.get('skip') or status in ('incomplete', 'not-run'):
            continue
        if not scope:
            raise ValueError('active part requires mutate ranges')
        concurrency = part.get('concurrency', 1)
        if type(concurrency) is not int or concurrency <= 0:
            raise ValueError('concurrency must be a positive integer')
        workers += concurrency
        executed.extend(scope)
        env = part.get('env') or {}
        if not isinstance(env, dict) or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key)
                                            or not isinstance(value, str) for key, value in env.items()):
            raise ValueError('invalid environment')
        url = env.get('TEST_DATABASE_URL', '')
        if url:
            name = urlparse(url).path.lstrip('/')
            identity = (urlparse(url).hostname, urlparse(url).port, name)
            if 'test' not in name.lower() or identity in dbs:
                raise ValueError('each active part requires its own test database')
            dbs[identity] = part['name']
    if bounded and workers > budget['workers']:
        raise ValueError('configured concurrency exceeds resource budget')
    exhausted = bounded and used >= budget['seconds']
    unavailable = spec.get('runner_available') is False
    missing = uncovered(risk.get('mandatory', []), executed + cancelled) if bounded else []
    if missing and not exhausted and not unavailable:
        raise ValueError('mandatory risk ranges omitted without explicit user cancellation: ' + ', '.join(missing))
    outstanding = uncovered(risk.get('mandatory', []), [] if exhausted or unavailable else executed) if bounded else []
    status = ('legacy/unbounded' if not bounded else 'incomplete' if exhausted else
              'not-run' if unavailable else 'SKIPPED BY USER' if cancelled else 'planned')
    return {'status': status, 'uncovered_ranges': outstanding,
            'reason': 'budget exhausted' if exhausted else 'runner unavailable' if unavailable else '',
            'next_action': 'Run required uncovered ranges within a renewed budget' if exhausted or unavailable else
                           'Run remaining gates; preserve explicit mutation cancellation' if cancelled else 'Run and evaluate mutation reports',
            'run': not (exhausted or unavailable)}


def slug(name: str, i: int) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower().encode("ascii", "ignore").decode()).strip("-")
    return f"{i:02d}-{s}" if s else f"{i:02d}-part"


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    policy = validate(spec)
    paths = resolve_paths(Path.cwd(), spec['version'], os.environ.get('CODEX_THREAD_ID', ''))
    root, version = paths.checkout, paths.version
    out = contained_path(paths.gitdir, paths.local / 'mutation')
    # Validate source/config paths before the first output directory is created.
    for part in spec['parts']:
        for key in ('dir', 'base'):
            if part.get(key):
                contained_path(root, root / part[key])
    out.mkdir(parents=True, exist_ok=True)
    dbs: dict[str, str] = {}
    parts, commands = [], []
    for i, p in enumerate(spec["parts"], 1):
        if p.get('status') == 'SKIPPED BY USER' or not policy['run'] or p.get('status') in ('incomplete', 'not-run'):
            status = p.get('status') if policy['run'] else policy['status']
            parts.append({'name': p['name'], 'skip': p.get('reason') or policy['reason'] or status,
                          'status': status, 'uncovered_ranges': p.get('mutate', [])})
            continue
        if p.get("skip"):
            parts.append({"name": p["name"], "skip": p["skip"]})
            continue
        url = (p.get("env") or {}).get("TEST_DATABASE_URL", "")
        if url:
            name = urlparse(url).path.lstrip("/").split("?")[0]
            if "test" not in name.lower():
                sys.exit(f"mutation_config: «{p['name']}» — в имени базы «{name}» нет «test»")
            if url in dbs:
                sys.exit(f"mutation_config: «{p['name']}» и «{dbs[url]}» на одной базе — у каждой доли своя "
                         "(health.md → In parallel, each stream with its own data)")
            dbs[url] = p["name"]
        if not p.get("mutate"):
            sys.exit(f"mutation_config: у «{p['name']}» нет диапазонов mutate")
        s = slug(p["name"], i)
        work = root / p.get("dir", ".")
        base = (root / p["base"]).resolve() if p.get("base") else None
        cfg = out / f"{s}.stryker.mjs"
        overrides = {
            "mutate": p["mutate"], "inPlace": False, "concurrency": int(p.get("concurrency", 1)),
            "tempDirName": str(out / f"{s}.tmp"), "incremental": True, "incrementalFile": str(out / f"{s}.incremental.json"),
            "reporters": ["progress-append-only", "clear-text", "json"],
            "jsonReporter": {"fileName": str(out / f"{s}.report.json")},
        }
        head = f"import base from {json.dumps(str(base))};\n" if base else "const base = {};\n"
        cfg.write_text("// generated by work/scripts/mutation_config.py — one share of a mutation run; do not edit\n"
                       + head + f"export default {{ ...base, ...{json.dumps(overrides, ensure_ascii=False, indent=2)} }};\n",
                       encoding="utf-8")
        log = out / f"{s}.log"
        env = " ".join(f"{k}={shlex.quote(v)}" for k, v in (p.get("env") or {}).items())
        commands.append(f"cd {shlex.quote(str(work))} && {env + ' ' if env else ''}npx stryker run "
                        f"{shlex.quote(str(cfg))} > {shlex.quote(str(log))} 2>&1")
        workers = f"{overrides['concurrency']} поток" + ("" if overrides["concurrency"] == 1 else "а" if overrides["concurrency"] < 5 else "ов")
        db = f" · база {urlparse(url).path.lstrip('/').split('?')[0]}" if url else ""
        parts.append({"name": p["name"], "scope": ", ".join(p["mutate"]), "workers": workers + db, "tool": "stryker",
                      "log": str(log), **({"mutants": p["mutants"]} if p.get("mutants") else {})})
    (out / "parts.json").write_text(json.dumps({"budget": spec.get("budget", ""), "parts": parts,
                                               'policy': policy, 'risk_scope': spec.get('risk_scope'),
                                               'equivalent_mutants': spec.get('equivalent_mutants', [])},
                                               ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"mutation_config: долей {len(commands)}, конфиги и parts.json — в {out}")
    print("Запустить каждую в фоне (run_in_background), все сразу:")
    for c in commands:
        print("  " + c)
    progress = Path(__file__).resolve().parents[2] / "pipeline" / "scripts" / "progress_mutation.py"
    page = root / "documentation" / "plans" / version / "progress-mutation.md"
    if page.parent.is_dir():   # the page exists before the first share starts
        subprocess.run([sys.executable, str(progress), str(page), str(out / "parts.json")], capture_output=True)
        print(f"Страница прогресса создана: {page.relative_to(root)} (ссылку в чат — progress_link.py)")
    print("Следить за прогоном — одна команда под Monitor, она сама обновляет страницу и заканчивается с последней долей:")
    print(f"  python3 {shlex.quote(str(progress))} {shlex.quote(str(page))} {shlex.quote(str(out / 'parts.json'))} --watch 120")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as exc:
        sys.exit(f'mutation_config: {exc}')
