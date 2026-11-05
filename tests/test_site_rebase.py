"""Real divergent local clones exercise generated-site rebase and recovery."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch
import unittest

from test_push_branch import BRANCH, GitFixture, ROOT


class SiteRebase(GitFixture):
    def divergence(self, source_conflict: bool = False) -> Path:
        docs = self.repo / 'documentation/architecture'
        docs.mkdir()
        (docs / 'one.md').write_text('# First\n\nbase first\n', encoding='utf-8')
        (docs / 'two.md').write_text('# Second\n\nbase second\n', encoding='utf-8')
        site = self.repo / 'documentation/_web-docs'
        site.mkdir()
        (site / 'index.html').write_text('base site\n', encoding='utf-8')
        self.commit(self.repo, 'documentation')
        self.git(self.repo, 'push', '-q', 'origin', BRANCH)
        peer = self.peer()
        (peer / 'documentation/architecture/one.md').write_text('# First\n\nREMOTE SOURCE\n', encoding='utf-8')
        (peer / 'documentation/_web-docs/index.html').write_text('remote site\n', encoding='utf-8')
        self.commit(peer, 'documentation')
        self.git(peer, 'push', '-q', 'origin', BRANCH)
        path = 'one.md' if source_conflict else 'two.md'
        (docs / path).write_text('# Local\n\nLOCAL SOURCE\n', encoding='utf-8')
        (site / 'index.html').write_text('local site\n', encoding='utf-8')
        self.commit(self.repo, 'documentation')
        self.before_rebase = self.oid(self.repo)
        self.remote_before = self.remote_oid()
        return peer

    def dirty_layers(self) -> dict:
        (self.repo / 'binary.bin').write_bytes(b'\x00staged\xfe')
        self.git(self.repo, 'add', 'binary.bin')
        (self.repo / 'binary.bin').write_bytes(b'\x00unstaged\xff')
        (self.repo / 'other.bin').write_bytes(b'\x00unstaged other\xff')
        (self.repo / 'untracked\nbytes.bin').write_bytes(b'\x00new\x80')
        return self.layers()

    def layers(self) -> dict:
        names = ('binary.bin', 'other.bin', 'untracked\nbytes.bin')
        return {'files': {name: (self.repo / name).read_bytes() for name in names},
                'index': self.git(self.repo, 'ls-files', '--stage', '-z', '--', *names),
                'status': self.git(self.repo, 'status', '--porcelain=v1', '-z', '--', *names)}

    def journal(self) -> dict:
        paths = list((self.repo / '.git/pipeline-work').rglob('push-recovery.json'))
        self.assertEqual(len(paths), 1)
        return json.loads(paths[0].read_bytes())

    def run_with_valid_docs(self) -> tuple[int, str]:
        # Document-form checks are separate from these Git-state regressions.
        with patch.object(self.module, 'form_problems', return_value=''):
            return self.run_push()

    def test_generated_only_conflict_rebuilds_both_merged_sources_and_preserves_layers(self) -> None:
        self.divergence()
        late = self.repo / 'documentation/architecture/late.md'
        late.write_text('# Later commit\n\nLATE SOURCE\n', encoding='utf-8')
        self.commit(self.repo, 'documentation/architecture/late.md')
        expected = self.dirty_layers()
        code, output = self.run_with_valid_docs()
        self.assertEqual(code, 0, output)
        search = (self.repo / 'documentation/_web-docs/assets/search-index.js').read_text(encoding='utf-8')
        self.assertIn('REMOTE SOURCE', search)
        self.assertIn('LOCAL SOURCE', search)
        self.assertIn('LATE SOURCE', search)
        self.assertEqual(self.layers(), expected)
        self.assertEqual(self.remote_oid(), self.oid(self.repo))
        self.assertFalse((self.repo / '.git/rebase-merge').exists())
        self.assertFalse(list((self.repo / '.git/pipeline-work').rglob('push-recovery.json')))

    def test_source_conflict_aborts_and_restores_exact_stash_including_old_stash(self) -> None:
        self.divergence(source_conflict=True)
        (self.repo / 'other.bin').write_bytes(b'old stash')
        self.git(self.repo, 'stash', 'push', '-qm', 'foreign stash')
        old_stash = self.git(self.repo, 'rev-parse', 'refs/stash')
        expected = self.dirty_layers()
        code, output = self.run_with_valid_docs()
        self.assertEqual(code, 2, output)
        self.assertEqual(self.oid(self.repo), self.before_rebase)
        self.assertEqual(self.remote_oid(), self.remote_before)
        self.assertEqual(self.layers(), expected)
        self.assertIn(old_stash.strip(), self.git(self.repo, 'stash', 'list', '--format=%H'))
        self.assertFalse((self.repo / '.git/rebase-merge').exists())

    def test_build_failure_aborts_no_push_and_recovers_dirty_layers(self) -> None:
        self.divergence()
        expected = self.dirty_layers()
        with patch.object(self.module, 'rebuild_site', return_value=(1, 'injected renderer failure')):
            code, output = self.run_with_valid_docs()
        self.assertEqual(code, 2, output)
        self.assertEqual(self.oid(self.repo), self.before_rebase)
        self.assertEqual(self.remote_oid(), self.remote_before)
        self.assertEqual(self.layers(), expected)

    def api_fixture(self, tool: bool = True) -> None:
        exclude = self.repo / '.git/info/exclude'
        exclude.write_text(exclude.read_text(encoding='utf-8') + '\nnode_modules/\n', encoding='utf-8')
        api = self.repo / 'documentation/api'
        api.mkdir(exist_ok=True)
        spec = {'openapi': '3.0.3', 'info': {'title': 'Merged API', 'version': '1.0.0'},
                'paths': {'/fixture': {'get': {'operationId': 'mergedOperation',
                                             'responses': {'200': {'description': 'ok'}}}}}}
        (api / 'openapi.yaml').write_text(json.dumps(spec), encoding='utf-8')
        modules = self.repo / 'node_modules'
        assets = modules / 'swagger-ui-dist'
        assets.mkdir(parents=True, exist_ok=True)
        for name in ('swagger-ui-bundle.js', 'swagger-ui.css'):
            (assets / name).write_text('fixture asset', encoding='utf-8')
        if tool:
            executable = modules / '.bin/redocly'
            executable.parent.mkdir(exist_ok=True)
            executable.write_text(f'#!{sys.executable}\nimport json, pathlib, sys\n'
                                  'spec=json.loads(pathlib.Path(sys.argv[2]).read_text())\n'
                                  'pathlib.Path(sys.argv[sys.argv.index("-o")+1]).write_text(json.dumps(spec))\n',
                                  encoding='utf-8')
            executable.chmod(0o755)
        self.commit(self.repo, 'documentation/api')

    def test_offline_api_rebuild_uses_installed_local_tool_and_merged_source(self) -> None:
        self.api_fixture()
        self.divergence()
        code, output = self.run_with_valid_docs()
        self.assertEqual(code, 0, output)
        bundled = json.loads((self.repo / 'documentation/_web-docs/api/openapi.json').read_bytes())
        self.assertEqual(bundled['info']['title'], 'Merged API')
        self.assertEqual(bundled['paths']['/fixture']['get']['operationId'], 'mergedOperation')
        self.assertIn('mergedOperation', (self.repo / 'documentation/_web-docs/api/spec.js').read_text(encoding='utf-8'))
        self.assertIn('src="spec.js"', (self.repo / 'documentation/_web-docs/api/index.html').read_text(encoding='utf-8'))
        self.assertEqual(self.remote_oid(), self.oid(self.repo))

    def test_missing_local_api_tool_aborts_and_cleans_only_own_build_scratch(self) -> None:
        self.api_fixture(tool=False)
        self.divergence()
        expected = self.dirty_layers()
        code, output = self.run_with_valid_docs()
        self.assertEqual(code, 2, output)
        self.assertIn('offline API build requires', output)
        self.assertEqual(self.oid(self.repo), self.before_rebase)
        self.assertEqual(self.remote_oid(), self.remote_before)
        self.assertEqual(self.layers(), expected)
        self.assertFalse((self.repo / 'documentation/._web-docs.building').exists())

    def test_checkpoint_restore_refusal_retains_journal_and_never_pushes(self) -> None:
        self.divergence(source_conflict=True)
        expected = self.dirty_layers()
        with patch.object(self.module.checkpoint, 'restore',
                          side_effect=self.module.checkpoint.CheckpointError('restore-incomplete', 'injected restore failure')):
            code, output = self.run_with_valid_docs()
        self.assertEqual(code, 2, output)
        self.assertEqual(self.journal()['status'], 'restore-verification-failed')
        self.assertEqual(self.remote_oid(), self.remote_before)
        self.assertEqual(self.layers(), expected)

    def test_final_build_failure_retains_changed_head_exact_stash_and_journal(self) -> None:
        self.divergence()
        self.dirty_layers()
        real = self.module.rebuild_site
        calls = 0
        def build(root):
            nonlocal calls
            calls += 1
            return real(root) if calls == 1 else (1, 'injected final build error')
        with patch.object(self.module, 'rebuild_site', side_effect=build):
            code, output = self.run_with_valid_docs()
        self.assertEqual(code, 2, output)
        self.assertEqual(self.journal()['status'], 'rebase-finalize-failed')
        self.assertNotEqual(self.oid(self.repo), self.before_rebase)
        self.assertEqual(self.remote_oid(), self.remote_before)
        self.git(self.repo, 'cat-file', '-e', self.journal()['stash'])

    def test_abort_failure_keeps_rebase_stash_snapshot_and_explicit_recovery_state(self) -> None:
        self.divergence(source_conflict=True)
        self.dirty_layers()
        real = self.module.git
        def git(root, *args):
            return (1, 'injected abort error') if args[:2] == ('rebase', '--abort') else real(root, *args)
        with patch.object(self.module, 'git', side_effect=git):
            code, output = self.run_with_valid_docs()
        self.assertEqual(code, 2, output)
        journal = self.journal()
        self.assertEqual(journal['status'], 'abort-failed')
        self.assertTrue((self.repo / '.git/rebase-merge').exists())
        self.git(self.repo, 'cat-file', '-e', journal['stash'])
        self.assertTrue(Path(journal['snapshot']).is_dir())
        self.assertIn('recovery', output)
        self.assertEqual(self.remote_oid(), self.remote_before)

    def test_stash_apply_failure_is_not_retried_or_pushed(self) -> None:
        self.divergence()
        self.dirty_layers()
        real = self.module.git
        calls = []
        def git(root, *args):
            calls.append(args)
            if args[:2] == ('stash', 'apply'):
                # Real apply may have already changed bytes before reporting failure.
                real(root, *args)
                return 1, 'injected partial restore failure'
            return real(root, *args)
        with patch.object(self.module, 'git', side_effect=git):
            code, output = self.run_with_valid_docs()
            before = self.layers()
            again, second_output = self.run_with_valid_docs()
        self.assertEqual(code, 2, output)
        self.assertNotEqual(again, 0, second_output)
        self.assertEqual(sum(args[:2] == ('stash', 'apply') for args in calls), 1)
        self.assertFalse(any(args[0] == 'push' for args in calls))
        self.assertEqual(self.layers(), before)
        self.assertEqual(self.journal()['status'], 'stash-restore-failed')
        self.assertEqual(self.remote_oid(), self.remote_before)

    def test_existing_rebase_is_never_aborted_or_modified(self) -> None:
        self.divergence(source_conflict=True)
        self.git(self.repo, 'fetch', 'origin', BRANCH)
        self.git(self.repo, 'rebase', 'FETCH_HEAD', check=False)
        metadata = self.repo / '.git/rebase-merge'
        before = {p.name: p.read_bytes() for p in metadata.iterdir() if p.is_file()}
        head = self.oid(self.repo)
        code, output = self.run_with_valid_docs()
        self.assertNotEqual(code, 0, output)
        self.assertEqual(self.oid(self.repo), head)
        self.assertEqual({p.name: p.read_bytes() for p in metadata.iterdir() if p.is_file()}, before)
        self.assertEqual(self.remote_oid(), self.remote_before)


class RebuildForeground(unittest.TestCase):
    def module(self):
        source = ROOT / 'dev-pipeline/skills/docs-site/scripts/rebuild.py'
        spec = importlib.util.spec_from_file_location('rebuild_git_batch', source)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_missing_builder_is_explicit_failure_without_server(self) -> None:
        module = self.module()
        with patch.object(module, 'HERE', Path('/definitely/missing/docs-site/scripts')):
            self.assertNotEqual(module.for_rebase(ROOT), 0)


if __name__ == '__main__':
    unittest.main()
