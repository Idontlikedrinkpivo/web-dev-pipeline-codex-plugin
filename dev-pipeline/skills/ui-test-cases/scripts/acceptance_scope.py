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
        return {"cases": [], "changes": {}, "prior_failures": [], "unavailable": "mapping unavailable"}
    data = json.loads(contained(root, mapping).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list) or not isinstance(data.get("changes", {}), dict):
        raise ValueError("invalid case mapping")
    ids = set()
    for case in data["cases"]:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"] or case["id"] in ids:
            raise ValueError("invalid/duplicate case id")
        ids.add(case["id"])
        if not contained(root, case["path"]).is_file():
            raise ValueError("case file unavailable: " + str(case["path"]))
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


def select(root: Path, base: str, mapping: str | None) -> dict:
    base_sha, head = git(root, "rev-parse", base + "^{commit}").strip(), git(root, "rev-parse", "HEAD").strip()
    hashes, data = fingerprints(root, mapping)
    changed = set(git(root, "diff", "--name-only", "-z", base_sha).split("\0")) - {""}
    changed.update(set(git(root, "ls-files", "-z", "--others", "--exclude-standard").split("\0")) - {""})
    selected, unmapped = {}, []
    def include(case_id, reason):
        selected.setdefault(case_id, []).append(reason)
    for case in data["cases"]:
        if case["path"] in changed:
            include(case["id"], "added/changed case")
        if case["id"] in data.get("prior_failures", []):
            include(case["id"], "previous failure")
    for path in sorted(changed):
        if path.startswith("documentation/plans/") or path == mapping or path in {c["path"] for c in data["cases"]}:
            continue
        matched = False
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
    branch = git(root, 'rev-parse', '--abbrev-ref', 'HEAD').strip()
    iteration = re.fullmatch(r'iteration/(\d+\.\d+\.\d+)', branch)
    return {"schema_version": 1, "base": base_sha, "head": head, "mapping": mapping,
            "version": iteration[1] if iteration else None,
            "fingerprints": hashes, "universe": sorted(c["id"] for c in data["cases"]),
            "selected": selected, "unmapped": unmapped,
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
        expected = select(root, manifest["base"], manifest["mapping"])
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


def check(root: Path, manifest: dict) -> tuple[bool, str]:
    ok, reason = current(root, manifest)
    if not ok:
        return False, reason
    applicability = manifest.get("applicability", {})
    if applicability.get("ui") is False and not str(applicability.get("reason") or "").strip():
        return False, "no-UI applicability requires a reason"
    for run in reversed(manifest.get("runs", [])):
        if run.get("scope") != "full":
            continue
        passed = (run.get("status") == "pass" and run.get("fingerprints") == manifest["fingerprints"]
                  and run.get("head") == manifest["head"] and run.get("cases") == manifest.get("universe")
                  and bool(str(run.get("evidence") or "").strip()))
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
            manifest = select(root, args.base, args.mapping)
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
