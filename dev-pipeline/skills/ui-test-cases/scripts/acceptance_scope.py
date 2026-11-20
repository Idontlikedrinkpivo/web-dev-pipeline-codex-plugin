"""Fingerprint UI acceptance without launching a browser or claiming a run.

select ROOT --base REF [--mapping FILE] --out FILE
record ROOT --manifest FILE --scope selected|full --status pass|blocked|not-run
       --evidence TEXT [--tool NAME --stand URL | --no-ui-reason REASON]
check ROOT --manifest FILE
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import subprocess
import stat
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'pipeline' / 'scripts'))
from review_state import report_only_descendant

sys.path.insert(0, str(Path(__file__).resolve().parent))
import case_impact
import code_reach


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if result.returncode:
        raise ValueError(result.stderr.decode(errors="replace").strip() or "git failed")
    return result.stdout.decode(errors="surrogateescape")


def contained(root: Path, value: str | Path) -> Path:
    path = Path(value)
    path = path if path.is_absolute() else root / path
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("acceptance paths must stay in checkout")
    return path


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def file_hash(path: Path) -> str | None:
    if path.is_symlink():
        return digest(["symlink", str(path.readlink())])
    return digest([stat.S_IMODE(path.stat().st_mode), hashlib.sha256(path.read_bytes()).hexdigest()]) if path.is_file() else None


def mapping_data(root: Path, mapping: str | None) -> dict:
    if not mapping:
        return case_impact.discover(root)
    data = json.loads(contained(root, mapping).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list) or not isinstance(data.get("changes", {}), dict):
        raise ValueError("invalid case mapping")
    ids = set()
    marked_by_file = {}
    for case in data["cases"]:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"] or case["id"] in ids:
            raise ValueError("invalid/duplicate case id")
        ids.add(case["id"])
        if not contained(root, case["path"]).is_file():
            raise ValueError("case file unavailable: " + str(case["path"]))
        if case["path"] not in marked_by_file:
            content = contained(root, case["path"]).read_text(errors="replace")
            marked_by_file[case["path"]] = {cid for cid, body in case_impact.blocks(content)
                                            if case_impact.CROSS_CUTTING.search(body)}
        if case["id"] in marked_by_file[case["path"]]:
            case["cross_cutting"] = True
        for key in ("screens", "operations"):
            if not isinstance(case.get(key, []), list) or any(not isinstance(x, str) for x in case.get(key, [])):
                raise ValueError("invalid case screen/operation mapping")
    failures = data.get("prior_failures", [])
    if not isinstance(failures, list) or any(x not in ids for x in failures):
        raise ValueError("prior failure missing from case universe")
    return data


def fingerprints(root: Path, mapping: str | None) -> tuple[dict, dict]:
    data = mapping_data(root, mapping)
    paths = set(git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard").split("\0")) - {""}
    # Reports and generated documentation are not application code. Cases and
    # the complete mapping are hashed separately, including newly added cases.
    cases = {c["path"] for c in data["cases"]}
    code = {p: file_hash(contained(root, p)) for p in sorted(paths)
            if p not in cases and not p.startswith(("documentation/plans/", "documentation/_web-docs/", ".git/"))}
    universe = {"mapping": data, "files": {p: file_hash(contained(root, p)) for p in sorted(cases)}}
    return {"code_tree": digest(code), "case_set": digest(universe)}, data


def select(root: Path, base: str, mapping: str | None, *, previous_failures=None, code_only=False) -> dict:
    base_sha, head = git(root, "rev-parse", base + "^{commit}").strip(), git(root, "rev-parse", "HEAD").strip()
    hashes, data = fingerprints(root, mapping)
    changed = set(git(root, "diff", "--relative", "--name-only", "-z", base_sha, "--", ".").split("\0")) - {""}
    changed.update(set(git(root, "ls-files", "-z", "--others", "--exclude-standard").split("\0")) - {""})
    selected, unmapped = {}, []
    def include(case_id, reason):
        selected.setdefault(case_id, []).append(reason)
    branch = git(root, 'rev-parse', '--abbrev-ref', 'HEAD').strip()
    iteration = re.fullmatch(r'iteration/(\d+\.\d+\.\d+)', branch)
    folder = root / 'documentation/plans' / iteration[1] if iteration else None
    plan = contained(root, folder / 'plan.md') if folder else None
    units = list(case_impact.plan_units(plan.read_text(), data['cases'])) if not mapping and plan and plan.is_file() else []
    report = contained(root, folder / 'test-run.md') if folder else None
    if previous_failures is None:
        previous_failures = case_impact.failures(report.read_text()) if not mapping and report and report.is_file() else []
    cases = data['cases']
    case_paths = {c['path'] for c in cases}
    app_changes = sorted(p for p in changed if not p.startswith("documentation/"))
    if code_only:
        units = [u for u in units if u[2].intersection(app_changes)]
    screens, shell, other = code_reach.split(root, app_changes)
    traced_code = set()
    for screen, paths in screens.items():
        for case in cases:
            if screen in case.get("screens", []):
                traced_code.update(paths)
                include(case["id"], f"код экрана {screen}: {', '.join(paths)}")
    named_ops = {op for case in cases for op in case.get("operations", [])}
    op_names = re.compile(r"[A-Za-z_][\w.-]*")
    for path in app_changes:
        if not named_ops or not path.endswith(code_reach.CODE) or code_reach.is_test(path):
            continue
        diff = git(root, "diff", "--no-ext-diff", "--no-textconv", "-U0", base_sha, "--", path)
        lines = (line[1:] for line in diff.splitlines() if line.startswith(("+", "-"))
                 and not line.startswith(("+++", "---")))
        touched = named_ops.intersection(op_names.findall("\n".join(lines)))
        for case in cases:
            hits = touched.intersection(case.get("operations", []))
            if hits:
                include(case["id"], f"операция в коде: {', '.join(sorted(hits))}")
                traced_code.add(path)
    smoke = [case for case in cases if case.get("cross_cutting")]
    if smoke:
        traced_code.update(shell)
        traced_code.update(other)
    for case in smoke:
        include(case["id"], "сквозной")
    for case in cases:
        if mapping and case["path"] in changed:
            include(case["id"], "added/changed case")
        if case["id"] in set(previous_failures) | set(data.get("prior_failures", [])):
            include(case["id"], "previous failure")
        for uid, ids, _ in units:
            overlap = ids.intersection(case['screens'] + case['operations'] + case['requirements'])
            if overlap:
                include(case['id'], f"plan {uid}: {', '.join(sorted(overlap))}")
    for path in sorted(changed):
        if path.startswith(("documentation/plans/", "documentation/_web-docs/")) or path == mapping:
            continue
        document = (path.startswith(('documentation/api/', 'documentation/requirements/srs/'))
                    or '/screen-specs/' in path or path.endswith('/frames-register.md'))
        if code_only and path.startswith("documentation/") and path not in case_paths:
            continue
        if not mapping and (document or path in case_paths):
            obj = f'{base_sha}:./{path}'
            before = git(root, 'show', obj) if subprocess.run(['git', '-C', str(root), 'cat-file', '-e', obj],
                                                               capture_output=True).returncode == 0 else ''
            file = contained(root, path)
            after = file.read_text(errors='replace') if file.is_file() else ''
            if path in case_paths:
                if before.partition('## TC-')[0] != after.partition('## TC-')[0]:
                    unmapped.append(path)  # shared prerequisites or setup changed
                old = dict(case_impact.blocks(before))
                for cid, body in case_impact.blocks(after):
                    if old.get(cid) != body:
                        include(cid, "added/changed case")
                continue
            dimension, ids = case_impact.identifiers(path, before, after)
            covered = set()
            for c in cases:
                overlap = ids.intersection(c.get(dimension, []))
                if overlap:
                    include(c['id'], f"{path}: {', '.join(sorted(overlap))}")
                    covered.update(overlap)
            if not ids or covered != ids:
                unmapped.append(path)
            continue
        if path in case_paths:
            continue
        if not mapping:
            file_units = [ids for _, ids, files in units if path in files]
            traced = {identifier for c in cases for field in ('screens', 'operations', 'requirements')
                      for identifier in c[field]}
            if file_units and all(ids and ids <= traced for ids in file_units):
                continue  # selection above already includes each case linked to these units
        matched = path in traced_code
        for dimension in ("screens", "operations"):
            rules = data.get("changes", {}).get(dimension, {})
            if not isinstance(rules, dict):
                raise ValueError("invalid change mapping")
            for pattern, identifiers in rules.items():
                if not isinstance(identifiers, list) or any(not isinstance(x, str) for x in identifiers):
                    raise ValueError("invalid mapped identifiers")
                if fnmatch.fnmatchcase(path, pattern):
                    covered = False
                    for case in data["cases"]:
                        overlap = set(case.get(dimension, [])) & set(identifiers)
                        if overlap:
                            include(case["id"], f"changed {dimension}: {path}: {','.join(sorted(overlap))}")
                            covered = True
                    matched = matched or covered
        if not matched:
            unmapped.append(path)
    if unmapped or data.get("unavailable"):
        for case in data["cases"]:
            include(case["id"], "conservative full set: uncertain mapping")
    return {"schema_version": 1, "base": base_sha, "head": head, "mapping": mapping,
            "version": iteration[1] if iteration else None,
            "fingerprints": hashes, "universe": sorted(c["id"] for c in data["cases"]),
            "code_only": code_only, "shell": shell, "outside_screens": other,
            "previous_failures": previous_failures, "selected": selected, "unmapped": unmapped,
            "blocked": data.get("unavailable"), "applicability": {"ui": True, "reason": None}, "runs": []}


def current(root: Path, manifest: dict, *, allow_dirty: bool = False) -> tuple[bool, str]:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        return False, "legacy/malformed acceptance manifest"
    try:
        hashes, data = fingerprints(root, manifest["mapping"])
        if hashes != manifest["fingerprints"]:
            return False, "code/case fingerprint changed"
        current_head, reason = report_only_descendant(root, manifest['head'], version=manifest.get('version'), allow_dirty=allow_dirty)
        if not current_head:
            return False, reason
        expected = select(root, manifest["base"], manifest["mapping"], previous_failures=manifest.get("previous_failures"),
                          code_only=manifest.get("code_only", False))
        if manifest.get("universe") != expected["universe"] or manifest.get("selected") != expected["selected"]:
            return False, "acceptance coverage/selection differs from current case universe"
        if manifest.get("blocked") != data.get("unavailable"):
            return False, "acceptance prerequisites differ"
        return True, "current"
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return False, f"invalid acceptance: {exc}"


def record(root: Path, manifest: dict, scope: str, status: str, evidence: str,
           tool: str | None = None, stand: str | None = None, no_ui_reason: str | None = None) -> dict:
    ok, reason = current(root, manifest, allow_dirty=True)
    if not ok:
        raise ValueError(reason)
    if not evidence.strip():
        raise ValueError("run evidence required")
    if no_ui_reason:
        if scope != "full" or not no_ui_reason.strip():
            raise ValueError("no-UI requires a full applicability decision with reason")
        manifest["applicability"] = {"ui": False, "reason": no_ui_reason.strip()}
    elif status == "pass" and (not tool or not stand or manifest.get("blocked") or not manifest["universe"]):
        raise ValueError("UI pass requires mapping, cases, tool, live stand and evidence")
    run = {"scope": scope, "status": status, "evidence": evidence, "tool": tool, "stand": stand,
           "fingerprints": manifest["fingerprints"], "head": manifest["head"],
           "cases": manifest["universe"] if scope == "full" else sorted(manifest["selected"])}
    if run not in manifest["runs"]:
        manifest["runs"].append(run)
    return manifest


def check(root: Path, manifest: dict, *, declined_reason: str | None = None) -> tuple[bool, str]:
    ok, reason = current(root, manifest)
    if not ok:
        return False, reason
    applicability = manifest.get("applicability", {})
    if applicability.get("ui") is False and not str(applicability.get("reason") or "").strip():
        return False, "no-UI applicability requires a reason"
    for run in reversed(manifest.get("runs", [])):
        if run.get("scope") != "full":
            continue
        matches = (run.get("fingerprints") == manifest["fingerprints"] and run.get("head") == manifest["head"]
                   and run.get("cases") == manifest.get("universe") and bool(str(run.get("evidence") or "").strip()))
        if declined_reason:
            if matches and run.get("status") == "not-run" and run.get("evidence") == declined_reason:
                return True, f"полный набор пропущен по решению пользователя — {declined_reason}"
            return False, "причина пропуска в test-run.md должна совпадать с текущей записью full/not-run"
        passed = matches and run.get("status") == "pass"
        if applicability.get("ui") is True:
            passed = passed and bool(run.get("tool") and run.get("stand") and manifest.get("universe") and not manifest.get("blocked"))
        elif applicability.get("ui") is not False:
            return False, "UI applicability unavailable"
        return bool(passed), "current full acceptance" if passed else "full acceptance blocked/not-run/incomplete"
    return False, "full acceptance not run"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["select", "record", "check"])
    parser.add_argument("root", type=Path)
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--mapping")
    parser.add_argument("--code-only", action="store_true", help="select a defect rerun from changed code")
    parser.add_argument("--out")
    parser.add_argument("--manifest")
    parser.add_argument("--scope", choices=["selected", "full"])
    parser.add_argument("--status", choices=["pass", "blocked", "not-run"])
    parser.add_argument("--evidence", default="")
    parser.add_argument("--tool")
    parser.add_argument("--stand")
    parser.add_argument("--no-ui-reason")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        target = contained(root, args.out if args.command == "select" else args.manifest)
        if args.command == "select":
            manifest = select(root, args.base, args.mapping, code_only=args.code_only)
        else:
            manifest = json.loads(target.read_text(encoding="utf-8"))
            if args.command == "check":
                ok, reason = check(root, manifest)
                print(json.dumps({"current": ok, "reason": reason}))
                raise SystemExit(0 if ok else 2)
            if not args.scope or not args.status:
                raise ValueError("record requires --scope and --status")
            manifest = record(root, manifest, args.scope, args.status, args.evidence, args.tool, args.stand, args.no_ui_reason)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(manifest))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"acceptance: {exc}\n")


if __name__ == "__main__":
    main()
