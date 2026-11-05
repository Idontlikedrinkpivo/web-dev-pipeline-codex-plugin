"""Small iterations have a validated marker rather than a synthetic plan."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / 'dev-pipeline/skills/pipeline/scripts'
VERSION = '1.3.1'
sys.dont_write_bytecode = True


class SmallCheckpoints(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.repo = self.base / 'source'
        self.repo.mkdir()
        self.git(self.repo, 'init', '-q', '-b', 'main')
        self.git(self.repo, 'config', 'user.name', 'Test')
        self.git(self.repo, 'config', 'user.email', 'test@example.com')
        for name in ('same.txt', 'staged.txt'):
            (self.repo / name).write_bytes(b'base\n')
        self.git(self.repo, 'add', '.')
        self.git(self.repo, 'commit', '-qm', 'base')
        result = subprocess.run([sys.executable, str(SCRIPTS / 'open_iteration.py'),
                                 VERSION, str(self.repo), '--small'], capture_output=True,
                                text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.plans = self.repo / 'documentation/plans' / VERSION
        self.marker = self.plans / 'iteration.json'
        self.assertFalse((self.plans / 'plan.md').exists())
        self.metadata = json.loads(self.marker.read_text(encoding='utf-8'))
        self.git(self.repo, 'add', str(self.marker))
        self.git(self.repo, 'commit', '-qm', 'record small iteration identity')
        self.head = self.git(self.repo, 'rev-parse', 'HEAD').decode().strip()
        sys.path.insert(0, str(SCRIPTS))
        self.addCleanup(sys.path.remove, str(SCRIPTS))
        spec = importlib.util.spec_from_file_location('small_checkpoint', SCRIPTS / 'checkpoint.py')
        assert spec is not None and spec.loader is not None
        self.checkpoint = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.checkpoint
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(self.checkpoint)

    def git(self, repo: Path, *args: str) -> bytes:
        return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True,
                              env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'), timeout=20).stdout

    def state(self) -> dict:
        return {'run_id': 'small-run', 'source_id': 'small-source', 'unit': 'chat-1',
                'phase': 'unit', 'next_action': 'review small change',
                'review': {'base': self.head, 'head': self.head}, 'low_batches': [],
                'findings': [], 'decisions': [],
                'reports': {name: '# Saved small iteration\n' for name in
                            ('work-run.md', 'resume.md', 'context-handover.md')}}

    def capture(self) -> dict:
        return self.checkpoint.capture(self.repo, VERSION, 'physical-source', self.state(),
                                       ['same.txt', 'staged.txt', 'new.bin'])

    def dirty(self) -> None:
        (self.repo / 'same.txt').write_bytes(b'staged version\n')
        (self.repo / 'staged.txt').write_bytes(b'only staged\n')
        self.git(self.repo, 'add', 'same.txt', 'staged.txt')
        (self.repo / 'same.txt').write_bytes(b'unstaged version\n')
        (self.repo / 'new.bin').write_bytes(b'new\x00\xff\x80\n')

    def clone(self, name: str) -> Path:
        target = self.base / name
        self.git(self.repo, 'clone', '-q', '--no-local', str(self.repo), str(target))
        return target

    def inventory(self, repo: Path) -> tuple:
        names = ['same.txt', 'staged.txt', 'new.bin', f'documentation/plans/{VERSION}/iteration.json']
        return ([(name, (repo / name).read_bytes() if (repo / name).exists() else None) for name in names],
                self.git(repo, 'ls-files', '--stage', '-z'),
                self.git(repo, 'status', '--porcelain=v1', '-z', '--', *names))

    def index(self, repo: Path) -> bytes:
        gitdir = Path(self.git(repo, 'rev-parse', '--absolute-git-dir').decode().strip())
        return (gitdir / 'index').read_bytes()

    def restore(self, target: Path, manifest: dict) -> dict:
        return self.checkpoint.restore(target, VERSION, 'physical-target', manifest['checkpoint_id'],
                                       source=self.plans / 'checkpoints' / manifest['checkpoint_id'])

    def assert_error(self, code: str, call, *args) -> None:
        with self.assertRaises(self.checkpoint.CheckpointError) as caught:
            call(*args)
        self.assertEqual(caught.exception.code, code)

    def test_small_open_capture_restore_preserves_staged_unstaged_and_new_bytes(self) -> None:
        self.dirty()
        before, index = self.inventory(self.repo), self.index(self.repo)
        manifest = self.capture()
        self.assertEqual(self.inventory(self.repo), before)
        self.assertEqual(self.index(self.repo), index)
        self.assertEqual(manifest['plan_source'], 'iteration.json:small-identity-v1')
        self.assertRegex(manifest['plan_sha256'], r'^[0-9a-f]{64}$')
        target = self.clone('target')
        self.assertEqual(self.restore(target, manifest)['status'], 'restored')
        self.assertEqual(self.inventory(target), before)
        self.assertEqual(self.git(target, 'show', ':same.txt'), b'staged version\n')
        self.assertEqual(self.restore(target, manifest)['status'], 'already-restored')
        self.assertFalse((self.plans / 'plan.md').exists())
        self.assertFalse((target / 'documentation/plans' / VERSION / 'plan.md').exists())

    def test_missing_malformed_or_invalid_small_identity_cannot_capture(self) -> None:
        wrong = []
        for key, value in (('schema_version', 999), ('mode', 'normal'), ('version', '9.9.9'),
                           ('chat_id', 'physical/invalid'), ('started_at', '2026-11-05'),
                           ('base_head', '0' * 40)):
            wrong.append(dict(self.metadata, **{key: value}))
        unrelated = self.git(self.repo, 'commit-tree', self.head + '^{tree}', '-m', 'unrelated').decode().strip()
        wrong.append(dict(self.metadata, base_head=unrelated))
        for number, value in enumerate([None, '{malformed', *wrong]):
            with self.subTest(case=number):
                if value is None:
                    self.marker.unlink()
                else:
                    self.marker.write_text(value if isinstance(value, str) else json.dumps(value), encoding='utf-8')
                before, index = self.inventory(self.repo), self.index(self.repo)
                self.assert_error('invalid-state', self.capture)
                self.assertEqual(self.inventory(self.repo), before)
                self.assertEqual(self.index(self.repo), index)
                self.assertFalse((self.plans / 'run-state.json').exists())
                self.assertFalse((self.plans / 'plan.md').exists())

    def test_wrong_small_identity_is_rejected_before_restore_writes(self) -> None:
        self.dirty()
        manifest = self.capture()
        for number, change in enumerate(({'chat_id': 'chat-2'}, {'base_head': self.head},
                                         {'started_at': '2026-11-01T00:00:00Z'}, {'mode': 'normal'})):
            with self.subTest(change=change):
                target = self.clone('wrong-' + str(number))
                marker = target / 'documentation/plans' / VERSION / 'iteration.json'
                marker.write_text(json.dumps(dict(self.metadata, **change)), encoding='utf-8')
                before, index = self.inventory(target), self.index(target)
                self.assert_error('wrong-plan', self.restore, target, manifest)
                self.assertEqual(self.inventory(target), before)
                self.assertEqual(self.index(target), index)

    def test_mutable_evidence_keeps_identity_but_target_dirt_and_head_still_block(self) -> None:
        self.dirty()
        manifest = self.capture()
        updated = dict(self.metadata, result={'scope': ['same.txt'], 'head': self.head,
                                             'unit_review': {'status': 'PASS'}},
                       source_scope={'head': self.head, 'paths': ['same.txt']})
        target = self.clone('dirty-evidence')
        (target / 'documentation/plans' / VERSION / 'iteration.json').write_text(json.dumps(updated), encoding='utf-8')
        before, index = self.inventory(target), self.index(target)
        self.assert_error('dirty-target', self.restore, target, manifest)
        self.assertEqual(self.inventory(target), before)
        self.assertEqual(self.index(target), index)
        self.marker.write_text(json.dumps(updated), encoding='utf-8')
        self.git(self.repo, 'add', str(self.marker))
        self.git(self.repo, 'commit', '-qm', 'record mutable small evidence', '--only', '--', str(self.marker))
        self.head = self.git(self.repo, 'rev-parse', 'HEAD').decode().strip()
        later = self.capture()
        self.assertEqual(later['plan_source'], manifest['plan_source'])
        self.assertEqual(later['plan_sha256'], manifest['plan_sha256'])
        target = self.clone('later-head')
        before, index = self.inventory(target), self.index(target)
        self.assert_error('wrong-base', self.restore, target, manifest)
        self.assertEqual(self.inventory(target), before)
        self.assertEqual(self.index(target), index)


if __name__ == '__main__':
    unittest.main()
