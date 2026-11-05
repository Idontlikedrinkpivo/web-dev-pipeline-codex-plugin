"""Rebuild the documentation site in the background after a document changes; wait for it before a commit.

    python3 rebuild.py <project dir> [--api]   # queue a rebuild (--api: the contract changed, rebuild its page)
    python3 rebuild.py <project dir> --api --force   # a build the user asked for: also a first site the hook
                                               # would not start (another repository, a declined site)
    python3 rebuild.py <project dir> --wait    # block until no rebuild runs or is queued
    python3 rebuild.py <project dir> --wait --report   # then print the last build's report (pages, ids, links)
    python3 rebuild.py <project dir> --if-outdated  # open-docs: wait, then build a missing site or rebuild one
                                               # another plugin version built; one line says which (exit 1: no
                                               # documentation/ at all)
    python3 rebuild.py <project dir> --for-rebase  # synchronous, offline, strict build; never starts a server

`docs-site` and `open-docs` build through this script, never by calling build_site.py beside a running worker: the
worker swaps the whole site folder in at the end of its build, so a second, parallel build loses its output or
its folder mid-write.

Called by the plugin's PostToolUse hook (hooks/site-rebuild.sh) on every edit under documentation/ — plans/ and the
site itself left out. A pipeline project without a site gets one at its first document (a full build, the API page
too) — not another repository that merely has a documentation/ folder, and not a project whose user declined the
site for good (`docs-site` in documentation/.dev-pipeline.json → skipped). One build
runs at a time: an edit during a build queues exactly one more, so a burst of edits costs two builds, not twenty.
Without --api the bundled contract is reused (bundling it takes seconds to minutes); with it, rebundled. State in <git dir>/pipeline-work/:
site-build.lock (the running worker's pid), site-build.pending (a queued rebuild, «api» when the contract
changed) and site-build.log (the last build's report). The site is swapped in whole at the end of a build, so a
reader never sees half of it.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def work_dir(root: Path, create: bool = True) -> Path:
    try:
        git = subprocess.run(["git", "-C", str(root), "rev-parse", "--git-dir"], capture_output=True, text=True,
                             timeout=10).stdout.strip()
    except Exception:
        git = ""
    base = (root / git) if git and not os.path.isabs(git) else Path(git) if git else root
    d = base.resolve() / "pipeline-work"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def running(lock: Path) -> bool:
    try:
        return alive(int(lock.read_text().split()[0]))
    except (OSError, ValueError, IndexError):
        return False


def wanted(root: Path) -> bool:
    """A first site only in a pipeline project (requirements, plans or the plugin stamp under documentation/) — the
    plugin is installed per user, and another repository's documentation/ is not its business — and not when the
    user declined the site for good (upgrade-docs → skip docs-site)."""
    doc = root / "documentation"
    if not any((doc / p).exists() for p in ("requirements", "plans", ".dev-pipeline.json")):
        return False
    try:
        return "docs-site" not in json.loads((doc / ".dev-pipeline.json").read_text()).get("skipped", [])
    except (OSError, ValueError, AttributeError):
        return True


def worker(root: Path, d: Path) -> int:
    lock, pending, log = d / "site-build.lock", d / "site-build.pending", d / "site-build.log"
    lock.write_text(str(os.getpid()))
    result = 0
    try:
        while pending.exists():
            api = pending.read_text().strip() == "api"
            pending.unlink()
            with open(log, "w", encoding="utf-8") as out:
                try:
                    built = subprocess.run([sys.executable, str(HERE / "build_site.py"), "--docs", str(root / "documentation"),
                                            "--out", str(root / "documentation" / "_web-docs")] + ([] if api else ["--keep-api"]),
                                           cwd=root, stdout=out, stderr=subprocess.STDOUT, timeout=600)
                    result = built.returncode
                except (OSError, subprocess.TimeoutExpired) as exc:
                    out.write(f'site: build did not finish: {exc}\n')
                    result = 1
            (d / 'site-build.result').write_text(str(result), encoding='utf-8')
    finally:
        lock.unlink(missing_ok=True) if sys.version_info >= (3, 8) else None
    return result


def wait(root: Path, d: Path) -> int:
    lock, pending = d / "site-build.lock", d / "site-build.pending"
    for _ in range(1200):  # up to 10 minutes: a contract rebuild bundles the spec
        if not running(lock):
            break  # idle — or queued with no worker: run it now, in the foreground
        time.sleep(0.5)
    if pending.exists() and not running(lock):
        return worker(root, d)
    if running(lock):
        print('site: build still running after wait timeout')
        return 1
    result = d / 'site-build.result'
    try:
        return int(result.read_text(encoding='utf-8')) if result.exists() else 0
    except (OSError, ValueError):
        return 1


def for_rebase(root: Path) -> int:
    """Build merged sources in the foreground; no queue, installs or server."""
    if not (HERE / 'build_site.py').is_file() or not (HERE / 'mdhtml.py').is_file():
        print('site: required builder or Markdown renderer is missing')
        return 1
    if not (root / 'documentation').is_dir():
        print('site: documentation/ is missing')
        return 1
    docs = root / 'documentation'
    scratch = docs / '._web-docs.building'
    if docs.resolve() != docs or (docs / '_web-docs').is_symlink() or scratch.exists() or (docs / '._web-docs.old').exists():
        print('site: symlinked output or existing build scratch requires inspection before rebase')
        return 1
    d = work_dir(root)
    lock = d / 'site-build.lock'
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print('site: another build owns the lock; rebase build refused')
        return 1
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(str(os.getpid()))
        if (d / 'site-build.pending').exists():
            print('site: a queued build must finish before rebase recovery')
            return 1
        try:
            result = subprocess.run([sys.executable, str(HERE / 'build_site.py'), '--docs',
                                     str(root / 'documentation'), '--out',
                                     str(root / 'documentation/_web-docs'), '--offline'],
                                    cwd=root, capture_output=True, text=True, timeout=600)
        except (OSError, subprocess.TimeoutExpired) as exc:
            if scratch.is_dir() and not scratch.is_symlink():
                shutil.rmtree(scratch)
            print(f'site: synchronous build did not finish: {exc}')
            return 1
        if result.returncode and scratch.is_dir() and not scratch.is_symlink():
            shutil.rmtree(scratch)
        print(result.stdout + result.stderr, end='')
        return result.returncode
    finally:
        lock.unlink()


def if_outdated(root: Path) -> int:
    """A missing site is built, one another plugin version built is rebuilt (a new version's site features — a back
    button, a new page — appear only after a rebuild); either way through the queue, and waited for."""
    doc = root / "documentation"
    if not doc.is_dir():
        print("site: documentation/ нет — показывать нечего")
        return 1
    d = work_dir(root)
    if wait(root, d):
        return 1
    sys.path.insert(0, str(HERE))
    from build_site import plugin_version  # noqa: E402 — only here: the builder's imports are not needed otherwise
    want = plugin_version()
    stamp = doc / "_web-docs" / "assets" / "plugin-version.txt"
    if not (doc / "_web-docs" / "index.html").exists():
        why = "собран сейчас"
    else:
        have = stamp.read_text(encoding="utf-8").strip() if stamp.exists() else ""
        if have == want:
            print(f"site: актуален (плагин {want or '?'})")
            return 0
        why = f"пересобран для плагина {want or '?'}" + (f" (был собран плагином {have})" if have else "")
    (d / "site-build.pending").write_text("api")
    if worker(root, d):
        print('site: rebuild failed; inspect site-build.log')
        return 1
    print(f"site: {why} — в git войдёт со следующим коммитом документов")
    return 0


def main() -> None:
    args = sys.argv[1:]
    root = Path(next((a for a in args if not a.startswith("--")), os.getcwd())).resolve()
    if '--for-rebase' in args:
        sys.exit(for_rebase(root))
    if "--if-outdated" in args:
        sys.exit(if_outdated(root))
    first = not (root / "documentation" / "_web-docs" / "index.html").exists()
    if first and "--wait" not in args and "--worker" not in args and "--force" not in args and not wanted(root):
        return  # no site, and this project is not the pipeline's or declined one
    d = work_dir(root, create="--wait" not in args)
    lock, pending = d / "site-build.lock", d / "site-build.pending"
    if "--wait" in args:
        result = wait(root, d)
        if "--report" in args:
            log = d / "site-build.log"
            print(log.read_text(encoding="utf-8").rstrip() if log.exists() else "no build has run yet")
        sys.exit(result)
    if "--worker" in args:
        sys.exit(worker(root, d))
    api = "--api" in args or first  # the first build makes the API page as well
    if api or not pending.exists() or pending.read_text().strip() != "api":
        pending.write_text("api" if api else "page")
    if not running(lock):
        proc = subprocess.Popen([sys.executable, __file__, str(root), "--worker"], stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, start_new_session=True, cwd=root)
        lock.write_text(str(proc.pid))  # at once, so the next edit queues instead of starting a second worker


if __name__ == "__main__":
    main()
