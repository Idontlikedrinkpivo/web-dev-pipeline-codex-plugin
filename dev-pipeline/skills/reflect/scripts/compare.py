#!/usr/bin/env python3
"""Compare two variants (the plugin before and after a change) over several runs of the same tasks.

usage:
  compare.py --metric <name> [--metric <name> ...]
             --task <name> --base <a.json> <b.json> ... --variant <x.json> <y.json> ...
             [--task <name> --base ... --variant ...]

Each json is one run's figures from `measure.py … --json` (one run = one `work` over the same plan, or one stage
over the same input). For each metric and task: the median of the base runs and of the variant runs, and their
ratio; over all tasks, the geometric mean of those ratios with a 95% interval from a bootstrap that resamples the
runs of each task. A change is real only when the interval stays on one side of 1.00 — inside it, the runs did
not tell the variants apart. Metrics: total, session, session_peak, calls, executors_over_250k, per_accepted_unit,
first_review_share, or any group name («Исполнители», «Ревью кода», …). Lower is better except first_review_share.
Standard library only (method: reflect/references/comparing.md).
"""
from __future__ import annotations

import json
import math
import random
import statistics
import sys
from pathlib import Path


def value(run: dict, metric: str) -> float | None:
    v = run.get(metric)
    if v is None:
        v = (run.get("groups") or {}).get(metric)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def comparison_status(runs: list[dict]) -> tuple[bool, str]:
    if any(r.get("schema_version") != 2 for r in runs):
        return False, "legacy reports: provenance/acceptance unknown"
    if any(r.get("complete") is not True for r in runs):
        return False, "incomplete telemetry"
    for key in ("window", "baseline", "unit_kind"):
        if any(r.get(key) != runs[0].get(key) for r in runs[1:]):
            return False, f"unequal {key}"
    if not runs[0].get("baseline") or not all((runs[0].get("window") or {}).get(k) for k in ("start", "end")):
        return False, "window/baseline provenance unknown"
    return True, "comparable"


def parse(args: list) -> tuple[list, list]:
    metrics, tasks, cur, slot = [], [], None, None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--metric":
            metrics.append(args[i + 1])
            i += 2
            continue
        if a == "--task":
            cur = {"name": args[i + 1], "base": [], "variant": []}
            tasks.append(cur)
            i += 2
            continue
        if a in ("--base", "--variant"):
            slot = a[2:]
        elif cur is not None and slot:
            cur[slot].append(json.loads(Path(a).read_text(encoding="utf-8")))
        i += 1
    return metrics, tasks


def ratio(base: list, variant: list) -> float | None:
    if not base or not variant:
        return None
    b, v = statistics.median(base), statistics.median(variant)
    return v / b if b > 0 and v >= 0 else None


def main() -> None:
    metrics, tasks = parse(sys.argv[1:])
    if not metrics or not tasks or any(not t["base"] or not t["variant"] for t in tasks):
        sys.exit(__doc__)
    rnd = random.Random(7)
    print("| Показатель | Задача | База, медиана (прогонов) | Вариант, медиана (прогонов) | Вариант / база |")
    print("|---|---|---|---|---|")
    summary = []
    for m in metrics:
        per_task = []
        for t in tasks:
            comparable, reason = comparison_status(t["base"] + t["variant"])
            if not comparable:
                print(f"| {m} | {t['name']} | incomplete comparison | {reason} | — |")
                continue
            b = [x for x in (value(r, m) for r in t["base"]) if x is not None]
            v = [x for x in (value(r, m) for r in t["variant"]) if x is not None]
            r = ratio(b, v)
            per_task.append((b, v))
            print(f"| {m} | {t['name']} | {statistics.median(b) if b else '—':.4g} ({len(b)}) | "
                  f"{statistics.median(v) if v else '—':.4g} ({len(v)}) | {r:.2f} |" if r is not None else
                  f"| {m} | {t['name']} | нет данных | нет данных | — |")
        ok = [(b, v) for b, v in per_task if ratio(b, v)]
        if not ok:
            summary.append(f"- {m}: нет данных")
            continue
        point = math.exp(statistics.mean(math.log(ratio(b, v)) for b, v in ok))
        boots = []
        for _ in range(2000):
            logs = []
            for b, v in ok:
                rb = [rnd.choice(b) for _ in b]
                rv = [rnd.choice(v) for _ in v]
                r = ratio(rb, rv)
                if r:
                    logs.append(math.log(r))
            if logs:
                boots.append(math.exp(statistics.mean(logs)))
        boots.sort()
        lo, hi = boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots)) - 1]
        better_up = m == "first_review_share"
        if hi < 1:
            verdict = "лучше" if not better_up else "хуже"
        elif lo > 1:
            verdict = "хуже" if not better_up else "лучше"
        else:
            verdict = "разницы не видно"
        runs = min(min(len(b), len(v)) for b, v in ok)
        note = " · прогонов меньше 3 на вариант — интервал ненадёжен" if runs < 3 else ""
        summary.append(f"- {m}: вариант / база = {point:.2f} [{lo:.2f}..{hi:.2f}] — {verdict}{note}")
    print("\nИтог (среднее геометрическое по задачам, 95% интервал):")
    print("\n".join(summary))


if __name__ == "__main__":
    main()
