"""Checkout-local portable plans and chat-local runtime state, using real Git repos."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'dev-pipeline'
PIPELINE = PLUGIN / 'skills/pipeline/scripts'
PLAN_STATE = PLUGIN / 'skills/work/scripts/plan_state.py'
sys.dont_write_bytecode = True


class StatePaths(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.main = self.base / 'main'
        self.main.mkdir()
        self.git(self.main, 'init', '-q', '-b', 'main')
        self.git(self.main, 'config', 'user.name', 'Test')
        self.git(self.main, 'config', 'user.email', 'test@example.com')
        self.git(self.main, 'commit', '-q', '--allow-empty', '-m', 'fixture')
        self.one = self.base / 'one'
        self.two = self.base / 'two'
        self.git(self.main, 'worktree', 'add', '-q', '-b', 'iteration/1.0.0', str(self.one))
        self.git(self.main, 'worktree', 'add', '-q', '-b', 'iteration/2.0.0', str(self.two))
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', CODEX_HOME=str(self.base / 'codex'))
        self.env.pop('CLAUDE_PROJECT_DIR', None)
        self.env.pop('CODEX_THREAD_ID', None)

    def git(self, checkout, *args):
        return subprocess.run(['git', '-C', str(checkout), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def cli(self, script, *args, checkout=None, chat='chat-a'):
        env = dict(self.env, CODEX_THREAD_ID=chat)
        return subprocess.run([sys.executable, str(script), *map(str, args)],
                              cwd=checkout or self.one, env=env, capture_output=True, text=True)

    def plan(self, checkout, version, unit='1'):
        folder = checkout / 'documentation/plans' / version
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / 'plan.md'
        path.write_text(f'# Plan {version}\n\n### U{unit}. Own checkout\n', encoding='utf-8')
        return path

    def stamp(self, checkout):
        path = checkout / 'documentation/.dev-pipeline.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{}', encoding='utf-8')

    def paths(self, checkout, version='1.0.0', chat='chat-a'):
        source = PIPELINE / 'state_paths.py'
        self.assertTrue(source.is_file(), 'U1 must provide the shared checkout state resolver')
        sys.path.insert(0, str(PIPELINE))
        self.addCleanup(sys.path.remove, str(PIPELINE))
        spec = importlib.util.spec_from_file_location('u1_state_paths', source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(module)
        return module.resolve_paths(checkout, version, chat)

    def sessions(self, checkout):
        gitdir = Path(self.git(checkout, 'rev-parse', '--absolute-git-dir'))
        return sorted((gitdir / 'pipeline-work').rglob('sessions.md'))

    def legacy(self, checkout, parent='chat-a'):
        path = checkout / 'documentation/plans/1.0.0/sessions.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('# Legacy sessions\n\n'
                        f'\u0420\u043e\u0434\u0438\u0442\u0435\u043b\u044c\u0441\u043a\u0430\u044f '
                        f'\u0441\u0435\u0441\u0441\u0438\u044f: {parent}\n\n'
                        '| # | Title | Stage | Skill | When | Id | State |\n'
                        '| 1 | 1.0.0 work | work | work | later | `legacy-child` | waiting |\n',
                        encoding='utf-8')
        return path

    def test_resolver_roots_are_inside_requested_checkout_and_gitdir(self):
        for checkout, version in ((self.main, '3.0.0'), (self.one, '1.0.0'), (self.two, '2.0.0')):
            nested = checkout / 'nested'
            nested.mkdir()
            for given in (checkout, nested):
                with self.subTest(checkout=given):
                    paths = self.paths(given, version)
                    self.assertEqual(paths.checkout, checkout)
                    self.assertEqual(paths.plans, checkout / 'documentation/plans' / version)
                    gitdir = Path(self.git(checkout, 'rev-parse', '--absolute-git-dir'))
                    self.assertTrue(paths.local.is_relative_to(gitdir / 'pipeline-work' / version))
                    self.assertNotEqual(paths.local, gitdir / 'pipeline-work' / version)

    def test_resolver_runtime_paths_are_distinct_for_chat_and_worktree(self):
        locals_ = {self.paths(checkout, chat=chat).local
                   for checkout in (self.main, self.one, self.two) for chat in ('chat-a', 'chat-b')}
        self.assertEqual(len(locals_), 6)

    def test_resolver_rejects_missing_and_non_git_roots(self):
        outside = self.base / 'outside'
        outside.mkdir()
        for root in (outside, self.base / 'missing'):
            with self.subTest(root=root):
                with self.assertRaises(ValueError):
                    self.paths(root)
        self.assertEqual(list(outside.iterdir()), [])

    def test_resolver_rejects_path_components_that_escape(self):
        for version in ('../escape', '/tmp/escape', '', '1.0.0/../../escape'):
            with self.subTest(version=version):
                with self.assertRaises(ValueError):
                    self.paths(self.one, version=version)
        for chat in ('../escape', '/tmp/escape', '', 'a/b', '..'):
            with self.subTest(chat=chat):
                with self.assertRaises(ValueError):
                    self.paths(self.one, chat=chat)

    def test_resolver_rejects_symlinked_portable_and_local_roots(self):
        (self.one / 'documentation').mkdir()
        (self.one / 'documentation/plans').symlink_to(self.main, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.paths(self.one)
        gitdir = Path(self.git(self.two, 'rev-parse', '--absolute-git-dir'))
        (gitdir / 'pipeline-work').symlink_to(self.main, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.paths(self.two)

    def test_guard_uses_iteration_of_requested_checkout(self):
        self.plan(self.main, '9.0.0')
        self.stamp(self.main)
        for checkout, version in ((self.one, '1.0.0'), (self.two, '2.0.0')):
            self.plan(checkout, version)
            self.stamp(checkout)
            payload = {'tool_name': 'Bash', 'cwd': str(checkout),
                       'tool_input': {'command': 'git update-ref refs/heads/main HEAD'}}
            result = subprocess.run([sys.executable, str(PLUGIN / 'hooks/guard.py')],
                                    input=json.dumps(payload), env=self.env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(result.stdout.strip(), 'moving main during the local open iteration must be denied')
            reason = json.loads(result.stdout)['hookSpecificOutput']['permissionDecisionReason']
            self.assertIn(version, reason)
            self.assertNotIn('9.0.0', reason)

    def test_plan_state_reads_only_local_plan_and_does_not_claim_shared_plans(self):
        for checkout, version, unit in ((self.one, '1.0.0', '11'), (self.two, '2.0.0', '22')):
            plan = self.plan(checkout, version, unit)
            result = self.cli(PLAN_STATE, plan, checkout=checkout)
            self.assertIn(f'version {version}', result.stdout)
            self.assertIn(f'U{unit}', result.stdout)
            self.assertNotIn('plans folder linked in', result.stdout)
            self.assertNotIn(str(self.main), result.stdout)

    def test_missing_plan_requires_switch_or_integration_without_main_fallback(self):
        foreign = self.plan(self.main, '1.0.0')
        before = foreign.read_bytes()
        missing = self.one / 'documentation/plans/1.0.0/plan.md'
        result = self.cli(PLAN_STATE, missing)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('open the session there', result.stdout)
        self.assertRegex(result.stdout.lower(), r'fetch|switch|integrat')
        self.assertFalse(missing.exists())
        self.assertEqual(foreign.read_bytes(), before)

    def test_plan_state_rejects_foreign_and_symlinked_plan(self):
        foreign = self.plan(self.main, '9.0.0', '99')
        link = self.one / 'documentation/plans/1.0.0'
        link.parent.mkdir(parents=True)
        link.symlink_to(foreign.parent, target_is_directory=True)
        for path in (foreign, link / 'plan.md'):
            with self.subTest(path=path):
                result = self.cli(PLAN_STATE, path)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('units 1', result.stdout)
                self.assertRegex(result.stdout.lower(), r'outside|foreign|checkout|symlink')

    def test_where_am_i_reads_ignored_plan_from_checkout_only(self):
        self.plan(self.main, '9.0.0')
        self.plan(self.one, '1.0.0')
        (self.one / '.gitignore').write_text('documentation/plans/\n', encoding='utf-8')
        result = self.cli(PIPELINE / 'where_am_i.py', self.one)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('1.0.0', result.stdout)
        self.assertNotIn('9.0.0', result.stdout)

    def test_subsessions_isolate_runtime_ids_by_chat_and_checkout(self):
        for checkout, chat, sid in ((self.one, 'chat-a', 'child-a'),
                                    (self.one, 'chat-b', 'child-b'), (self.two, 'chat-a', 'child-c')):
            for args in (('plan', 'work'), ('authorize', 'work'), ('set', '1', sid)):
                result = self.cli(PIPELINE / 'subsessions.py', checkout, '1.0.0', *args,
                                  checkout=checkout, chat=chat)
                self.assertEqual(result.returncode, 0, result.stderr)
        for checkout, chat, own, others in ((self.one, 'chat-a', 'child-a', ('child-b', 'child-c')),
                                            (self.one, 'chat-b', 'child-b', ('child-a', 'child-c')),
                                            (self.two, 'chat-a', 'child-c', ('child-a', 'child-b'))):
            result = self.cli(PIPELINE / 'subsessions.py', checkout, '1.0.0', 'show',
                              checkout=checkout, chat=chat)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(own, result.stdout)
            for other in others:
                self.assertNotIn(other, result.stdout)
        self.assertEqual(len(self.sessions(self.one)), 2)
        self.assertEqual(len(self.sessions(self.two)), 1)
        self.assertFalse((self.one / 'documentation/plans/1.0.0/sessions.md').exists())

    def test_legacy_sessions_require_explicit_matching_identity_and_preserve_source(self):
        source = self.legacy(self.one)
        before = source.read_bytes()
        implicit = self.cli(PIPELINE / 'subsessions.py', self.one, '1.0.0', 'show')
        self.assertNotEqual(implicit.returncode, 0)
        self.assertNotIn('legacy-child', implicit.stdout)
        for _ in range(2):
            result = self.cli(PIPELINE / 'subsessions.py', self.one, '1.0.0', 'show', '--legacy', source)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('legacy-child', result.stdout)
            self.assertEqual(source.read_bytes(), before)
        copies = self.sessions(self.one)
        self.assertEqual(len(copies), 1)
        first = copies[0].read_bytes()
        result = self.cli(PIPELINE / 'subsessions.py', self.one, '1.0.0', 'show', '--legacy', source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(copies[0].read_bytes(), first)
        self.assertIn('legacy-child', first.decode('utf-8'))

    def test_legacy_sessions_reject_foreign_checkout_and_other_chat(self):
        foreign = self.legacy(self.main)
        local = self.legacy(self.one, parent='other-chat')
        for source in (foreign, local):
            with self.subTest(source=source):
                before = source.read_bytes()
                result = self.cli(PIPELINE / 'subsessions.py', self.one, '1.0.0', 'show', '--legacy', source)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('legacy-child', result.stdout)
                self.assertEqual(source.read_bytes(), before)
                self.assertEqual(self.sessions(self.one), [])

    def test_common_dir_legacy_requires_checkout_chat_and_version_identity(self):
        common = Path(self.git(self.one, 'rev-parse', '--path-format=absolute', '--git-common-dir'))
        source = common / 'pipeline-work/1.0.0/legacy/sessions.md'
        local = self.legacy(self.one)
        source.parent.mkdir(parents=True)
        source.write_bytes(local.read_bytes())
        local.unlink()
        before = source.read_bytes()
        identity = source.with_name('state-identity.json')
        good = {'checkout': str(self.one), 'version': '1.0.0', 'chat_key': 'chat-a'}
        for metadata in (None, dict(good, checkout=str(self.two)), dict(good, chat_key='chat-b'),
                         dict(good, version='2.0.0')):
            with self.subTest(identity=metadata):
                if metadata is not None:
                    identity.write_text(json.dumps(metadata), encoding='utf-8')
                result = self.cli(PIPELINE / 'subsessions.py', self.one, '1.0.0', 'show', '--legacy', source)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('legacy-child', result.stdout)
                self.assertEqual(self.sessions(self.one), [])
                self.assertEqual(source.read_bytes(), before)
        identity.write_text(json.dumps(good), encoding='utf-8')
        identity_before = identity.read_bytes()
        for _ in range(2):
            result = self.cli(PIPELINE / 'subsessions.py', self.one, '1.0.0', 'show', '--legacy', source)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('legacy-child', result.stdout)
            self.assertEqual(len(self.sessions(self.one)), 1)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(identity.read_bytes(), identity_before)
        self.assertEqual(self.sessions(self.two), [])

    def test_open_iteration_migrates_ignored_plans_only_in_requested_checkout(self):
        foreign = self.plan(self.main, '9.0.0')
        foreign_before = foreign.read_bytes()
        plan = self.plan(self.one, '1.0.0')
        legacy = self.legacy(self.one)
        legacy_before = legacy.read_bytes()
        (self.one / '.gitignore').write_text('documentation/plans/\n', encoding='utf-8')
        for _ in range(2):
            result = self.cli(PIPELINE / 'open_iteration.py', '1.0.0', self.one)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(plan.read_text(encoding='utf-8'), '# Plan 1.0.0\n\n### U1. Own checkout\n')
            self.assertEqual(legacy.read_bytes(), legacy_before)
            self.assertEqual(foreign.read_bytes(), foreign_before)
            self.assertEqual(self.git(self.one, 'ls-files', '--', 'documentation/plans/1.0.0/plan.md'),
                             'documentation/plans/1.0.0/plan.md')
            self.assertEqual(self.git(self.one, 'ls-files', '--', 'documentation/plans/1.0.0/sessions.md'), '')
        self.assertFalse((self.main / '.gitignore').exists())

    def test_review_guard_denies_ref_mutation_with_invalid_plan_ownership(self):
        self.plan(self.main, '1.0.0')
        foreign = self.plan(self.main, '9.0.0')
        self.stamp(self.one)
        (self.one / 'documentation/plans').symlink_to(self.main / 'documentation/plans',
                                                    target_is_directory=True)
        self.plan(self.two, '2.0.0')
        self.stamp(self.two)
        (self.two / 'documentation/plans/9.0.0').symlink_to(foreign.parent, target_is_directory=True)
        original_ref = self.git(self.main, 'rev-parse', 'refs/heads/main')
        original_bytes = foreign.read_bytes()
        for checkout in (self.one, self.two):
            with self.subTest(checkout=checkout):
                payload = {'tool_name': 'Bash', 'cwd': str(checkout),
                           'tool_input': {'command': 'git update-ref refs/heads/main HEAD'}}
                result = subprocess.run([sys.executable, str(PLUGIN / 'hooks/guard.py')],
                                        input=json.dumps(payload), env=self.env, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.strip(), 'invalid plans ownership must not disable the guard')
                decision = json.loads(result.stdout)['hookSpecificOutput']
                self.assertEqual(decision['permissionDecision'], 'deny')
                self.assertRegex(decision['permissionDecisionReason'].lower(),
                                 r'checkout|ownership|invalid|symlink|outside')
                self.assertEqual(self.git(self.main, 'rev-parse', 'refs/heads/main'), original_ref)
                self.assertEqual(foreign.read_bytes(), original_bytes)
                payload['tool_input']['command'] = 'git status --short'
                read_only = subprocess.run([sys.executable, str(PLUGIN / 'hooks/guard.py')],
                                          input=json.dumps(payload), env=self.env, text=True, capture_output=True)
                self.assertEqual(read_only.returncode, 0, read_only.stderr)
                self.assertEqual(read_only.stdout.strip(), '')

    def test_review_legacy_duplicate_parent_headers_rejected_before_copy(self):
        for checkout, duplicate in ((self.one, 'chat-b'), (self.two, 'chat-a')):
            with self.subTest(duplicate=duplicate):
                source = self.legacy(checkout)
                source.write_text(source.read_text(encoding='utf-8') +
                                  '\n\u0420\u043e\u0434\u0438\u0442\u0435\u043b\u044c\u0441\u043a\u0430\u044f '
                                  f'\u0441\u0435\u0441\u0441\u0438\u044f: {duplicate}\n', encoding='utf-8')
                before = source.read_bytes()
                destination = self.paths(checkout).local
                self.assertFalse(destination.exists())
                result = self.cli(PIPELINE / 'subsessions.py', checkout, '1.0.0', 'show', '--legacy', source,
                                  checkout=checkout)
                self.assertEqual(source.read_bytes(), before)
                self.assertNotEqual(result.returncode, 0, 'duplicate parent headers must be ambiguous')
                self.assertFalse(destination.exists(), 'identity must be validated before any destination write')
                self.assertNotIn('legacy-child', result.stdout)

    def runtime_snapshot(self, checkout):
        gitdir = Path(self.git(checkout, 'rev-parse', '--absolute-git-dir'))
        runtime = gitdir / 'pipeline-work'
        return {p.relative_to(runtime): p.read_bytes() for p in runtime.rglob('*') if p.is_file()}

    def test_review_child_whoami_finds_parent_read_only_and_keeps_writes_local(self):
        for args in (('plan', 'work', 'audit'), ('authorize', 'work', 'audit'), ('set', '1', 'child-c'), ('set', '2', 'sibling-secret')):
            result = self.cli(PIPELINE / 'subsessions.py', self.one, '1.0.0', *args, chat='parent-p')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        before = self.runtime_snapshot(self.one)
        child_paths = self.paths(self.one, chat='child-c')
        for _ in range(2):
            result = self.cli(PIPELINE / 'subsessions.py', self.one, '1.0.0', 'whoami', 'child-c', chat='child-c')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('parent-p', result.stdout)
            self.assertIn('\u044d\u0442\u0430\u043f work', result.stdout)
            self.assertNotIn('sibling-secret', result.stdout)
            self.assertFalse(child_paths.local.exists(), 'whoami discovery must not copy a parent registry')
            self.assertEqual(self.runtime_snapshot(self.one), before)
        result = self.cli(PIPELINE / 'subsessions.py', self.one, '1.0.0', 'plan', 'ci', chat='child-c')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        after = self.runtime_snapshot(self.one)
        for path, content in before.items():
            self.assertEqual(after[path], content, 'child writes must preserve the owning parent registry')
        self.assertTrue((child_paths.local / 'sessions.md').exists())
        self.assertEqual(len(self.sessions(self.one)), 2)

    def test_review_child_whoami_rejects_ambiguous_parent_registries(self):
        for parent, stage in (('parent-p', 'work'), ('parent-q', 'audit')):
            for args in (('plan', stage), ('authorize', stage), ('set', '1', 'child-c')):
                result = self.cli(PIPELINE / 'subsessions.py', self.one, '1.0.0', *args, chat=parent)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        before = self.runtime_snapshot(self.one)
        result = self.cli(PIPELINE / 'subsessions.py', self.one, '1.0.0', 'whoami', 'child-c', chat='child-c')
        self.assertNotEqual(result.returncode, 0)
        self.assertRegex((result.stdout + result.stderr).lower(),
                         r'ambig|multiple|\u043d\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u043e|\u043d\u0435\u043e\u0434\u043d\u043e\u0437\u043d\u0430\u0447')
        self.assertEqual(self.runtime_snapshot(self.one), before)

    def test_review_child_whoami_does_not_discover_foreign_checkout(self):
        for checkout in (self.main, self.two):
            for args in (('plan', 'audit'), ('authorize', 'audit'), ('set', '1', 'child-c')):
                result = self.cli(PIPELINE / 'subsessions.py', checkout, '1.0.0', *args,
                                  checkout=checkout, chat='foreign-parent')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        before = {checkout: self.runtime_snapshot(checkout) for checkout in (self.main, self.one, self.two)}
        result = self.cli(PIPELINE / 'subsessions.py', self.one, '1.0.0', 'whoami', 'child-c', chat='child-c')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('foreign-parent', result.stdout + result.stderr)
        self.assertNotIn('\u044d\u0442\u0430\u043f audit', result.stdout)
        for checkout, state in before.items():
            self.assertEqual(self.runtime_snapshot(checkout), state)

    def test_review_child_whoami_ignores_unproven_owner_namespace(self):
        for args in (('parent', 'parent-p'), ('plan', 'work'), ('authorize', 'work'), ('set', '1', 'child-other')):
            result = self.cli(PIPELINE / 'subsessions.py', self.one, '1.0.0', *args, chat='parent-p')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        original = self.paths(self.one, chat='parent-p').local / 'sessions.md'
        forged = self.paths(self.one, chat='owner-q').local / 'sessions.md'
        forged.parent.mkdir(parents=True)
        forged.write_bytes(original.read_bytes().replace(b'child-other', b'child-c'))
        before = self.runtime_snapshot(self.one)
        result = self.cli(PIPELINE / 'subsessions.py', self.one, '1.0.0', 'whoami', 'child-c', chat='child-c')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('parent-p', result.stdout)
        self.assertEqual(self.runtime_snapshot(self.one), before)


if __name__ == '__main__':
    unittest.main()
