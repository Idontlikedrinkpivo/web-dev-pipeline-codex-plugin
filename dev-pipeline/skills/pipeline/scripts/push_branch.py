"""Send final iteration documents: python3 push_branch.py [<project dir>].

Exit 0 confirms the exact full origin ref (or skips a non-iteration branch),
1 means reports/remote/build preconditions failed, 2 means rebase/recovery needs
attention, and 3 retains the document-form refusal. Exit 4 lists uncommitted documentation. Only the current iteration
ref is pushed, without force or tags. Recovery uses a local-only U2 checkpoint
before integrating a clean checkout. Uncommitted code stays in place.
"""
from __future__ import annotations

from contextlib import contextmanager
import shlex
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterator

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


def pending_docs(root: str, branch: str, given: Path) -> bool:
    """Refuse before remote work. Print a path-limited suggestion without touching the index."""
    from project_scope import project_root
    dirty = set()
    for command in (('diff', '--cached', '--name-only', '--no-renames'),
                    ('diff', '--name-only', '--no-renames'),
                    ('ls-files', '--others', '--exclude-standard')):
        dirty.update(path for path in names(root, *command, '-z')
                     if 'documentation' in Path(path).parts[:-1])
    if not dirty:
        return False
    print('push: незакоммиченные изменения в документации, отправка остановлена:')
    for path in sorted(dirty):
        print('  ' + shlex.quote(path))
    version = branch.split('/', 1)[1]
    try:
        project = project_root(given)
    except ValueError:
        # Multiple projects share this branch. Refuse the push without guessing an owner.
        return True
    folder = project.relative_to(root) / 'documentation' / 'plans' / version
    reports = [path for path in sorted(dirty) if Path(path).parent == folder
               and path.endswith('.md') and Path(path).name != 'sessions.md']
    if reports:
        paths = shlex.join(reports)
        print('Проверьте свои отчёты и укажите их пути в обеих командах:')
        print('git --literal-pathspecs add -- ' + paths)
        print('git --literal-pathspecs commit -m ' + shlex.quote('chore: отчёты итерации ' + version) + ' -- ' + paths)
    return True


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
                # If later replayed commits changed the generated site, the caller
                # lists the dirty documents. Their owner commits them explicitly.
                return 0, 'site rebuilt from final tree'
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


def verify_recovery(root: str, version: str, chat_key: str, journal: Path,
                  recovery: dict, manifest: dict) -> bool:
    """Verify the snapshot after a replay or an abort, before releasing its journal."""
    try:
        # Let U2 capture/compare the full raw inventory instead of duplicating it.
        actual = recovery_capture(root, version, chat_key)
        expected_site = recovery.get('regenerated_site', [])
        restored = [item for item in actual['inventory'] if item['path'] not in expected_site]
        if restored != manifest['inventory']:
            raise PushError('restored index/worktree inventory differs from the saved snapshot')
        if full_head(root) == recovery['head']:
            checkpoint.restore(root, version, chat_key, recovery['checkpoint_id'])
    except (PushError, checkpoint.CheckpointError, OSError, UnicodeError) as exc:
        write_recovery(journal, recovery, 'restore-verification-failed')
        print(f'push: recovery incomplete; preserve checkpoint and journal: {exc}')
        return False
    write_recovery(journal, recovery, 'restored')
    journal.unlink()
    return True


