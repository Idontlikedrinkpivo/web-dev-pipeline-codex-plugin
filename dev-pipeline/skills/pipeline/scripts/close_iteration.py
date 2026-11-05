#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Where an iteration's close stands, step by step, in the order pipeline → End of the pipeline sets — so no step is
skipped and none runs out of order (a tag before the last stamp, a risk recorded after the tag).

    python3 close_iteration.py [<project dir>] [--version <v>]

One line per step, ✅ done or ✗ what is missing, in order:
  0 audit     security-audit.md says PASS, or the summary's «Безопасность» row has a verdict or «пропущен — <причина>»
              (the user's skip): the audit ran or was declined, not forgotten (ai-initiatives 2.2.0 went to the release
              without it; the owner's question found a P1)
  1 stamp     doc_state.py dirty returns zero (the latest valid stamp, including a no-row close)
  2 site      documentation/ (the site included) has nothing uncommitted
  3 summary   documentation/plans/<version>/summary.md exists
  3a UI       current full acceptance fingerprint or an explicit no-UI applicability reason
  4 tag       v<version> exists — and points at a commit that has steps 1–3a in it (never small mode)
  5 reflect   CODEX_HOME/dev-pipeline-feedback/<project>.md has contiguous complete exact windows of this version
              covering the final commit instant (the exclusive end must follow it)
  6 servers   no progress or documentation-site server of this project still running

The first ✗ is the next thing to do; a later step that is ✅ while an earlier one is ✗ is reported as out of order.
Exit 0 — all seven done; 2 — something left (the first ✗ says what). The version: --version, else the iteration branch.
Standard library only.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
import subprocess
import sys
import json
import importlib.util
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import where_am_i as w  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "reflect" / "scripts"))
import sessions  # noqa: E402
from open_iteration import iteration_metadata  # noqa: E402
from review_state import report_only_descendant  # noqa: E402


def stamp_gate(root: Path) -> tuple[bool, str]:
    script = HERE.parents[1] / "doc-versioning" / "scripts" / "doc_state.py"
    try:
        result = subprocess.run([sys.executable, str(script), str(root), "dirty"], capture_output=True, text=True)
        return result.returncode == 0, "" if result.returncode == 0 else (
            f"doc_state dirty exit {result.returncode}: " + (result.stdout + result.stderr).strip())
    except OSError as exc:
        return False, f"doc_state dirty unavailable: {exc}"


def small_gate(root: Path, metadata: dict) -> tuple[bool, str]:
    result = metadata.get("result")
    if not isinstance(result, dict):
        return False, "small result missing"
    if not isinstance(result.get("scope"), list) or not result["scope"] or not all(isinstance(p, str) and p.strip() for p in result["scope"]):
        return False, "small result needs scope + reviewed SHA"
    if any(Path(p).is_absolute() or '..' in Path(p).parts or not (root / p).resolve().is_relative_to(root.resolve()) for p in result['scope']):
        return False, "small result scope must stay in checkout"
    if git(root, "status", "--porcelain", "--", *result["scope"])[1]:
        return False, "small result scope has uncommitted changes after review"
    head = result.get('head')
    current_head, reason = report_only_descendant(root, head, version=metadata.get('version'), protected=tuple(result['scope']))
    if not current_head:
        return False, reason
    if not isinstance(result.get("affected_tests"), list) or not result["affected_tests"] or not all(str(x).strip() for x in result["affected_tests"]):
        return False, "small affected tests/evidence missing"
    for key in ("unit_review", "full_review"):
        review = result.get(key)
        if not isinstance(review, dict) or review.get("head") != head or review.get("status") != "PASS":
            return False, f"small {key} missing/stale"
    ui = result.get("ui", {})
    if ui.get("applicable") is False and not str(ui.get("reason") or "").strip():
        return False, "small no-UI needs a reason"
    if ui.get("applicable") not in (True, False):
        return False, "small UI applicability missing"
    return True, ""


