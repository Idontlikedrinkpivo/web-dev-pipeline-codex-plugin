"""Send final iteration documents: python3 push_branch.py [<project dir>].

Exit 0 confirms the exact full origin ref (or skips a non-iteration branch),
1 means reports/remote/build preconditions failed, 2 means rebase/recovery needs
attention, and 3 retains the document-form refusal. Only the current iteration
ref is pushed, without force or tags. Recovery uses a local-only U2 checkpoint
and a pinned exact stash object, never Git's implicit autostash.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterator, Literal

import checkpoint
from state_paths import checkout_root, contained_path, resolve_paths


OID = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z')
REPOSITORY_OVERRIDES = ('GIT_DIR', 'GIT_COMMON_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE',
                        'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES',
                        'GIT_NAMESPACE', 'GIT_CONFIG_PARAMETERS')


def git_environment() -> dict[str, str]:
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_EDITOR='true',
               GIT_SEQUENCE_EDITOR='true', GIT_OPTIONAL_LOCKS='0')
    for key in (*REPOSITORY_OVERRIDES, 'GIT_LITERAL_PATHSPECS',
                'GIT_GLOB_PATHSPECS', 'GIT_NOGLOB_PATHSPECS', 'GIT_ICASE_PATHSPECS'):
        env.pop(key, None)
    return env


def git(root: str, *args: str) -> tuple[int, str]:
    try:
        literal = ['--literal-pathspecs'] if '--' in args and args[0] in ('add', 'diff', 'ls-files') else []
        p = subprocess.run(['git', *literal, '-C', root, *args], capture_output=True, text=True,
                           errors='surrogateescape', env=git_environment(), timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, f'Git {args[0]} did not finish: {exc}'
    return p.returncode, p.stdout + p.stderr


def form_problems(root: str, upstream: str | None) -> str:
    """doc_check.py over the contract documents this push carries: a document with a broken form is not final."""
    base = upstream or next((b for b in ("origin/main", "main", "origin/master", "master")
                             if git(root, "rev-parse", "-q", "--verify", b)[0] == 0), None)
    if not base:
        return ""
    _, names = git(root, "diff", "--name-only", f"{base}...HEAD", "--", "documentation")
    docs = sorted({n for n in names.splitlines() if not n.startswith(("documentation/plans/", "documentation/_web-docs/"))})
    if not docs:
        return ""
    check = Path(__file__).resolve().parents[2] / "doc-versioning" / "scripts" / "doc_check.py"
    args = [sys.executable, str(check), root]
    for d in docs:
        args += ["--only", d]
    r = subprocess.run(args, capture_output=True, text=True)
    return "" if r.returncode == 0 else r.stdout.strip()


class PushError(ValueError):
    """A read/precondition failed; no success may be inferred from its output."""


def reject_repository_overrides() -> None:
    """Path discovery helpers also invoke Git; refuse redirection before them."""
    active = [key for key in REPOSITORY_OVERRIDES if key in os.environ]
    if os.environ.get('GIT_CONFIG_COUNT', '0') != '0':
        active.append('GIT_CONFIG_COUNT')
    if active:
        raise PushError('Git repository overrides are set: ' + ', '.join(active)
                        + '; unset them before explicit-checkout handoff')


def names(root: str, *args: str) -> tuple[str, ...]:
    code, out = git(root, *args)
    if code:
        raise PushError(out.strip() or f'Git {args[0]} failed')
    return tuple(name for name in out.split('\0') if name)


def portable_report(name: str, version: str) -> bool:
    prefix = f'documentation/plans/{version}/'
    if not name.startswith(prefix):
        return False
    tail = name[len(prefix):]
    # Immutable U2 payload patches/blobs are portable; legacy snapshots are not.
    if tail.startswith('checkpoints/'):
        return bool(re.fullmatch(r'checkpoints/[A-Za-z0-9][A-Za-z0-9_.-]{0,127}/'
                                 r'(?:manifest\.json|staged\.patch|unstaged\.patch|blobs/[0-9a-f]{64})', tail))
    path = Path(tail)
    return (not any(part.startswith('.') for part in path.parts)
            and path.name not in ('sessions.md', 'runtime.json')
            and path.suffix.lower() not in ('.html', '.png', '.jpg', '.jpeg', '.webm', '.patch')
            and not path.name.startswith(('snapshot', 'local-snapshot')))


def dirty_reports(root: str, branch: str) -> tuple[str, ...]:
    version = branch.split('/', 1)[1]
    scope = f'documentation/plans/{version}'
    result: set[str] = set()
    for args in (('diff', '--cached', '--name-only', '--no-renames', '-z', '--', scope),
                 ('diff', '--name-only', '--no-renames', '-z', '--', scope),
                 ('ls-files', '--others', '--exclude-standard', '-z', '--', scope)):
        result.update(name for name in names(root, *args) if portable_report(name, version))
    return tuple(sorted(result))


@dataclass(frozen=True, slots=True)
class ReportSave:
    status: Literal['clean', 'committed', 'failed']
    message: str


def report_preflight(root: str, branch: str) -> tuple[str, ...]:
    reports = dirty_reports(root, branch)
    if reports and names(root, 'diff', '--cached', '--name-only', '--no-renames', '-z'):
        raise PushError('unsaved iteration reports: index is occupied; preserve staged work and commit it first')
    return reports


def commit_reports(root: str, branch: str) -> ReportSave:
    """Stage exact current portable report paths; failures stop before remote work."""
    try:
        reports = report_preflight(root, branch)
        if not reports:
            return ReportSave('clean', 'iteration reports already saved')
        code, out = git(root, 'add', '--', *reports)
        if code:
            return ReportSave('failed', 'report add failed: ' + out.strip())
        staged = set(names(root, 'diff', '--cached', '--name-only', '--no-renames', '-z'))
        if staged != set(reports):
            return ReportSave('failed', 'report index changed; preserve it and inspect before retrying')
        code, out = git(root, 'commit', '-q', '-m', f'chore: отчёты итерации {branch.split("/", 1)[1]}')
        if code:
            return ReportSave('failed', 'report commit failed; staged reports retained: ' + out.strip())
        if dirty_reports(root, branch):
            return ReportSave('failed', 'mandatory reports changed during commit; nothing sent')
        return ReportSave('committed', 'iteration reports committed')
    except PushError as exc:
        return ReportSave('failed', str(exc))


def remote_head(root: str, branch: str) -> str | None:
    ref = 'refs/heads/' + branch
    code, destination = git(root, 'remote', 'get-url', '--push', '--all', 'origin')
    urls = destination.splitlines()
    if code or len(urls) != 1:
        raise PushError('origin must have one unambiguous push destination')
    code, out = git(root, 'ls-remote', '--exit-code', '--refs', '--', urls[0], ref)
    if code == 2 and not out.strip():
        return None
    if code:
        raise PushError('remote ref lookup failed: ' + out.strip())
    lines = out.splitlines()
    if len(lines) != 1:
        raise PushError('remote ref lookup was ambiguous')
    fields = lines[0].split('\t')
    if len(fields) != 2 or fields[1] != ref or not OID.fullmatch(fields[0]):
        raise PushError('remote ref lookup did not return the exact full branch OID')
    return fields[0]


def full_head(root: str) -> str:
    code, out = git(root, 'rev-parse', '--verify', 'HEAD')
    value = out.strip()
    if code or not OID.fullmatch(value):
        raise PushError('cannot resolve full local HEAD')
    return value


def git_operation(root: str) -> bool:
    code, out = git(root, 'rev-parse', '--absolute-git-dir')
    if code:
        raise PushError('cannot resolve checkout Git metadata')
    d = Path(out.strip())
    return any((d / name).exists() for name in ('rebase-merge', 'rebase-apply', 'MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD'))


def recovery_capture(root: str, version: str, chat_key: str) -> dict:
    plans = resolve_paths(root, version, chat_key).plans
    head = full_head(root)
    state = {'run_id': 'push-recovery', 'source_id': 'push-recovery', 'unit': 'handoff',
             'phase': 'final-checks', 'next_action': 'restore local changes and confirm exact remote ref',
             'review': {'base': head, 'head': head}, 'low_batches': [], 'findings': [], 'decisions': [],
             'reports': {name: (plans / name).read_text(encoding='utf-8') if (plans / name).exists() else ''
                         for name in checkpoint.REPORTS}}
    return checkpoint.capture(root, version, chat_key, state, [], local_only=True)


def write_recovery(journal: Path, data: dict, status: str) -> None:
    data['status'] = status
    temporary = journal.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2, ensure_ascii=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, journal)
    fd = os.open(journal.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def push_lock(gitdir: Path) -> Iterator[None]:
    folder = contained_path(gitdir, gitdir / 'pipeline-work')
    folder.mkdir(parents=True, exist_ok=True)
    lock = contained_path(gitdir, folder / 'push.lock')
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise PushError('another handoff owns push.lock; do not remove an unconfirmed owner') from exc
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(str(os.getpid()))
        identity = os.fstat(stream.fileno())
    try:
        yield
    finally:
        if lock.exists():
            actual = lock.lstat()
            if (actual.st_dev, actual.st_ino) == (identity.st_dev, identity.st_ino):
                lock.unlink()


def rebuild_site(root: str) -> tuple[int, str]:
    script = Path(__file__).resolve().parents[2] / 'docs-site/scripts/rebuild.py'
    try:
        result = subprocess.run([sys.executable, str(script), root, '--for-rebase'],
                                capture_output=True, text=True, timeout=660, env=git_environment())
        return result.returncode, result.stdout + result.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, f'site rebuild did not finish: {exc}'


def rebase(root: str, target: str) -> tuple[int, str]:
    code, out = git(root, '-c', 'rebase.autoStash=false', 'rebase', target)
    rebuilt = False
    for _ in range(100):  # bounded even if a hook/tool leaves an unexpected state
        if code == 0:
            if rebuilt:
                # Later commits in the todo can add sources after the conflict.
                # Render once from the final tree, never an intermediate replay.
                built, report = rebuild_site(root)
                if built:
                    return built, 'final merged site rebuild failed: ' + report
                added, report = git(root, 'add', '-A', '--', 'documentation/_web-docs')
                if added:
                    return added, report
                pending, report = git(root, 'diff', '--cached', '--quiet')
                if pending == 1:
                    return git(root, 'commit', '-q', '-m', 'chore: regenerate merged documentation site')
                if pending:
                    return pending, report
            return code, out
        clashes = names(root, 'diff', '--name-only', '--diff-filter=U', '-z')
        if not clashes or not all(name.startswith('documentation/_web-docs/') for name in clashes):
            return code, out
        built, report = rebuild_site(root)
        if built:
            return built, out + '\nsite rebuild failed: ' + report
        rebuilt = True
        # Resolve deletions as well as rebuilt files, confined to generated output.
        added, report = git(root, 'add', '-A', '--', 'documentation/_web-docs')
        if added:
            return added, report
        code, out = git(root, '-c', 'rebase.autoStash=false', 'rebase', '--continue')
    return 1, 'rebase exceeded the generated-conflict continuation limit'


def restore_stash(root: str, version: str, chat_key: str, journal: Path,
                  recovery: dict, manifest: dict) -> bool:
    """An uncertain apply is terminal. Retain the exact object and refuse retry."""
    stash = recovery.get('stash')
    if stash:
        write_recovery(journal, recovery, 'stash-restore-started')
        code, out = git(root, 'stash', 'apply', '--index', stash)
        if code:
            write_recovery(journal, recovery, 'stash-restore-failed')
            print('push: recovery incomplete; exact stash and checkpoint retained: ' + out.strip())
            return False
    try:
        # Let U2 capture/compare the full raw inventory instead of duplicating it.
        actual = recovery_capture(root, version, chat_key)
        if actual['inventory'] != manifest['inventory']:
            raise PushError('restored index/worktree inventory differs from the saved snapshot')
        if full_head(root) == recovery['head']:
            checkpoint.restore(root, version, chat_key, recovery['checkpoint_id'])
    except (PushError, checkpoint.CheckpointError, OSError, UnicodeError) as exc:
        write_recovery(journal, recovery, 'restore-verification-failed')
        print(f'push: recovery incomplete; preserve stash/checkpoint/journal: {exc}')
        return False
    write_recovery(journal, recovery, 'restored')
    if stash:
        # The private ref pins this exact object; never drop somebody else's stash.
        code, out = git(root, 'update-ref', '-d', recovery['stash_ref'], stash)
        if code:
            write_recovery(journal, recovery, 'stash-release-failed')
            print('push: recovery object release failed: ' + out.strip())
            return False
    journal.unlink()
    return True


def integrate(root: str, branch: str, remote: str, chat_key: str, manifest: dict,
              journal: Path) -> bool:
    version = branch.split('/', 1)[1]
    paths = resolve_paths(root, version, chat_key)
    recovery = {'head': full_head(root), 'branch': branch, 'checkpoint_id': manifest['checkpoint_id'],
                'snapshot': str(paths.local / 'checkpoints' / manifest['checkpoint_id']),
                'stash': None, 'stash_ref': 'refs/dev-pipeline/recovery/' + manifest['checkpoint_id']}
    write_recovery(journal, recovery, 'captured')
    code, out = git(root, 'status', '--porcelain=v1', '-z')
    if code:
        raise PushError('cannot inspect local work before stash: ' + out.strip())
    if out:
        before_stash = git(root, 'rev-parse', '--verify', 'refs/stash')[1].strip()
        write_recovery(journal, recovery, 'stash-started')
        code, out = git(root, 'stash', 'push', '--include-untracked', '-m', 'dev-pipeline ' + manifest['checkpoint_id'])
        if code:
            write_recovery(journal, recovery, 'stash-save-failed')
            raise PushError('stash save failed; inspect recovery journal: ' + out.strip())
        code, oid = git(root, 'rev-parse', '--verify', 'refs/stash')
        if code or not OID.fullmatch(oid.strip()) or oid.strip() == before_stash:
            write_recovery(journal, recovery, 'stash-identification-failed')
            raise PushError('cannot identify exact saved stash; preserve recovery state')
        recovery['stash'] = oid.strip()
        write_recovery(journal, recovery, 'stash-saved')
        code, out = git(root, 'update-ref', recovery['stash_ref'], recovery['stash'])
        if code:
            raise PushError('cannot pin stash object; inspect recovery journal: ' + out.strip())
        code, remaining = git(root, 'status', '--porcelain=v1', '-z')
        if code or remaining:
            write_recovery(journal, recovery, 'stash-cleanup-incomplete')
            raise PushError('stash did not clear captured work; preserve recovery objects, nothing sent')
    code, out = git(root, 'fetch', '--no-tags', 'origin', 'refs/heads/' + branch)
    if code:
        recovered = restore_stash(root, version, chat_key, journal, recovery, manifest)
        raise PushError('fetch failed' + ('; local changes restored: ' if recovered else '; recovery incomplete: ') + out.strip())
    fetched, fetched_oid = git(root, 'rev-parse', '--verify', 'FETCH_HEAD')
    if fetched or fetched_oid.strip() != remote:
        restore_stash(root, version, chat_key, journal, recovery, manifest)
        raise PushError('remote moved between lookup and fetch; nothing sent')
    write_recovery(journal, recovery, 'rebase-started')
    code, out = rebase(root, remote)
    if code:
        if git_operation(root):
            aborted, abort_output = git(root, 'rebase', '--abort')
            if aborted or git_operation(root):
                write_recovery(journal, recovery, 'abort-failed')
                print('push: recovery incomplete; rebase abort failed; preserve metadata, stash and snapshot: ' + abort_output.strip())
                return False
        if full_head(root) != recovery['head']:
            write_recovery(journal, recovery, 'rebase-finalize-failed')
            print('push: recovery incomplete; rebase changed HEAD before finalization failed; '
                  'preserve current tree, exact stash and snapshot: ' + out.strip())
            return False
        restored = restore_stash(root, version, chat_key, journal, recovery, manifest)
        print('push: rebase stopped; nothing sent; ' + ('local changes restored. ' if restored else 'recovery incomplete. ') + out.strip())
        return False
    return restore_stash(root, version, chat_key, journal, recovery, manifest)


def handoff(root: str, branch: str, version: str, chat_key: str) -> int:
    paths = resolve_paths(root, version, chat_key)
    journal = contained_path(paths.gitdir, paths.gitdir / 'pipeline-work/push-recovery.json')
    if journal.exists():
        print(f'push: unresolved recovery journal; inspect {journal}; nothing sent, stash not reapplied')
        return 2
    if git_operation(root):
        print('push: existing Git operation; nothing sent and no rebase aborted')
        return 2
    if (paths.gitdir / 'index.lock').exists():
        raise PushError('Git index is locked; preserve its owner and retry later')
    reports = report_preflight(root, branch)
    if git(root, 'remote', 'get-url', 'origin')[0]:
        raise PushError('origin is missing; handoff not performed')
    remote = remote_head(root, branch)
    if not reports and remote == full_head(root):
        print(f'push: already synchronized — {remote} in origin/{branch}')
        return 0
    manifest = recovery_capture(root, version, chat_key)
    saved = commit_reports(root, branch)
    if saved.status == 'failed':
        raise PushError(saved.message)
    if saved.status == 'committed':
        manifest = recovery_capture(root, version, chat_key)
    if remote is not None:
        if not integrate(root, branch, remote, chat_key, manifest, journal):
            return 2
    if dirty_reports(root, branch):
        raise PushError('mandatory reports remain unsaved; nothing sent')
    head = full_head(root)
    bad = form_problems(root, remote)
    if bad:
        print('push: nothing sent — document form errors (doc_check.py):\n' + bad)
        return 3
    if remote != head:
        code, out = git(root, 'push', '--porcelain', '--no-follow-tags', '-u', 'origin',
                        f'HEAD:refs/heads/{branch}')
        if code:
            raise PushError('not sent: ' + out.strip())
    confirmed = remote_head(root, branch)
    code, current_branch = git(root, 'rev-parse', '--abbrev-ref', 'HEAD')
    if code or current_branch.strip() != branch or full_head(root) != head or confirmed != head:
        raise PushError(f'unconfirmed remote ref: expected {head}, observed {confirmed or "missing"}')
    print(f'push: {"already synchronized" if remote == head else "sent"} — {head} in origin/{branch}')
    return 0


def main() -> int:
    try:
        reject_repository_overrides()
        root = str(checkout_root(sys.argv[1] if len(sys.argv) > 1 else '.'))
        if git_operation(root):
            print('push: existing Git operation; nothing sent and no rebase aborted')
            return 2
        code, branch = git(root, 'rev-parse', '--abbrev-ref', 'HEAD')
        branch = branch.strip()
        if code:
            raise PushError('cannot identify branch')
        if not branch.startswith('iteration/'):
            print(f'push: skipped branch {branch}; only iteration/<version> is sent')
            return 0
        version = branch.split('/', 1)[1]
        chat_key = os.environ.get('CODEX_THREAD_ID') or 'push-branch'
        paths = resolve_paths(root, version, chat_key)
        with push_lock(paths.gitdir):
            return handoff(root, branch, version, chat_key)
    except (PushError, checkpoint.CheckpointError, OSError, UnicodeError, ValueError) as exc:
        print(f'push: nothing confirmed — {exc}')
        return 1


if __name__ == "__main__":
    sys.exit(main())