def integrate(root: str, branch: str, remote: str, chat_key: str, manifest: dict,
              journal: Path) -> bool:
    version = branch.split('/', 1)[1]
    paths = resolve_paths(root, version, chat_key)
    recovery = {'head': full_head(root), 'branch': branch, 'checkpoint_id': manifest['checkpoint_id'],
                'snapshot': str(paths.local / 'checkpoints' / manifest['checkpoint_id'])}
    code, out = git(root, 'status', '--porcelain=v1', '-z')
    if code or out:
        raise PushError('checkout changed before integration; local edits retained')
    write_recovery(journal, recovery, 'captured')
    code, out = git(root, 'fetch', '--no-tags', 'origin', 'refs/heads/' + branch)
    if code:
        recovered = verify_recovery(root, version, chat_key, journal, recovery, manifest)
        raise PushError('fetch failed' + ('; local changes restored: ' if recovered else '; recovery incomplete: ') + out.strip())
    fetched, fetched_oid = git(root, 'rev-parse', '--verify', 'FETCH_HEAD')
    if fetched or fetched_oid.strip() != remote:
        verify_recovery(root, version, chat_key, journal, recovery, manifest)
        raise PushError('remote moved between lookup and fetch; nothing sent')
    write_recovery(journal, recovery, 'rebase-started')
    code, out = rebase(root, remote)
    if code:
        if git_operation(root):
            aborted, abort_output = git(root, 'rebase', '--abort')
            if aborted or git_operation(root):
                write_recovery(journal, recovery, 'abort-failed')
                print('push: recovery incomplete; rebase abort failed; preserve metadata and snapshot: ' + abort_output.strip())
                return False
        if full_head(root) != recovery['head']:
            write_recovery(journal, recovery, 'rebase-finalize-failed')
            print('push: recovery incomplete; rebase changed HEAD before finalization failed; '
                  'preserve current tree, checkpoint and snapshot: ' + out.strip())
            return False
        restored = verify_recovery(root, version, chat_key, journal, recovery, manifest)
        print('push: rebase stopped; nothing sent; ' + ('local changes restored. ' if restored else 'recovery incomplete. ') + out.strip())
        return False
    if out == 'site rebuilt from final tree':
        recovery['regenerated_site'] = list(names(root, 'ls-files', '--modified', '--others', '--exclude-standard',
                                                  '-z', '--', 'documentation/_web-docs'))
    return verify_recovery(root, version, chat_key, journal, recovery, manifest)


def handoff(root: str, branch: str, version: str, chat_key: str, given: Path) -> int:
    paths = resolve_paths(root, version, chat_key)
    journal = contained_path(paths.gitdir, paths.gitdir / 'pipeline-work/push-recovery.json')
    if journal.exists():
        print(f'push: unresolved recovery journal; inspect {journal}; nothing sent')
        return 2
    if git_operation(root):
        print('push: existing Git operation; nothing sent and no rebase aborted')
        return 2
    if (paths.gitdir / 'index.lock').exists():
        raise PushError('Git index is locked; preserve its owner and retry later')
    if pending_docs(root, branch, given):
        return 4
    if git(root, 'remote', 'get-url', 'origin')[0]:
        raise PushError('origin is missing; handoff not performed')
    remote = remote_head(root, branch)
    if remote == full_head(root):
        print(f'push: already synchronized — {remote} in origin/{branch}')
        return 0
    if remote is not None and git(root, 'merge-base', '--is-ancestor', remote, 'HEAD')[0]:
        code, dirty = git(root, 'status', '--porcelain=v1', '-z')
        if code:
            raise PushError('cannot inspect checkout before integration')
        if dirty:
            # No fast-forward proof locally (the remote commit may be new to this clone).
            # Let an ordinary push decide, without ever stashing another writer's files.
            print('push: незакоммиченный код сохранён на месте; отправляю только HEAD без ребейза')
        elif not integrate(root, branch, remote, chat_key, recovery_capture(root, version, chat_key), journal):
            return 2
    if pending_docs(root, branch, given):
        return 4
    head = full_head(root)
    bad = form_problems(root, remote)
    if bad:
        print('push: nothing sent — document form errors (doc_check.py):\n' + bad)
        return 3
    if remote != head:
        code, out = git(root, 'push', '--porcelain', '--no-follow-tags', '-u', 'origin',
                        f'HEAD:refs/heads/{branch}')
        if code and ('non-fast-forward' in out or 'fetch first' in out):
            print('push: ветки разошлись; рабочие файлы на месте, ничего не отправлено')
            return 2
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
        given = Path(sys.argv[1] if len(sys.argv) > 1 else '.')
        root = str(checkout_root(given))
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
            return handoff(root, branch, version, chat_key, given)
    except (PushError, checkpoint.CheckpointError, OSError, UnicodeError, ValueError) as exc:
        print(f'push: nothing confirmed — {exc}')
        return 1


if __name__ == "__main__":
    sys.exit(main())
