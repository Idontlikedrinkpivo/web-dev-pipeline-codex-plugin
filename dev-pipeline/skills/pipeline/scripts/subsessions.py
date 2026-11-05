#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The iteration's nested sessions, isolated by checkout and CODEX_THREAD_ID.

Stored in <absolute-git-dir>/pipeline-work/<version>/<chat-key>/sessions.md.
An explicit --legacy <sessions.md> copies identity-validated old local state;
the source is preserved and an existing local copy is never overwritten.

    python3 subsessions.py <project dir> <version> plan <stage>...
    python3 subsessions.py <project dir> <version> authorize [<stage>...]
    python3 subsessions.py <project dir> <version> set <row> <session id>
    python3 subsessions.py <project dir> <version> mark <row | session id> <state>
    python3 subsessions.py <project dir> <version> parent <session id>
    python3 subsessions.py <project dir> <version> show
    python3 subsessions.py <project dir> <version> whoami <session id>

plan    the stages kept for this iteration (keys below, any order) become rows in chain order, each with its title —
        «<version> · <its place in the chain, two digits> <word>», «1.0.0 · 02 SRS», so a sidebar sorted by name or
        by creation reads as the chain:
        one row per stage, and no parts: a stage over the context limit goes on in its own session, which the parent
        clears and starts again. A stage already in the list under an older title («прогон») is not added again.
        The fixes a check sends back (UI tests, the audit) run inside that check's own session, by agents. Rows already in
        the file keep their ids and states, so a later plan — a continued iteration, a stage added — only adds rows.
        A document stage whose documents all carry this version's stamp is closed and skipped, with a note: on a
        fresh clone (sessions.md is out of git: its ids are this machine's) the list holds only the stages left.
        These are proposals only. Replanning never grants or expands permission to create chats.
authorize records the user's explicit selected subset of proposed stages, in canonical order;
        replaces previous authorization, with no arguments revokes it. Historical rows are facts, not consent.
        Only authorized unopened rows are printed as ready to open. No command creates a chat.
set     an authorized row's session id, once opened (state → ждёт).
mark    a row's state: ждёт · идёт · закрыт · передан (handed over, to be cleared and started again) · убран.
parent  the parent's own session id, so a parent after a compaction or a new one on «продолжим» finds the list.
show    the table, then: the stage in work, the next one to start, the rows not opened yet — the input of «продолжим».
whoami  the row of a nested session by its own id: its stage and its skill — for a session after a compaction or a clear.

Stage keys, in chain order (pipeline → SKILL.md, the chain table): brd srs db api arch scaffold design specs cases
check plan work ui audit deploy ops ci close. Standard library only.
"""
from __future__ import annotations

import re
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from state_paths import StatePaths, contained_path, legacy_source, resolve_paths

try:
    import where_am_i as w  # the document registry and its stamps
except Exception:  # a broken neighbour must not break the list
    w = None

# key -> (title word, skill to run, a long stage — one that may hand over to a next part)
STAGES = {
    "brd": ("бизнес-требования", "brainstorm", False),
    "srs": ("SRS", "srs-writer", False),
    "db": ("схема БД", "db-schema-design", False),
    "api": ("API", "openapi-spec-generator", False),
    "arch": ("архитектура", "clean-architecture-design", False),
    "scaffold": ("каркас", "repo-scaffold", False),
    "design": ("макеты", "ui-design", True),
    "specs": ("ТЗ на экраны", "screen-spec", True),
    "cases": ("тест-кейсы", "ui-test-cases write", False),
    "check": ("сверка документов", "docs-consistency", False),
    "plan": ("план", "plan", False),
    "work": ("разработка", "work", True),   # «прогон» read as a test run; the user named it so
    "ui": ("UI-тесты", "ui-test-cases run", True),
    "audit": ("аудит безопасности", "security-audit", False),
    "deploy": ("релиз", "deploy-topology", False),
    "ops": ("эксплуатация", "operations-doc", False),
    "ci": ("CI", "ci-pipeline", False),
    "close": ("закрытие", "pipeline — End of the pipeline", False),
}
STATES = ("не открыта", "ждёт", "идёт", "закрыт", "передан", "убран")
HEAD = "| # | Подсессия | Этап | Навык | Когда | Id | Состояние |"
ROW = re.compile(r"^\|\s*(\d+)\s*\|(.*)\|(.*)\|(.*)\|(.*)\|(.*)\|(.*)\|\s*$")


def rows_for(version: str, key: str) -> list[dict]:
    word, skill, _ = STAGES[key]
    # the stage's place in the chain, two digits: a sidebar sorted by name keeps the chain order too («API» sorted
    # before «SRS», «архитектура» before «схема БД» — the user, 2026-11-04)
    n = list(STAGES).index(key) + 1
    return [dict(title=f"{version} · {n:02d} {word}", stage=key, skill=skill, when="по очереди")]


def parse(text: str) -> tuple[str, list[dict]]:
    lines = text.splitlines()
    parents = [match.group(1) for line in lines
               if (match := re.fullmatch(r"Родительская сессия:[ \t]*(.*)", line))]
    if len(parents) != 1 or not parents[0].strip():
        raise ValueError("sessions registry requires exactly one parent header")
    parent, rows = parents[0].strip(), []
    selections = [line.removeprefix('Authorized stages: ') for line in lines
                  if line.startswith('Authorized stages: ')]
    if len(selections) > 1:
        raise ValueError('duplicate authorization header')
    authorized = json.loads(selections[0]) if selections else []
    if not isinstance(authorized, list) or any(not isinstance(key, str) or key not in STAGES for key in authorized):
        raise ValueError('invalid authorized stage selection')
    for line in lines:
        m = ROW.match(line)
        if m:
            _, title, stage, skill, when, sid, state = (c.strip() for c in m.groups())
            rows.append(dict(title=title, stage=stage, skill=skill, when=when, id=sid.strip("`"), state=state,
                             authorized=stage in authorized))
    return parent, rows


def read(path: Path) -> tuple[str, list[dict]]:
    if not path.exists():
        return "", []
    return parse(path.read_text(encoding="utf-8"))


def write(path: Path, version: str, parent: str, rows: list[dict]) -> None:
    lines = [f"# Подсессии итерации {version}", "",
             "Ведёт родительская сессия; правит только `pipeline/scripts/subsessions.py` "
             "(pipeline → references/parent-session.md). В git не хранится.", "",
             f"Родительская сессия: {parent or '—'}",
             'Authorized stages: ' + json.dumps([key for key in STAGES if any(
                 r['stage'] == key and r.get('authorized') for r in rows)]),
             "", HEAD, "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        sid = f"`{r['id']}`" if r.get("id") else ""
        lines.append(f"| {i} | {r['title']} | {r['stage']} | {r['skill']} | {r['when']} | {sid} | "
                     f"{r.get('state') or 'не открыта'} |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def stamped(root: Path, version: str) -> set[str]:
    """Document stages closed in this iteration: every document of the stage carries the version's stamp."""
    if w is None:
        return set()
    by_stage: dict[int, list] = {}
    for d in w.registry(root):
        if d.path.is_file():
            by_stage.setdefault(d.stage, []).append(d.meta.get("version") == version)
    number = {1: "brd", 2: "srs", 3: "db", 4: "api", 5: "arch", 8: "specs"}
    return {number[n] for n, marks in by_stage.items() if n in number and marks and all(marks)}


def order_key(stage: str) -> int:
    keys = list(STAGES)
    return keys.index(stage.removesuffix("-fix")) if stage.removesuffix("-fix") in keys else len(keys)


def show(rows: list[dict]) -> None:
    for i, r in enumerate(rows, 1):
        print(f"{i:>2}. {r['title']} — {r.get('state') or 'не открыта'}" + (f" · {r['id']}" if r.get("id") else "")
              + ("" if r["when"] == "по очереди" else f" ({r['when']})"))
    busy = [r for r in rows if r.get("state") == "идёт"]
    nxt = next((r for r in rows if r.get("state") == "ждёт" and r["when"] == "по очереди"), None)
    unopened = [r for r in rows if r.get("state") in ("не открыта", "", None)
                and r["when"] == "по очереди" and r.get('authorized')]
    later = [r for r in rows if r.get("state") in ("не открыта", "", None) and r["when"] != "по очереди"]
    print()
    print("в работе: " + (", ".join(f"«{r['title']}» ({r['id']})" for r in busy) or "ничего"))
    print("дальше: " + (f"«{nxt['title']}» ({nxt['id']}) — отправить «начинай»" if nxt else "очередных нет"))
    if unopened:
        print("не открыты — открыть ВСЕ в этот ход пользователя, с этими названиями, без нового вопроса: " + "; ".join(
            f"{rows.index(r) + 1}. «{r['title']}»" for r in unopened))
    proposed = [r['stage'] for r in rows if not r.get('authorized') and not r.get('id')]
    if proposed:
        print('предложены, не разрешены — не открывать: ' + ' '.join(proposed))
    if later:   # a part from a list made before 1.2.256: a stage now goes on in its own session after a clear
        print("старые строки частей — не открывать, этап продолжается в своей подсессии (mark … убран): " + "; ".join(
            f"{rows.index(r) + 1}. «{r['title']}»" for r in later))


def migrate_legacy(paths: StatePaths, source: str, target: Path) -> None:
    """Copy only after both location and recorded parent prove local identity."""
    old = legacy_source(paths, source)
    payload = old.read_bytes()
    parent, _ = parse(payload.decode("utf-8"))
    if parent != paths.chat_key:
        raise ValueError("legacy sessions parent does not match this chat; no state copied")
    target.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation preserves state changed after an earlier migration.
    try:
        with target.open("xb") as copied:
            copied.write(payload)
    except FileExistsError:
        return


def owner_of(paths: StatePaths, child: str) -> tuple[str, dict] | None:
    """Read-only self lookup in identity-proven owner registries of this checkout.

    The unique parent header must reproduce the registry's exact hashed namespace
    through the resolver. A child row alone is never proof of an owning parent.
    """
    if child != paths.chat_key or not paths.local.parent.exists():
        return None
    matches = []
    for folder in sorted(paths.local.parent.iterdir()):
        try:
            source = contained_path(paths.gitdir, folder / "sessions.md")
            if not source.is_file():
                continue
            parent, rows = read(source)
            owner = resolve_paths(paths.checkout, paths.version, parent)
            if source != owner.local / "sessions.md":
                continue
        except ValueError:
            continue  # invalid/unproven namespaces cannot establish ownership
        hits = [row for row in rows if row.get("id") == child]
        if len(hits) > 1:
            raise ValueError("ambiguous child membership in parent registry")
        if hits:
            matches.append((parent, hits[0]))
    if len(matches) > 1:
        raise ValueError("ambiguous parent registries for this child session")
    return matches[0] if matches else None


def main() -> None:
    raw = sys.argv[1:]
    legacy = None
    if "--legacy" in raw:
        index = raw.index("--legacy")
        if index + 1 >= len(raw) or raw.count("--legacy") != 1:
            sys.exit("sessions: --legacy requires one explicit source path")
        legacy = raw[index + 1]
        raw = raw[:index] + raw[index + 2:]
    args = [a for a in raw if not a.startswith("--")]
    if len(args) < 3:
        sys.exit(__doc__)
    version, cmd, rest = args[1], args[2], args[3:]
    try:
        paths = resolve_paths(args[0], version, os.environ.get("CODEX_THREAD_ID", ""))
        root = paths.checkout
        path = contained_path(paths.gitdir, paths.local / "sessions.md")
        if legacy is not None:
            migrate_legacy(paths, legacy, path)
        parent, rows = read(path)
        if parent not in ('', '—', paths.chat_key):
            raise ValueError('registry parent does not match current chat')
    except (ValueError, OSError) as exc:
        sys.exit(f"sessions: {exc}")

    if cmd == "plan":
        bad = [k for k in rest if k not in STAGES]
        if bad or not rest:
            sys.exit(f"sessions: неизвестные этапы {bad} — ключи: {' '.join(STAGES)}")
        have = {r["title"] for r in rows}
        done = stamped(root, version) - {r["stage"] for r in rows}
        for key in sorted(done & set(rest), key=list(STAGES).index):
            print(f"sessions: «{STAGES[key][0]}» уже закрыт в {version} (документы со штампом) — подсессия не нужна")
        for key in sorted(set(rest) - done, key=list(STAGES).index):
            staged = {r["stage"] for r in rows if " · часть " not in r["title"]}   # an older title of the stage counts
            for r in rows_for(version, key):
                if r["title"] not in have and key not in staged:
                    rows.append(dict(r, id="", state="не открыта"))
        rows.sort(key=lambda r: order_key(r["stage"]))   # stable: a part stays after its stage
        write(path, version, parent if parent and parent != "—" else paths.chat_key, rows)
        show(rows)
    elif cmd == 'authorize':
        proposed = {r['stage'] for r in rows}
        if any(key not in STAGES or key not in proposed for key in rest):
            sys.exit('sessions: authorize accepts only previously proposed stage keys')
        for row in rows:
            row['authorized'] = row['stage'] in rest
        write(path, version, paths.chat_key, rows)
        show(rows)
    elif cmd == "set" and len(rest) == 2 and rest[0].isdigit() and 0 < int(rest[0]) <= len(rows):
        r = rows[int(rest[0]) - 1]
        if not r.get('authorized'):
            sys.exit('sessions: stage not explicitly authorized; record user selection with authorize')
        if r.get('id') and r['id'] != rest[1]:
            sys.exit('sessions: row already belongs to another session')
        if rest[1] in (row.get('id') for row in rows if row is not r):
            sys.exit('sessions: duplicate child session identity')
        r["id"], r["state"] = rest[1], "ждёт"
        write(path, version, parent if parent and parent != "—" else paths.chat_key, rows)
        print(f"sessions: {rest[0]}. «{r['title']}» — {rest[1]}, ждёт")
    elif cmd == "mark" and len(rest) == 2 and rest[1] in STATES:
        hit = [r for i, r in enumerate(rows, 1) if rest[0] in (str(i), r.get("id"))]
        if not hit:
            sys.exit(f"sessions: строки «{rest[0]}» нет — subsessions.py … show")
        if rest[1] in ('ждёт', 'идёт', 'передан') and not hit[0].get('id'):
            sys.exit('sessions: cannot activate an unopened row')
        hit[0]["state"] = rest[1]
        write(path, version, parent if parent and parent != "—" else paths.chat_key, rows)
        print(f"sessions: «{hit[0]['title']}» — {rest[1]}")
    elif cmd == "parent" and len(rest) == 1:
        if rest[0] != paths.chat_key:
            sys.exit('sessions: parent must match current chat identity')
        write(path, version, rest[0], rows)
        print(f"sessions: родительская сессия — {rest[0]}")
    elif cmd == "show":
        if not rows:
            sys.exit(f"sessions: списка нет ({path}) — составьте: subsessions.py … plan <этапы>; "
                     "для старого файла укажите --legacy <sessions.md> (нужна идентичность checkout/чата)")
        print(f"Родительская сессия: {parent or '—'}")
        show(rows)
    elif cmd == "whoami" and len(rest) == 1:
        hits = [r for r in rows if r.get("id") == rest[0]]
        if len(hits) > 1:
            sys.exit("sessions: ambiguous child membership in local registry")
        hit = hits[0] if hits else None
        try:
            owner = owner_of(paths, rest[0])
        except (ValueError, OSError) as exc:
            sys.exit(f"sessions: {exc}")
        if owner is not None:
            parent, hit = owner
        if not hit:
            sys.exit(f"sessions: сессии {rest[0]} в списке нет — спросите родительскую ({parent or 'id неизвестен'})")
        print(f"ты — «{hit['title']}»: этап {hit['stage']}, навык {hit['skill']}, {hit['when']}, состояние "
              f"{hit['state']}; родительская сессия — {parent or '—'}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
