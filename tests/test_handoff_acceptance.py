"""U27: local-origin handoffs prove Git/state, not document or Figma quality."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'dev-pipeline/skills/pipeline/scripts'
VERSION = '1.3.0'
BRANCH = 'iteration/' + VERSION
PLANS = 'documentation/plans/' + VERSION
SRS = 'documentation/requirements/srs/srs.md'
ARCH = 'documentation/architecture/architecture.md'
REGISTER = 'documentation/ui/mockups.md'
SPEC = 'documentation/ui/screen-specs/S-1-home.md'
SITE = 'documentation/_web-docs/index.html'
REPORTS = ('work-run.md', 'resume.md', 'context-handover.md')
sys.path.insert(0, str(SCRIPTS))
import subsessions  # noqa: E402


class HandoffAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix='handoff-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_TERMINAL_PROMPT='0', GIT_EDITOR='true',
                        PYTHONDONTWRITEBYTECODE='1', CODEX_HOME=str(self.base / 'codex-home'),
                        CODEX_THREAD_ID='fixture-thread')
        self.origin = self.base / 'origin.git'
        self.run_command(['git', 'init', '-q', '--bare', '--initial-branch=' + BRANCH, str(self.origin)])
        self.author = self.base / 'author'
        self.author.mkdir()
        self.git(self.author, 'init', '-q', '-b', BRANCH)
        self.identity(self.author)
        self.git(self.author, 'remote', 'add', 'origin', str(self.origin))
        self.write(self.author, PLANS + '/plan.md', '# Fixture plan\n\n### U1. Handoff\n')
        self.write(self.author, 'owned.bin', b'\x00base\xff')
        self.write(self.author, 'foreign.txt', 'unchanged\n')
        self.commit(self.author, 'fixture baseline')
        self.push(self.author)

    def run_command(self, args: list[str], *, cwd: Path | None = None,
                    data: str | None = None, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(args, cwd=cwd, env=self.env, input=data,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def git(self, repo: Path, *args: str) -> str:
        return self.run_command(['git', '-C', str(repo), *args]).stdout.strip()

    def identity(self, repo: Path) -> None:
        self.git(repo, 'config', 'user.name', 'Fixture')
        self.git(repo, 'config', 'user.email', 'fixture@example.invalid')
        self.git(repo, 'config', 'core.autocrlf', 'false')

    def clone(self, name: str) -> Path:
        repo = self.base / name
        self.run_command(['git', 'clone', '-q', '--no-local', str(self.origin), str(repo)])
        self.identity(repo)
        return repo

    def write(self, repo: Path, name: str, content: str | bytes) -> None:
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding='utf-8')

    def document(self, repo: Path, name: str, body: str) -> None:
        metadata = ('title: Fixture SRS\ndate: 2026-11-05\n' if name == SRS
                    else 'sources: [stated-directly]\n')
        if name == 'documentation/db/schema.md':
            metadata += 'migration: 0\n'
        self.write(repo, name, '---\n' + metadata + 'updated: 2026-11-05\nversion: 1.3.0\n---\n'
                   '# Fixture\n\n' + body + '\n\n## Журнал изменений\n\n'
                   '| Версия | Дата | Изменение | Тип | Кого затрагивает |\n'
                   '|---|---|---|---|---|\n'
                   '| 1.3.0 | 2026-11-05 | первый выпуск | — | fixture |\n')

    def commit(self, repo: Path, message: str) -> None:
        self.git(repo, 'add', '.')
        self.git(repo, 'commit', '-qm', message)

    def push(self, repo: Path, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = self.run_command([sys.executable, str(SCRIPTS / 'push_branch.py'), str(repo)],
                                  expected=expected)
        if expected == 0:
            remote = self.git(repo, 'ls-remote', '--heads', 'origin', 'refs/heads/' + BRANCH).split()[0]
            self.assertEqual(remote, self.git(repo, 'rev-parse', 'HEAD'))
            self.assertEqual(self.git(repo, 'status', '--porcelain', '--', PLANS), '')
        return result

    def report(self, repo: Path, next_action: str) -> None:
        for name in REPORTS:
            self.write(repo, PLANS + '/' + name, '# Portable fixture\n' + next_action + '\n')

    def recipient(self, name: str, expected_files: tuple[str, ...], stage: str) -> Path:
        repo = self.clone(name)
        for path in (*expected_files, *(PLANS + '/' + report for report in REPORTS)):
            self.assertTrue((repo / path).is_file(), path)
        # An old author is merely document history. This CLI authorizes fixtures only;
        # no host chat is created. Proposal alone must not grant set permission.
        cli = [sys.executable, str(SCRIPTS / 'subsessions.py'), str(repo), VERSION]
        self.run_command([*cli, 'plan', stage])
        unauthorized = subprocess.run([*cli, 'set', '1', 'fixture-child'], env=self.env,
                                      capture_output=True, text=True, timeout=20)
        self.assertNotEqual(unauthorized.returncode, 0)
        self.run_command([*cli, 'authorize', stage])
        self.run_command([*cli, 'set', '1', 'fixture-child'])
        shown = self.run_command([*cli, 'show']).stdout
        paths = subsessions.resolve_paths(repo, VERSION, 'fixture-thread')
        _, rows = subsessions.read(paths.local / 'sessions.md')
        self.assertEqual([(row['stage'], row['authorized'], row['id']) for row in rows],
                         [(stage, True, 'fixture-child')])
        title = subsessions.rows_for(VERSION, stage)[0]['title']
        self.assertEqual(rows[0]['title'], title)
        self.assertIn(title, shown)
        self.assertIn('fixture-child', shown)
        return repo

    def finish_specs(self, repo: Path) -> None:
        self.document(repo, SPEC, 'S-1 references fixture frame M-1 in mockups.md.')
        self.commit(repo, 'fixture screen spec from registered mockup')
        self.report(repo, 'Next: consistency, then implementation; previous author: participant A.')
        self.push(repo)
        recipient = self.recipient('user', (SRS, ARCH, REGISTER, SPEC), 'check')
        cli = [sys.executable, str(SCRIPTS / 'subsessions.py'), str(recipient), VERSION]
        self.run_command([*cli, 'plan', 'check', 'work'])
        self.run_command([*cli, 'authorize', 'check', 'work'])
        self.assertIn(subsessions.rows_for(VERSION, 'work')[0]['title'],
                      self.run_command([*cli, 'show']).stdout)
        paths = subsessions.resolve_paths(recipient, VERSION, 'fixture-thread')
        _, rows = subsessions.read(paths.local / 'sessions.md')
        self.assertEqual([row['stage'] for row in rows if row['authorized']], ['check', 'work'])
        self.assertIn('implementation', (recipient / PLANS / 'work-run.md').read_text(encoding='utf-8'))

    def test_sequential_human_handoff_through_architecture_mockups_specs_and_user(self) -> None:
        self.document(self.author, 'documentation/requirements/business-requirements/business-requirements.md',
                      'Fixture business requirement.')
        self.document(self.author, SRS, 'FR-1 fixture requirement.')
        self.document(self.author, 'documentation/db/schema.md', 'Fixture data model.')
        self.write(self.author, 'documentation/api/openapi.yaml',
                   'openapi: 3.0.3\ninfo:\n  title: Fixture API\n  version: 1.3.0\n'
                   '  x-changelog:\n    - version: 1.3.0\n      change: initial fixture\n'
                   '      type: adds\npaths: {}\n')
        self.document(self.author, ARCH, 'Architecture by participant A.')
        self.document(self.author, 'documentation/architecture/domain.md', 'Fixture domain model.')
        self.document(self.author, 'documentation/architecture/scenarios/fixture/UC-1.md',
                      'UC-1 fixture scenario.')
        self.commit(self.author, 'fixture documents through architecture')
        self.report(self.author, 'Next: designer may choose design.')
        self.push(self.author)
        designer = self.recipient('designer', (SRS, ARCH, 'documentation/db/schema.md',
                                  'documentation/api/openapi.yaml', 'documentation/architecture/domain.md'), 'design')
        self.document(designer, REGISTER, 'M-1 | S-1 | fixture-frame-1 | participant Designer')
        self.commit(designer, 'fixture mockup register')
        self.report(designer, 'Next: participant A may choose screen specs.')
        self.push(designer)
        self.git(self.author, 'pull', '--ff-only')
        self.assertTrue((self.author / REGISTER).exists())
        self.finish_specs(self.author)

    def parallel_fixture(self) -> Path:
        self.document(self.author, SRS, 'FR-1 fixture requirement.')
        self.write(self.author, SITE, 'base generated site\n')
        self.commit(self.author, 'fixture SRS before parallel work')
        self.report(self.author, 'Next: technical documents and design in parallel.')
        self.push(self.author)
        return self.recipient('designer', (SRS,), 'design')

    def test_parallel_human_handoff_rebuilds_generated_conflict_from_combined_sources(self) -> None:
        designer = self.parallel_fixture()
        self.document(self.author, ARCH, 'TECHNICAL-SOURCE-UNIQUE')
        self.write(self.author, SITE, 'technical generated site\n')
        self.commit(self.author, 'fixture technical documents')
        self.push(self.author)
        self.document(designer, REGISTER, 'M-1 | S-1 | DESIGN-SOURCE-UNIQUE')
        self.write(designer, SITE, 'designer generated site\n')
        self.commit(designer, 'fixture parallel mockup register')
        self.push(designer)
        combined = self.clone('combined')
        self.assertIn('TECHNICAL-SOURCE-UNIQUE', (combined / ARCH).read_text(encoding='utf-8'))
        self.assertIn('DESIGN-SOURCE-UNIQUE', (combined / REGISTER).read_text(encoding='utf-8'))
        html = '\n'.join(path.read_text(encoding='utf-8') for path in
                         (combined / 'documentation/_web-docs').rglob('*.html'))
        self.assertIn('TECHNICAL-SOURCE-UNIQUE', html)
        self.assertIn('DESIGN-SOURCE-UNIQUE', html)
        self.assertNotIn('<<<<<<<', html)
        self.assertEqual(self.git(designer, 'status', '--porcelain'), '')
        self.git(self.author, 'pull', '--ff-only')
        self.finish_specs(self.author)

    def test_parallel_source_conflict_stops_preserving_remote_local_head_and_unowned_edit(self) -> None:
        designer = self.parallel_fixture()
        self.document(self.author, SRS, 'FR-1 author decision.')
        self.commit(self.author, 'fixture author source change')
        self.push(self.author)
        remote = self.git(self.author, 'rev-parse', 'HEAD')
        self.document(designer, SRS, 'FR-1 conflicting designer decision.')
        self.commit(designer, 'fixture conflicting source change')
        local = self.git(designer, 'rev-parse', 'HEAD')
        self.write(designer, 'foreign.txt', 'unowned local work\n')
        before = self.git(designer, 'status', '--porcelain')
        self.push(designer, expected=2)
        self.assertEqual(self.git(designer, 'rev-parse', 'HEAD'), local)
        self.assertEqual(self.git(designer, 'status', '--porcelain'), before)
        self.assertEqual((designer / 'foreign.txt').read_text(), 'unowned local work\n')
        self.assertEqual(self.git(designer, 'ls-remote', '--heads', 'origin', 'refs/heads/' + BRANCH).split()[0], remote)
        gitdir = Path(self.git(designer, 'rev-parse', '--absolute-git-dir'))
        self.assertFalse((gitdir / 'rebase-merge').exists())
        self.assertFalse((gitdir / 'rebase-apply').exists())

    def state(self, repo: Path, phase: str) -> dict[str, object]:
        head = self.git(repo, 'rev-parse', 'HEAD')
        return {'run_id': 'fixture-run', 'source_id': 'logical-author', 'unit': 'U1',
                'phase': phase, 'next_action': 'continue ' + phase + '; final checks and whole review remain',
                'review': {'base': head, 'head': head},
                'low_batches': [{'units': ['U1'], 'base': head, 'head': head, 'findings': ['F1']}],
                'findings': [{'id': 'F1', 'status': 'open', 'attempts': ['first fix']}],
                'decisions': ['Only agreed mandatory checks remain.'],
                'reports': {name: '# Saved fixture\nContinue ' + phase + '; F1 open.\n' for name in REPORTS}}

    def capture(self, repo: Path, state: dict[str, object], owned: tuple[str, ...] = (),
                event: str = 'CHECKPOINT') -> dict[str, object]:
        state_file = self.base / 'capture-state.json'
        state_file.write_text(json.dumps(state), encoding='utf-8')
        runtime = self.base / 'runtime.json'
        runtime.write_text(json.dumps({'stage': 'work', 'owner': {'status': 'known'},
                                       'writers': [], 'checks': []}), encoding='utf-8')
        args = [sys.executable, str(SCRIPTS / 'checkpoint.py'), 'capture', '--checkout', str(repo),
                '--version', VERSION, '--chat-key', 'fixture-thread', '--state', str(state_file),
                '--runtime', str(runtime), '--event', event]
        for path in owned:
            args += ['--owned', path]
        if event == 'HANDOVER':
            args += ['--successor-id', 'logical-recipient', '--ownership-confirmed',
                     '--writers-stopped', '--checks-stopped']
        return json.loads(self.run_command(args).stdout)

    def test_partial_binary_handoff_restores_owned_layers_from_clone_without_sender(self) -> None:
        self.write(self.author, 'owned.bin', b'\x00staged\xff')
        self.git(self.author, 'add', 'owned.bin')
        self.write(self.author, 'owned.bin', b'\x00unstaged\x80')
        self.write(self.author, 'new.bin', b'\x00new\xff')
        self.write(self.author, 'foreign.txt', 'private unowned change\n')
        before = self.git(self.author, 'status', '--porcelain', '--', 'owned.bin', 'new.bin')
        state = self.state(self.author, 'low-fix')
        manifest = self.capture(self.author, state, ('owned.bin', 'new.bin'), 'HANDOVER')
        self.git(self.author, 'add', '--', PLANS)
        self.git(self.author, 'commit', '-qm', 'fixture portable partial handoff', '--only', '--', PLANS)
        self.push(self.author)
        target = self.clone('partial-recipient')
        saved = json.loads((target / PLANS / 'run-state.json').read_text())
        for key in ('phase', 'next_action', 'review', 'low_batches', 'findings', 'decisions'):
            self.assertEqual(saved[key], state[key])
        exported = self.base / 'recipient-payload'
        shutil.copytree(target / PLANS / 'checkpoints' / str(manifest['checkpoint_id']), exported)
        self.assertNotIn(b'private unowned change', b''.join(p.read_bytes() for p in exported.rglob('*') if p.is_file()))
        shutil.rmtree(self.author)
        self.git(target, 'checkout', '-q', '--detach', str(manifest['head']))
        args = [sys.executable, str(SCRIPTS / 'checkpoint.py'), 'restore', '--checkout', str(target),
                '--version', VERSION, '--chat-key', 'recipient', '--checkpoint-id', str(manifest['checkpoint_id']),
                '--source', str(exported)]
        self.assertEqual(json.loads(self.run_command(args).stdout)['status'], 'restored')
        self.assertEqual((target / 'owned.bin').read_bytes(), b'\x00unstaged\x80')
        staged = subprocess.run(['git', '-C', str(target), 'show', ':owned.bin'], env=self.env,
                                capture_output=True, check=True, timeout=20).stdout
        self.assertEqual(staged, b'\x00staged\xff')
        self.assertEqual((target / 'new.bin').read_bytes(), b'\x00new\xff')
        self.assertEqual((target / 'foreign.txt').read_text(), 'unchanged\n')
        self.assertEqual(self.git(target, 'status', '--porcelain', '--', 'owned.bin', 'new.bin'), before)
        self.assertEqual(json.loads(self.run_command(args).stdout)['status'], 'already-restored')

    def test_low_and_whole_review_continuation_with_simulated_compaction_hook(self) -> None:
        for phase in ('low-fix', 'whole-review', 'review-fix'):
            with self.subTest(phase=phase):
                state = self.state(self.author, phase)
                self.capture(self.author, state)
                manifest = self.capture(self.author, state, event='COMPACT')
                for key in ('phase', 'next_action', 'review', 'low_batches', 'findings', 'decisions'):
                    self.assertEqual(manifest[key], state[key])
                self.assertEqual(manifest['events'][-1]['type'], 'COMPACT')
                self.assertFalse(manifest['paused'])
                hook = self.run_command(['sh', str(ROOT / 'dev-pipeline/hooks/session-start.sh')],
                                        cwd=self.author, data=json.dumps({'cwd': str(self.author),
                                        'source': 'compact', 'thread_id': 'fixture-thread'}))
                self.assertIn('in this stage (work,', hook.stdout)
                saved = json.loads((self.author / PLANS / 'run-state.json').read_text())
                self.assertEqual(saved['next_action'], state['next_action'])


if __name__ == '__main__':
    unittest.main()
