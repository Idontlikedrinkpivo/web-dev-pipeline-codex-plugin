#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""What the plugin's command guard (hooks/guard.py) refused in a project, for reflect's «### Отказы хука».

    python3 guard_report.py <project dir> [--since YYYY-MM-DD[THH:MM]]

Reads ${CODEX_HOME:-~/.codex}/dev-pipeline-feedback/.guard/<project folder>.jsonl — one line per refusal, written by
the hook — and prints a block to paste unchanged: the count per rule and, for each rule, up to three distinct
commands it refused. Reflect reads those commands: a refusal of a command that was right is a finding on the hook
(its rule is too wide); a rule that fires again and again in one session is a finding on the skill that keeps
asking for that command. Standard library only.
"""
from __future__ import annotations

import collections
import json
import os
import sys
from pathlib import Path

from datetime import datetime, timezone

NAMES = {"commit-chained": "коммит склеен с проверкой", "commit-on-main": "коммит в main во время итерации",
         "merge-before-close": "слияние в main до закрытия итерации",
         "plan-unit-trailer": "Plan-Unit, который git не прочитает", "sed-i": "sed -i по-GNU",
         "progress-from-shell": "файл прогресса из оболочки", "wipe-shared-tree": "stash / reset / clean в общей папке",
         "edit-outside-worktree": "правка основной папки из worktree", "other": "другое"}


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def main() -> None:
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    project = Path(args[0]).resolve().name
    since = args[args.index("--since") + 1] if "--since" in args else ""
    start = timestamp(since) if since else None
    rows = []
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    f = home / "dev-pipeline-feedback" / ".guard" / f"{project}.jsonl"
    if f.exists():
        for number, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            try:
                r = json.loads(line)
                when = timestamp(r["ts"])
            except (ValueError, TypeError, KeyError) as exc:
                print(f"incomplete: {f}:{number}: invalid guard record ({exc})", file=sys.stderr)
                continue
            if start is None or when >= start:
                rows.append((when, r))
    rows = [r for _, r in sorted(rows, key=lambda item: item[0])]
    print("### Отказы хука")
    print()
    if not rows:
        print(f"Отказов нет{' с ' + since if since else ''}.")
        return
    by = collections.defaultdict(list)
    for r in rows:
        by[r.get("rule", "other")].append(r)
    print(f"Всего: {len(rows)} ({timestamp(rows[0]['ts']).date()} — {timestamp(rows[-1]['ts']).date()})")
    print()
    print("| Правило | Отказов | Примеры команд |")
    print("|---|---|---|")
    for rule, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        seen, examples = set(), []
        for r in rs:
            w = " ".join(r.get("what", "").split())[:110]
            if w and w not in seen:
                seen.add(w)
                examples.append(f"`{w.replace('|', '¦').replace('`', '')}`")
            if len(examples) == 3:
                break
        print(f"| {NAMES.get(rule, rule)} | {len(rs)} | {'<br>'.join(examples) or '—'} |")


if __name__ == "__main__":
    main()