def acceptance_gate(root: Path, folder: Path) -> tuple[bool, str]:
    script = HERE.parents[1] / "ui-test-cases" / "scripts" / "acceptance_scope.py"
    spec = importlib.util.spec_from_file_location("pipeline_acceptance_scope", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = folder / "ui-acceptance.json"
    try:
        return module.check(root, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return False, f"UI acceptance unavailable: {exc}"


def git(root: Path, *args: str) -> tuple[int, str]:
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return p.returncode, p.stdout.strip()


def alive(marker: Path) -> bool:
    try:
        pid = int(marker.read_text().split()[0])
        os.kill(pid, 0)
        return True
    except (OSError, ValueError, IndexError):
        return False


def main() -> None:
    args = sys.argv[1:]
    root = Path(next((a for a in args if not a.startswith("--") and Path(a).is_dir()), ".")).resolve()
    version = args[args.index("--version") + 1] if "--version" in args else None
    if not version:
        _, branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
        m = re.fullmatch(r"iteration/(\d+(?:\.\d+)*)", branch)
        version = m.group(1) if m else None
    if not version:
        print("close: версия не найдена — запустите на ветке iteration/<версия> или с --version")
        sys.exit(1)
    folder = root / "documentation" / "plans" / version
    steps: list[tuple[str, bool, str]] = []
    small = False
    marker = folder / "iteration.json"
    if marker.exists():
        try:
            metadata = iteration_metadata(marker, version)
            small = metadata["mode"] == "small"
            if small:
                ok, reason = small_gate(root, metadata)
                steps.append(("small результат", ok, reason))
        except ValueError as exc:
            steps.append(("iteration metadata", False, str(exc)))

    audit = folder / "security-audit.md"
    first = audit.read_text(encoding="utf-8", errors="replace").splitlines()[:1] if audit.exists() else []
    verdict = first[0] if first else ""
    row = re.search(r"^\| Безопасность \|[^|]*\|([^|]*)\|", (folder / "summary.md").read_text(encoding="utf-8")
                    if (folder / "summary.md").exists() else "", re.M)
    said = row.group(1).strip() if row else ""
    audited = ("PASS" in verdict and "заблокирован" not in verdict) or \
              bool(said) and ("PASS" in said or said.lower().startswith("пропущен"))
    steps.append(("0 аудит", audited, "" if audited else
                  f"аудит безопасности: {verdict.strip() or 'отчёта нет'} — проведите security-audit (или исправьте "
                  "находки), а если пользователь от него отказался, запишите в итоге строку «| Безопасность | … | "
                  "пропущен — <причина> |»"))

    stamped, stamp_reason = stamp_gate(root)
    steps.append(("1 штамп", stamped, stamp_reason))
    _, dirty = git(root, "status", "--porcelain", "--", "documentation", ":!documentation/plans")
    steps.append(("2 сайт", not dirty, f"не закоммичено в documentation/: {len(dirty.splitlines())} файл(ов) — "
                  "пересоберите сайт и закоммитьте" if dirty else ""))
    summary = folder / "summary.md"
    steps.append(("3 итог", summary.exists(), f"нет {summary.relative_to(root)} (pipeline → references/summary.md)"
                  if not summary.exists() else ""))
    accepted, acceptance_reason = acceptance_gate(root, folder)
    steps.append(("3a UI acceptance", accepted, acceptance_reason))
    code, tag_sha = git(root, "rev-list", "-n", "1", f"v{version}")
    tagged = code == 0 and bool(tag_sha)
    late = ""
    if tagged:
        _, after = git(root, "log", "--format=%s", f"v{version}..HEAD", "--", "documentation", ":!documentation/plans")
        if after:
            late = f"после метки ещё коммиты в документах ({len(after.splitlines())}) — метка не несёт их"
    steps.append(("4 метка", tagged and not late and not small,
                  "small mode prepares close; release requires normal workflow" if small else late or (f"нет метки v{version}" if not tagged else "")))
    _, last = git(root, "log", "-1", "--format=%ct", f"v{version}" if tagged else "HEAD")
    reflected, why = sessions.reflect_coverage(root, version, datetime.fromtimestamp(int(last), timezone.utc)) if last else (False, "HEAD unavailable")
    steps.append(("5 reflect", reflected, why))
    running = [m for m in (folder / ".progress-server", root / "documentation" / "_web-docs" / ".site-server")
               if m.exists() and alive(m)]
    steps.append(("6 серверы", not running, "работают: " + ", ".join(str(m.parent.relative_to(root)) for m in running)
                  if running else ""))

    first = next((i for i, (_, ok, _) in enumerate(steps) if not ok), None)
    for i, (name, ok, why) in enumerate(steps):
        mark = "✅" if ok else "✗"
        note = f" — {why}" if why else ""
        if ok and first is not None and i > first and name.startswith("4"):   # a reflect part may come early
            note = " — сделано раньше шага, который ещё не закрыт (порядок нарушен)"
        print(f"{mark} {name}{note}")
        if name == '3 итог':
            sys.path.insert(0, str(HERE.parents[1] / 'doc-versioning' / 'scripts'))
            from open_questions import pending_lines, scan
            for pending in pending_lines(scan(root)):
                print('  заметка к итогу: ' + pending)
    if first is None:
        print(f"close: итерация {version} закрыта")
        sys.exit(0)
    print(f"close: дальше — шаг «{steps[first][0]}»" + (" — метку ставить только после шагов 0–3" if first < 4 else ""))
    sys.exit(2)


if __name__ == "__main__":
    main()
