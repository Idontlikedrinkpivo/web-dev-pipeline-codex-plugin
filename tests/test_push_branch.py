"""Handoff safety against temporary local bare origins; no external remotes."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'dev-pipeline/skills/pipeline/scripts'
VERSION = '1.3.0'
BRANCH = 'iteration/' + VERSION
sys.dont_write_bytecode = True


class GitFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        # Ignore the real user's aliases, hooks, credentials and Git overrides.
        env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
        env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                   GIT_TERMINAL_PROMPT='0', GIT_ALLOW_PROTOCOL='file',
                   PYTHONDONTWRITEBYTECODE='1', CODEX_THREAD_ID='git-test')
        self.environment = patch.dict(os.environ, env, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.origin = self.base / 'origin.git'
        self.repo = self.base / 'one'
        self.repo.mkdir()
        self.git(self.repo, 'init', '-q', '-b', BRANCH)
        self.configure(self.repo)
        self.plans = self.repo / 'documentation/plans' / VERSION
        self.plans.mkdir(parents=True)
        for name in ('plan.md', 'progress.md', 'work-run.md', 'resume.md', 'context-handover.md'):
            (self.plans / name).write_text('# Fixture\n', encoding='utf-8')
        (self.repo / 'binary.bin').write_bytes(b'\x00base\xff')
        (self.repo / 'other.bin').write_bytes(b'\x00other\xff')
        self.git(self.repo, 'add', '.')
        self.git(self.repo, 'commit', '-qm', 'fixture')
        self.git(self.repo, 'init', '-q', '--bare', str(self.origin))
        self.git(self.repo, 'remote', 'add', 'origin', str(self.origin))
        self.git(self.repo, 'push', '-qu', 'origin', BRANCH)
        self.initial = self.oid(self.repo)
        sys.path.insert(0, str(SCRIPTS))
        self.addCleanup(sys.path.remove, str(SCRIPTS))
        spec = importlib.util.spec_from_file_location('git_batch_push', SCRIPTS / 'push_branch.py')
        assert spec is not None and spec.loader is not None
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.module
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(self.module)

    def configure(self, repo: Path) -> None:
        self.git(repo, 'config', 'user.name', 'Fixture')
        self.git(repo, 'config', 'user.email', 'fixture@example.invalid')
        self.git(repo, 'config', 'core.autocrlf', 'false')

    def git(self, repo: Path, *args: str, check: bool = True) -> bytes:
        return subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                              check=check, timeout=20).stdout

    def oid(self, repo: Path) -> str:
        return self.git(repo, 'rev-parse', 'HEAD').decode().strip()

    def remote_oid(self) -> str:
        return self.git(self.origin, 'rev-parse', 'refs/heads/' + BRANCH).decode().strip()

    def run_push(self) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(sys, 'argv', ['push_branch.py', str(self.repo)]):
            try:
                result = self.module.main()
            except SystemExit as exc:
                return int(exc.code or 0), output.getvalue()
        return int(result or 0), output.getvalue()

    def commit(self, repo: Path, *paths: str) -> None:
        self.git(repo, 'add', '--', *paths)
        self.git(repo, 'commit', '-qm', 'fixture change')

    def peer(self) -> Path:
        peer = self.base / 'peer'
        self.git(self.repo, 'clone', '-q', '-b', BRANCH, str(self.origin), str(peer))
        self.configure(peer)
        return peer

    def index_bytes(self) -> bytes:
        gitdir = self.git(self.repo, 'rev-parse', '--absolute-git-dir').decode().strip()
        return (Path(gitdir) / 'index').read_bytes()


class PushReports(GitFixture):
    def test_git_environment_redirection_refuses_before_discovery_and_preserves_both_checkouts(self) -> None:
        peer = self.peer()
        (self.plans / 'progress.md').write_bytes(b'requested report\n')
        (peer / 'documentation/plans/1.3.0/progress.md').write_bytes(b'peer report\n')
        (peer / 'binary.bin').write_bytes(b'\x00peer bytes\xff')

        def inventory(repo: Path) -> dict:
            return {'head': self.oid(repo), 'index': (repo / '.git/index').read_bytes(),
                    'files': {str(path.relative_to(repo)): path.read_bytes()
                              for path in repo.rglob('*') if path.is_file()
                              and '.git' not in path.relative_to(repo).parts}}

        before = {repo: inventory(repo) for repo in (self.repo, peer)}
        refs = self.git(self.origin, 'show-ref')
        overrides = [
            {'GIT_DIR': str(peer / '.git'), 'GIT_WORK_TREE': str(peer)},
            {'GIT_DIR': str(peer / '.git')},
            {'GIT_WORK_TREE': str(peer)},
            {'GIT_COMMON_DIR': str(peer / '.git')},
            {'GIT_INDEX_FILE': str(peer / '.git/index')},
            {'GIT_OBJECT_DIRECTORY': str(peer / '.git/objects')},
            {'GIT_ALTERNATE_OBJECT_DIRECTORIES': str(peer / '.git/objects')},
            {'GIT_NAMESPACE': 'peer-namespace'},
            {'GIT_CONFIG_PARAMETERS': f"'core.worktree={peer}'"},
            {'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.worktree',
             'GIT_CONFIG_VALUE_0': str(peer)},
        ]
        for override in overrides:
            with self.subTest(override=tuple(override)):
                result = subprocess.run([sys.executable, str(SCRIPTS / 'push_branch.py'), str(self.repo)],
                                        env=dict(os.environ, **override), capture_output=True,
                                        text=True, timeout=20)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('Git repository overrides', result.stdout)
                self.assertEqual({repo: inventory(repo) for repo in (self.repo, peer)}, before)
                self.assertEqual(self.git(self.origin, 'show-ref'), refs)
                self.assertFalse((self.repo / '.git/pipeline-work').exists())
                self.assertFalse((peer / '.git/pipeline-work').exists())

    def test_foreign_staged_and_dirty_report_refuses_before_remote_and_keeps_index(self) -> None:
        (self.repo / 'binary.bin').write_bytes(b'\x00staged\xfe')
        self.git(self.repo, 'add', 'binary.bin')
        (self.plans / 'progress.md').write_text('unfinished report\n', encoding='utf-8')
        before = self.index_bytes()
        code, output = self.run_push()
        self.assertNotEqual(code, 0, output)
        self.assertEqual(self.index_bytes(), before)
        self.assertEqual(self.remote_oid(), self.initial)
        self.assertEqual(self.oid(self.repo), self.initial)

    def test_report_commit_hook_failure_stops_before_fetch_and_preserves_staged_report(self) -> None:
        (self.plans / 'progress.md').write_text('dirty report\n', encoding='utf-8')
        hook = self.repo / '.git/hooks/pre-commit'
        hook.write_text('#!/bin/sh\nexit 1\n', encoding='utf-8')
        hook.chmod(0o755)
        calls = []
        real = self.module.git
        def git(root, *args):
            calls.append(args)
            return real(root, *args)
        with patch.object(self.module, 'git', side_effect=git):
            code, output = self.run_push()
        self.assertNotEqual(code, 0, output)
        self.assertFalse(any(args[0] in ('fetch', 'push', 'rebase') for args in calls))
        self.assertEqual(self.git(self.repo, 'show', ':documentation/plans/1.3.0/progress.md'), b'dirty report\n')
        self.assertEqual(self.remote_oid(), self.initial)

    def test_add_failure_is_not_report_success(self) -> None:
        (self.plans / 'progress.md').write_text('dirty report\n', encoding='utf-8')
        real = self.module.git
        calls = []
        def git(root, *args):
            calls.append(args)
            return (1, 'injected add error') if args[0] == 'add' else real(root, *args)
        with patch.object(self.module, 'git', side_effect=git):
            code, output = self.run_push()
        self.assertNotEqual(code, 0, output)
        self.assertFalse(any(args[0] in ('fetch', 'push', 'rebase') for args in calls))
        self.assertEqual(self.remote_oid(), self.initial)

    def test_only_current_portable_reports_are_committed(self) -> None:
        (self.plans / 'progress.md').write_text('portable update\n', encoding='utf-8')
        old = self.repo / 'documentation/plans/1.2.0'
        old.mkdir()
        (old / 'progress.md').write_text('foreign iteration\n', encoding='utf-8')
        for name in ('sessions.md', 'progress.html', 'snapshot.patch', '.progress-server', 'runtime.json'):
            (self.plans / name).write_text('local only\n', encoding='utf-8')
        code, output = self.run_push()
        self.assertEqual(code, 0, output)
        tracked = self.git(self.repo, 'ls-tree', '-r', '--name-only', 'HEAD').decode().splitlines()
        self.assertNotIn('documentation/plans/1.2.0/progress.md', tracked)
        for name in ('sessions.md', 'progress.html', 'snapshot.patch', '.progress-server', 'runtime.json'):
            self.assertNotIn('documentation/plans/1.3.0/' + name, tracked)
        self.assertEqual(self.remote_oid(), self.oid(self.repo))
        self.assertEqual(self.git(self.repo, 'show', 'HEAD:documentation/plans/1.3.0/progress.md'), b'portable update\n')

    def test_new_branch_push_confirms_full_oid_then_reports_already_synchronized(self) -> None:
        self.git(self.origin, 'update-ref', '-d', 'refs/heads/' + BRANCH)
        code, output = self.run_push()
        self.assertEqual(code, 0, output)
        self.assertIn(self.oid(self.repo), output)
        self.assertEqual(self.remote_oid(), self.oid(self.repo))
        code, output = self.run_push()
        self.assertEqual(code, 0, output)
        self.assertIn('synchronized', output)

    def test_missing_origin_is_not_success(self) -> None:
        self.git(self.repo, 'remote', 'remove', 'origin')
        code, output = self.run_push()
        self.assertNotEqual(code, 0, output)

    def test_report_changed_by_successful_hook_is_not_sent(self) -> None:
        (self.plans / 'progress.md').write_text('first report\n', encoding='utf-8')
        hook = self.repo / '.git/hooks/post-commit'
        hook.write_text('#!/bin/sh\nprintf "changed by hook\\n" > documentation/plans/1.3.0/progress.md\n', encoding='utf-8')
        hook.chmod(0o755)
        code, output = self.run_push()
        self.assertNotEqual(code, 0, output)
        self.assertEqual(self.remote_oid(), self.initial)
        self.assertEqual((self.plans / 'progress.md').read_bytes(), b'changed by hook\n')

    def test_real_origin_race_does_not_confirm_another_oid(self) -> None:
        peer = self.peer()
        (peer / 'other.bin').write_bytes(b'peer change')
        self.commit(peer, 'other.bin')
        other = self.oid(peer)
        (self.repo / 'binary.bin').write_bytes(b'local change')
        self.commit(self.repo, 'binary.bin')
        real = self.module.git
        lookups = 0
        def git(root, *args):
            nonlocal lookups
            if args[0] == 'ls-remote':
                lookups += 1
                if lookups == 2:
                    # Move the real bare ref at the confirmation boundary.
                    self.git(self.origin, 'update-ref', 'refs/heads/' + BRANCH, other)
            return real(root, *args)
        # Transfer peer's object without changing the branch under test.
        self.git(peer, 'push', '-q', 'origin', 'HEAD:refs/heads/race-fixture')
        with patch.object(self.module, 'git', side_effect=git):
            code, output = self.run_push()
        self.assertNotEqual(code, 0, output)
        self.assertEqual(self.remote_oid(), other)
        self.assertNotEqual(self.remote_oid(), self.oid(self.repo))

    def test_false_push_success_and_remote_lookup_failure_do_not_confirm(self) -> None:
        (self.repo / 'other.bin').write_bytes(b'\x00commit\xff')
        self.commit(self.repo, 'other.bin')
        for lookup_fails in (False, True):
            with self.subTest(lookup_fails=lookup_fails):
                real = self.module.git
                lookups = 0
                def git(root, *args):
                    nonlocal lookups
                    if args[0] == 'push':
                        return 0, 'Everything up-to-date'
                    if args[0] == 'ls-remote':
                        lookups += 1
                        if lookup_fails and lookups > 1:
                            return 1, 'injected ref lookup error'
                    return real(root, *args)
                with patch.object(self.module, 'git', side_effect=git):
                    code, output = self.run_push()
                self.assertNotEqual(code, 0, output)
                self.assertNotEqual(self.remote_oid(), self.oid(self.repo))

    def test_index_lock_is_not_removed_and_no_remote_action_runs(self) -> None:
        lock = self.repo / '.git/index.lock'
        lock.write_bytes(b'foreign owner')
        real = self.module.git
        calls = []
        def git(root, *args):
            calls.append(args)
            return real(root, *args)
        with patch.object(self.module, 'git', side_effect=git):
            code, output = self.run_push()
        self.assertNotEqual(code, 0, output)
        self.assertEqual(lock.read_bytes(), b'foreign owner')
        self.assertFalse(any(args[0] in ('fetch', 'push', 'rebase') for args in calls))


if __name__ == '__main__':
    unittest.main()
