"""Lossless, checkout-owned checkpoints, exercised against temporary Git repos."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'dev-pipeline/skills/pipeline/scripts'
SCRIPT = SCRIPTS / 'checkpoint.py'
VERSION = '1.3.0'
PHASES = ('unit', 'wave', 'low-fix', 'final-checks', 'whole-review', 'review-fix')
sys.dont_write_bytecode = True


class Checkpoints(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.repo = self.base / 'source'
        self.repo.mkdir()
        self.git(self.repo, 'init', '-q', '-b', 'iteration/1.3.0')
        self.git(self.repo, 'config', 'user.name', 'Test')
        self.git(self.repo, 'config', 'user.email', 'test@example.com')
        self.git(self.repo, 'config', 'core.filemode', 'true')
        self.git(self.repo, 'config', 'core.autocrlf', 'false')
        self.plans = self.repo / 'documentation/plans' / VERSION
        self.plans.mkdir(parents=True)
        (self.plans / 'plan.md').write_text('# Plan\n\n### U2. Checkpoint\n', encoding='utf-8')
        for name in ('same.txt', 'staged.txt', 'deleted.txt', 'tool.sh', 'foreign.txt'):
            (self.repo / name).write_bytes(b'base\n')
        (self.repo / 'binary.bin').write_bytes(bytes(range(256)))
        (self.repo / 'link').symlink_to('same.txt')
        self.git(self.repo, 'add', '.')
        self.git(self.repo, 'commit', '-qm', 'fixture')
        self.head = self.git(self.repo, 'rev-parse', 'HEAD').decode().strip()
        self.names = ['same.txt', 'staged.txt', 'deleted.txt', 'tool.sh', 'binary.bin',
                      'link', 'new text.txt', 'new\nline.bin', 'new-link', 'foreign.txt']

    def git(self, repo: Path, *args: str, check: bool = True) -> bytes:
        result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                                check=check, env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'),
                                timeout=20)
        return result.stdout

    def module(self) -> ModuleType:
        # A missing unit symbol is RED, not an accidental import/fixture error.
        self.assertTrue(SCRIPT.is_file(), 'U2 must provide checkpoint.capture and checkpoint.restore')
        sys.path.insert(0, str(SCRIPTS))
        self.addCleanup(sys.path.remove, str(SCRIPTS))
        spec = importlib.util.spec_from_file_location('u2_checkpoint', SCRIPT)
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(module)
        for symbol in ('capture', 'restore', 'CheckpointError'):
            self.assertTrue(hasattr(module, symbol), f'U2 must provide checkpoint.{symbol}')
        return module

    def state(self, phase: str = 'unit') -> dict:
        return {'run_id': 'run-one', 'source_id': 'logical-one', 'unit': 'U2',
                'phase': phase, 'next_action': 'review U2 before committing',
                'review': {'base': self.head, 'head': self.head},
                'low_batches': [{'units': ['U1'], 'base': self.head, 'head': self.head,
                                 'findings': ['F1']}],
                'findings': [{'id': 'F1', 'status': 'open',
                              'attempts': [{'change': 'first fix', 'result': 'still red'}]}],
                'decisions': [{'id': 'D1', 'decision': 'preserve the staged boundary'}],
                'reports': {'work-run.md': '# Run\nU1 reviewed. U2 in flight.\n',
                            'resume.md': '# Resume\nReview U2 before committing.\n',
                            'context-handover.md': '# Handover\nF1 remains open.\n'}}

    def dirty(self) -> list[str]:
        (self.repo / 'staged.txt').write_bytes(b'only staged\n')
        (self.repo / 'same.txt').write_bytes(b'staged layer\n')
        self.git(self.repo, 'add', 'staged.txt', 'same.txt')
        (self.repo / 'same.txt').write_bytes(b'unstaged layer\n')
        (self.repo / 'deleted.txt').unlink()
        (self.repo / 'binary.bin').write_bytes(b'\x00\xff\x80changed\x00')
        (self.repo / 'tool.sh').chmod(0o755)
        (self.repo / 'link').unlink()
        (self.repo / 'link').symlink_to('binary.bin')
        (self.repo / 'new text.txt').write_bytes(b'new text\r\n')
        (self.repo / 'new\nline.bin').write_bytes(b'\x00\xffnew\x00')
        (self.repo / 'new\nline.bin').chmod(0o755)
        (self.repo / 'new-link').symlink_to('missing-target')
        return [name for name in self.names if name != 'foreign.txt']

    def inventory(self, repo: Path) -> dict:
        files = {}
        for name in self.names:
            path = repo / name
            if path.is_symlink():
                files[name] = ('symlink', os.readlink(path))
            elif path.exists():
                files[name] = ('file', path.read_bytes(), path.stat().st_mode & 0o777)
            else:
                files[name] = ('missing',)
        return {'files': files,
                'index': self.git(repo, 'ls-files', '--stage', '-z', '--', *self.names),
                'status': self.git(repo, 'status', '--porcelain=v1', '-z', '--', *self.names),
                'staged': self.git(repo, 'diff', '--cached', '--binary', '--full-index', '--', *self.names),
                'unstaged': self.git(repo, 'diff', '--binary', '--full-index', '--', *self.names)}

    def raw_index(self, repo: Path) -> bytes:
        gitdir = Path(self.git(repo, 'rev-parse', '--absolute-git-dir').decode().strip())
        return (gitdir / 'index').read_bytes()

    def capture(self, module: ModuleType, owned: list[str], **kwargs) -> dict:
        return module.capture(self.repo, VERSION, 'physical-thread-one', self.state(), owned, **kwargs)

    def portable(self, manifest: dict) -> Path:
        return self.plans / 'checkpoints' / manifest['checkpoint_id']

    def local(self, manifest: dict) -> Path:
        from state_paths import resolve_paths
        return resolve_paths(self.repo, VERSION, 'physical-thread-one').local / 'checkpoints' / manifest['checkpoint_id']

    def clone(self, name: str = 'target') -> Path:
        destination = self.base / name
        self.git(self.repo, 'clone', '-q', '--no-local', str(self.repo), str(destination))
        return destination

    def assert_error(self, module: ModuleType, code: str, call, *args, **kwargs) -> None:
        with self.assertRaises(module.CheckpointError) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_capture_preserves_raw_index_status_bytes_modes_and_each_layer(self) -> None:
        owned = self.dirty()
        before, index = self.inventory(self.repo), self.raw_index(self.repo)
        module = self.module()
        manifest = self.capture(module, owned)
        self.assertEqual(self.inventory(self.repo), before)
        self.assertEqual(self.raw_index(self.repo), index)
        self.assertTrue(before['staged'])
        self.assertTrue(before['unstaged'])
        self.assertEqual(self.git(self.repo, 'show', ':same.txt'), b'staged layer\n')
        for folder in (self.portable(manifest), self.local(manifest)):
            self.assertTrue((folder / 'staged.patch').read_bytes())
            self.assertTrue((folder / 'unstaged.patch').read_bytes())
        self.assertTrue(manifest['completeness']['local'])
        self.assertTrue(manifest['completeness']['portable'])
        self.assertEqual(manifest['completeness']['scope'], 'owned')

    def test_local_only_recovery_never_publishes_or_rewrites_portable_state(self) -> None:
        module = self.module()
        published = self.capture(module, [])
        before = {p.relative_to(self.plans).as_posix(): p.read_bytes()
                  for p in self.plans.rglob('*') if p.is_file()}
        owned = self.dirty()
        inventory, index = self.inventory(self.repo), self.raw_index(self.repo)
        local = self.capture(module, owned, local_only=True)
        self.assertEqual(local['completeness'], {'local': True, 'portable': False, 'scope': 'local'})
        self.assertEqual({p.relative_to(self.plans).as_posix(): p.read_bytes()
                          for p in self.plans.rglob('*') if p.is_file()}, before)
        self.assertTrue(self.portable(published).is_dir())
        self.assertFalse(self.portable(local).exists())
        self.assertTrue((self.local(local) / 'manifest.json').is_file())
        self.assertEqual(self.inventory(self.repo), inventory)
        self.assertEqual(self.raw_index(self.repo), index)

    def test_roundtrip_preserves_layers_untracked_binary_delete_exec_and_symlink(self) -> None:
        owned = self.dirty()
        expected = self.inventory(self.repo)
        module = self.module()
        manifest = self.capture(module, owned)
        target = self.clone()
        result = module.restore(target, VERSION, 'physical-target', manifest['checkpoint_id'],
                                source=self.portable(manifest))
        self.assertEqual(result['status'], 'restored')
        self.assertEqual(self.inventory(target), expected)
        index = self.raw_index(target)
        result = module.restore(target, VERSION, 'physical-target', manifest['checkpoint_id'],
                                source=self.portable(manifest))
        self.assertEqual(result['status'], 'already-restored')
        self.assertEqual(self.inventory(target), expected)
        self.assertEqual(self.raw_index(target), index)

    def test_local_restore_includes_foreign_changes_but_portable_does_not(self) -> None:
        owned = self.dirty()
        secret = b'foreign unowned private edit\n'
        (self.repo / 'foreign.txt').write_bytes(secret)
        module = self.module()
        manifest = self.capture(module, owned)
        portable = self.portable(manifest)
        for path in portable.rglob('*'):
            if path.is_file():
                self.assertNotIn(secret, path.read_bytes(), str(path))
                self.assertNotIn(b'foreign.txt', path.read_bytes(), str(path))
        self.assertIn(secret, b''.join(p.read_bytes() for p in self.local(manifest).rglob('*') if p.is_file()))
        target = self.clone()
        module.restore(target, VERSION, 'physical-target', manifest['checkpoint_id'], source=portable)
        self.assertEqual((target / 'foreign.txt').read_bytes(), b'base\n')
        self.assertEqual((self.repo / 'foreign.txt').read_bytes(), secret)
        result = module.restore(self.repo, VERSION, 'physical-thread-one', manifest['checkpoint_id'])
        self.assertEqual(result['status'], 'already-restored')

    def test_committed_artifacts_in_clone_carry_payload_reports_and_decisions(self) -> None:
        owned = self.dirty()
        expected = self.inventory(self.repo)
        module = self.module()
        manifest = self.capture(module, owned)
        self.git(self.repo, 'add', '--', str(self.portable(manifest)),
                 *(str(self.plans / name) for name in ('run-state.json', 'work-run.md', 'resume.md', 'context-handover.md')))
        # Commit only the artifact index; source edits remain staged in their original index.
        self.git(self.repo, 'commit', '-qm', 'portable handover fixture', '--only', '--',
                 str(self.portable(manifest)),
                 *(str(self.plans / name) for name in ('run-state.json', 'work-run.md', 'resume.md', 'context-handover.md')))
        target = self.clone()
        target_plans = target / 'documentation/plans' / VERSION
        saved = json.loads((target_plans / 'run-state.json').read_text(encoding='utf-8'))
        for field in ('review', 'low_batches', 'findings', 'decisions', 'next_action'):
            self.assertEqual(saved[field], self.state()[field])
        for name, contents in self.state()['reports'].items():
            self.assertEqual((target_plans / name).read_text(encoding='utf-8'), contents)
        exported = self.base / 'exported-checkpoint'
        shutil.copytree(target_plans / 'checkpoints' / manifest['checkpoint_id'], exported)
        self.git(target, 'checkout', '-q', '--detach', self.head)
        # Removing the source's local recovery data proves the clone is self-contained.
        shutil.rmtree(self.local(manifest))
        result = module.restore(target, VERSION, 'new-machine-thread', manifest['checkpoint_id'], source=exported)
        self.assertEqual(result['status'], 'restored')
        self.assertEqual(self.inventory(target), expected)

    def test_schema_persists_every_phase_plan_hash_ranges_and_findings(self) -> None:
        import hashlib
        module = self.module()
        plan_hash = hashlib.sha256((self.plans / 'plan.md').read_bytes()).hexdigest()
        for phase in PHASES:
            with self.subTest(phase=phase):
                state = self.state(phase)
                manifest = module.capture(self.repo, VERSION, 'physical-thread-one', state, [])
                self.assertEqual(manifest['schema_version'], 1)
                self.assertEqual(manifest['head'], self.head)
                self.assertEqual(manifest['branch'], 'iteration/1.3.0')
                self.assertEqual(manifest['plan_sha256'], plan_hash)
                self.assertTrue(manifest['checkpoint_id'])
                for field in ('run_id', 'source_id', 'phase', 'next_action', 'review', 'low_batches', 'findings', 'decisions'):
                    self.assertEqual(manifest[field], state[field])
                self.assertEqual(json.loads((self.plans / 'run-state.json').read_text(encoding='utf-8')), manifest)
                self.assertEqual(json.loads((self.portable(manifest) / 'manifest.json').read_text(encoding='utf-8')), manifest)

    def test_physical_runtime_ids_and_logs_remain_local(self) -> None:
        module = self.module()
        runtime = {'host': 'private-host-123', 'thread': 'physical-thread-one',
                   'processes': [{'pid': 812345, 'log': '/private/host-only/run.log'}],
                   'owner': {'status': 'known'}, 'writers': [], 'checks': []}
        manifest = self.capture(module, [], runtime=runtime)
        for path in self.plans.rglob('*'):
            if path.is_file():
                contents = path.read_bytes()
                for secret in (b'private-host-123', b'physical-thread-one', b'812345', b'/private/host-only'):
                    self.assertNotIn(secret, contents, str(path))
        local_bytes = b''.join(p.read_bytes() for p in self.local(manifest).rglob('*') if p.is_file())
        self.assertIn(b'private-host-123', local_bytes)
        self.assertIn(b'physical-thread-one', local_bytes)

    def test_checkpoint_keeps_owner_and_next_action_without_pause_or_successor(self) -> None:
        module = self.module()
        manifest = self.capture(module, [], runtime={'owner': {'status': 'known'},
                                                   'writers': [{'id': 'child', 'status': 'running'}]})
        self.assertFalse(manifest['paused'])
        self.assertEqual(manifest['source_id'], 'logical-one')
        self.assertEqual(manifest['next_action'], self.state()['next_action'])
        event = manifest['events'][-1]
        self.assertEqual(event['type'], 'CHECKPOINT')
        self.assertEqual(event['source_id'], 'logical-one')
        self.assertIsNone(event['successor_id'])

    def test_handover_requires_confirmation_and_stopped_writers_and_checks(self) -> None:
        module = self.module()
        for flags in ({}, {'ownership_confirmed': True},
                      {'ownership_confirmed': True, 'writers_stopped': True}):
            with self.subTest(flags=flags):
                self.assert_error(module, 'unsafe-handover', self.capture, module, [],
                                  event='HANDOVER', successor_id='logical-two', **flags)
        self.assertFalse((self.plans / 'run-state.json').exists())

    def test_active_child_check_and_unknown_or_stale_owner_block_handover(self) -> None:
        module = self.module()
        for runtime in ({'writers': [{'id': 'child', 'status': 'running'}]},
                        {'checks': [{'id': 'check', 'status': 'running'}]},
                        {'owner': {'status': 'unknown'}}, {'owner': {'status': 'stale'}}):
            with self.subTest(runtime=runtime):
                self.assert_error(module, 'unsafe-handover', self.capture, module, [],
                                  event='HANDOVER', successor_id='logical-two',
                                  ownership_confirmed=True, writers_stopped=True,
                                  checks_stopped=True, runtime=runtime)
        self.assertFalse((self.plans / 'run-state.json').exists())

    def test_events_link_checkpoint_handover_resume_and_compact_logically(self) -> None:
        module = self.module()
        self.capture(module, [])
        for event in ('HANDOVER', 'RESUME', 'COMPACT'):
            manifest = self.capture(module, [], event=event, successor_id='logical-two',
                                    ownership_confirmed=True, writers_stopped=True, checks_stopped=True,
                                    runtime={'owner': {'status': 'known'}, 'writers': [], 'checks': []})
        events = manifest['events']
        self.assertEqual([e['type'] for e in events], ['CHECKPOINT', 'HANDOVER', 'RESUME', 'COMPACT'])
        self.assertEqual(len({e['event_id'] for e in events}), 4)
        for event in events[1:]:
            self.assertEqual((event['source_id'], event['successor_id']), ('logical-one', 'logical-two'))

    def test_corrupt_payload_is_rejected_before_any_target_write(self) -> None:
        module = self.module()
        manifest = self.capture(module, self.dirty())
        source = self.portable(manifest)
        (source / 'staged.patch').write_bytes(b'corrupted patch\n')
        target = self.clone()
        before, index = self.inventory(target), self.raw_index(target)
        self.assert_error(module, 'corrupt-payload', module.restore, target, VERSION, 'target',
                          manifest['checkpoint_id'], source=source)
        self.assertEqual(self.inventory(target), before)
        self.assertEqual(self.raw_index(target), index)

    def test_missing_payload_and_incomplete_manifest_cannot_restore(self) -> None:
        module = self.module()
        manifest = self.capture(module, self.dirty())
        source = self.portable(manifest)
        target = self.clone()
        before = self.inventory(target)
        (source / 'unstaged.patch').unlink()
        self.assert_error(module, 'corrupt-payload', module.restore, target, VERSION, 'target',
                          manifest['checkpoint_id'], source=source)
        self.assertEqual(self.inventory(target), before)
        manifest['completeness']['portable'] = False
        (source / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        self.assert_error(module, 'incomplete-checkpoint', module.restore, target, VERSION, 'target',
                          manifest['checkpoint_id'], source=source)
        self.assertEqual(self.inventory(target), before)

    def test_wrong_base_and_plan_hash_refuse_restore_without_writing(self) -> None:
        module = self.module()
        manifest = self.capture(module, self.dirty())
        target = self.clone()
        self.git(target, '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
                 'commit', '-q', '--allow-empty', '-m', 'different head')
        before, index = self.inventory(target), self.raw_index(target)
        self.assert_error(module, 'wrong-base', module.restore, target, VERSION, 'target',
                          manifest['checkpoint_id'], source=self.portable(manifest))
        self.assertEqual(self.inventory(target), before)
        self.assertEqual(self.raw_index(target), index)
        target2 = self.clone('wrong-plan')
        (target2 / 'documentation/plans' / VERSION / 'plan.md').write_text('changed plan\n', encoding='utf-8')
        self.assert_error(module, 'wrong-plan', module.restore, target2, VERSION, 'target',
                          manifest['checkpoint_id'], source=self.portable(manifest))
        self.assertEqual((target2 / 'same.txt').read_bytes(), b'base\n')

    def test_partial_divergent_and_unrelated_dirty_target_refuse_restore(self) -> None:
        module = self.module()
        manifest = self.capture(module, self.dirty())
        for kind, path, contents in (('partial', 'staged.txt', b'only staged\n'),
                                     ('divergent', 'same.txt', b'other work\n'),
                                     ('unrelated', 'foreign.txt', b'do not overwrite\n')):
            with self.subTest(kind=kind):
                target = self.clone(kind)
                (target / path).write_bytes(contents)
                if kind == 'partial':
                    self.git(target, 'add', path)
                before, index = self.inventory(target), self.raw_index(target)
                self.assert_error(module, 'dirty-target', module.restore, target, VERSION, 'target',
                                  manifest['checkpoint_id'], source=self.portable(manifest))
                self.assertEqual(self.inventory(target), before)
                self.assertEqual(self.raw_index(target), index)

    def test_concurrent_source_write_is_incomplete_and_keeps_previous_checkpoint(self) -> None:
        module = self.module()
        owned = self.dirty()
        previous = self.capture(module, owned)
        published = (self.plans / 'run-state.json').read_bytes()
        write_payload = module._write_payload

        def write_then_drift(*args, **kwargs):
            result = write_payload(*args, **kwargs)
            (self.repo / 'same.txt').write_bytes(b'concurrent writer\n')
            return result

        with patch.object(module, '_write_payload', side_effect=write_then_drift):
            self.assert_error(module, 'concurrent-drift', self.capture, module, owned)
        self.assertEqual((self.repo / 'same.txt').read_bytes(), b'concurrent writer\n')
        self.assertEqual((self.plans / 'run-state.json').read_bytes(), published)
        self.assertTrue((self.portable(previous) / 'manifest.json').is_file())

    def test_ignored_destination_conflict_preserves_bytes_index_and_other_paths(self) -> None:
        (self.repo / '.gitignore').write_text('ignored.txt\n', encoding='utf-8')
        self.git(self.repo, 'add', '.gitignore')
        self.git(self.repo, 'commit', '-qm', 'ignore private local files')
        self.head = self.git(self.repo, 'rev-parse', 'HEAD').decode().strip()
        (self.repo / 'ignored.txt').write_bytes(b'owned checkpoint content\n')
        (self.repo / 'staged.txt').write_bytes(b'owned tracked change\n')
        module = self.module()
        manifest = self.capture(module, ['ignored.txt', 'staged.txt'])
        target = self.clone()
        private = b'private ignored target bytes\x00\xff\n'
        (target / 'ignored.txt').write_bytes(private)
        self.assertEqual(self.git(target, 'status', '--porcelain=v1'), b'')
        before, index = self.inventory(target), self.raw_index(target)
        self.assert_error(module, 'dirty-target', module.restore, target, VERSION, 'target',
                          manifest['checkpoint_id'], source=self.portable(manifest))
        self.assertEqual((target / 'ignored.txt').read_bytes(), private)
        self.assertEqual(self.inventory(target), before)
        self.assertEqual(self.raw_index(target), index)

    def test_interrupted_publish_keeps_original_tree_index_and_previous_manifest(self) -> None:
        module = self.module()
        owned = self.dirty()
        self.capture(module, owned)
        published = (self.plans / 'run-state.json').read_bytes()
        before, index = self.inventory(self.repo), self.raw_index(self.repo)
        with patch.object(module, '_publish', side_effect=OSError('interrupted atomic save')):
            self.assert_error(module, 'capture-incomplete', self.capture, module, owned)
        self.assertEqual((self.plans / 'run-state.json').read_bytes(), published)
        self.assertEqual(self.inventory(self.repo), before)
        self.assertEqual(self.raw_index(self.repo), index)

    def test_checkpoint_lock_and_git_index_lock_are_not_taken_over(self) -> None:
        module = self.module()
        from state_paths import resolve_paths
        paths = resolve_paths(self.repo, VERSION, 'physical-thread-one')
        paths.local.mkdir(parents=True)
        before, index = self.inventory(self.repo), self.raw_index(self.repo)
        for lock in (paths.local / 'checkpoint.lock', paths.gitdir / 'index.lock'):
            with self.subTest(lock=lock):
                lock.write_bytes(b'unknown owner; never remove\n')
                self.assert_error(module, 'locked', self.capture, module, [])
                self.assertEqual(lock.read_bytes(), b'unknown owner; never remove\n')
                lock.unlink()
        self.assertEqual(self.inventory(self.repo), before)
        self.assertEqual(self.raw_index(self.repo), index)

    def test_unmerged_index_and_submodule_cannot_be_complete(self) -> None:
        module = self.module()
        blob = self.git(self.repo, 'rev-parse', 'HEAD:same.txt').decode().strip()
        self.git(self.repo, 'update-index', '--force-remove', 'same.txt')
        stages = ''.join(f'100644 {blob} {stage}\tsame.txt\n' for stage in (1, 2, 3)).encode()
        subprocess.run(['git', '-C', str(self.repo), 'update-index', '--index-info'],
                       input=stages, check=True, capture_output=True, timeout=20)
        before, index = self.inventory(self.repo), self.raw_index(self.repo)
        self.assert_error(module, 'unsupported-state', self.capture, module, ['same.txt'])
        self.assertEqual(self.inventory(self.repo), before)
        self.assertEqual(self.raw_index(self.repo), index)
        other = self.clone('submodule')
        self.git(other, 'update-index', '--add', '--cacheinfo', f'160000,{self.head},submodule')
        index = self.raw_index(other)
        self.assert_error(module, 'unsupported-state', module.capture, other, VERSION, 'target',
                          self.state(), ['submodule'])
        self.assertEqual(self.raw_index(other), index)
        self.assertFalse((other / 'documentation/plans' / VERSION / 'run-state.json').exists())

    def test_legacy_patch_is_local_only_and_cannot_be_used_as_portable_checkpoint(self) -> None:
        module = self.module()
        gitdir = Path(self.git(self.repo, 'rev-parse', '--absolute-git-dir').decode().strip())
        legacy = gitdir / 'pipeline-work' / VERSION / 'U2.patch'
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b'old local patch without staged or owned inventory\n')
        manifest = self.capture(module, [])
        self.assertEqual(legacy.read_bytes(), b'old local patch without staged or owned inventory\n')
        target = self.clone()
        self.assert_error(module, 'legacy-local-only', module.restore, target, VERSION, 'target',
                          manifest['checkpoint_id'], source=legacy)
        self.assertEqual((target / 'same.txt').read_bytes(), b'base\n')

    def test_scope_escape_and_symlink_parent_are_rejected_without_external_reads(self) -> None:
        module = self.module()
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'secret').write_bytes(b'never capture\n')
        (self.repo / 'outside-link').symlink_to(outside, target_is_directory=True)
        for owned in (['../outside/secret'], [str(outside / 'secret')], ['outside-link/secret'],
                      ['.git/config'], ['documentation/plans/1.3.0/checkpoints/self']):
            with self.subTest(owned=owned):
                self.assert_error(module, 'invalid-scope', self.capture, module, owned)
        self.assertEqual((outside / 'secret').read_bytes(), b'never capture\n')
        self.assertFalse((self.plans / 'run-state.json').exists())

    def test_unknown_schema_or_phase_and_traversal_id_fail_closed(self) -> None:
        module = self.module()
        self.assert_error(module, 'invalid-state', module.capture, self.repo, VERSION,
                          'physical-thread-one', self.state('invented-phase'), [])
        manifest = self.capture(module, [])
        path = self.portable(manifest) / 'manifest.json'
        manifest['schema_version'] = 999
        path.write_text(json.dumps(manifest), encoding='utf-8')
        target = self.clone()
        self.assert_error(module, 'unsupported-schema', module.restore, target, VERSION, 'target',
                          manifest['checkpoint_id'], source=path.parent)
        self.assert_error(module, 'invalid-checkpoint-id', module.restore, target, VERSION,
                          'target', '../escape')

    def test_cli_capture_and_restore_return_json_and_nonzero_expected_errors(self) -> None:
        self.module()
        owned = self.dirty()
        state = self.base / 'state.json'
        state.write_text(json.dumps(self.state()), encoding='utf-8')
        common = ['--checkout', str(self.repo), '--version', VERSION, '--chat-key', 'physical-thread-one']
        args = [sys.executable, str(SCRIPT), 'capture', *common, '--state', str(state)]
        for name in owned:
            args.extend(['--owned', name])
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        result = subprocess.run(args, capture_output=True, text=True, env=env, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(result.stdout)
        target = self.clone()
        restore = [sys.executable, str(SCRIPT), 'restore', '--checkout', str(target), '--version', VERSION,
                   '--chat-key', 'target', '--checkpoint-id', manifest['checkpoint_id'],
                   '--source', str(self.portable(manifest))]
        result = subprocess.run(restore, capture_output=True, text=True, env=env, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'restored')
        (target / 'same.txt').write_bytes(b'divergent\n')
        result = subprocess.run(restore, capture_output=True, text=True, env=env, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)['error'], 'dirty-target')


if __name__ == '__main__':
    unittest.main()
