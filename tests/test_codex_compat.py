"""Isolated Codex compatibility regressions; no account or network required."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'dev-pipeline'
sys.dont_write_bytecode = True


def load(name, path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = load('guard', PLUGIN / 'hooks/guard.py')
formats = load('project_format', PLUGIN / 'skills/upgrade-docs/scripts/project_format.py')


class CodexCompatibility(unittest.TestCase):
    def test_package_syntax_and_agent_identity(self):
        for p in PLUGIN.rglob('*.json'):
            json.loads(p.read_text())
        for p in PLUGIN.rglob('*.py'):
            ast.parse(p.read_text())
        for p in PLUGIN.rglob('*.sh'):
            subprocess.run(['bash', '-n', str(p)], check=True, capture_output=True)
        for p in (PLUGIN / 'agents').glob('*.toml'):
            role = tomllib.loads(p.read_text())
            self.assertEqual(role['name'], p.stem)
            self.assertTrue(role['developer_instructions'])
            self.assertTrue(role['model'])

    def test_installed_version(self):
        expected = json.loads((PLUGIN / '.codex-plugin/plugin.json').read_text())['version']
        self.assertEqual(formats.installed(), expected)

    def test_patch_paths_including_move_relative_escape_and_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            main = Path(td) / 'main'; wt = main / 'worktrees/unit'
            wt.mkdir(parents=True)
            (wt / 'outside').symlink_to(main, target_is_directory=True)
            options = dict(worktree_root=str(wt), main_root=str(main))
            for header in ['Update File: ../../a.py', 'Delete File: ../../a.py',
                           'Add File: outside/a.py', 'Move to: ../../a.py']:
                patch = '*** Begin Patch\n*** ' + header + '\n*** End Patch'
                self.assertIsNotNone(guard.decide('apply_patch', {'command': patch}, str(wt), **options))
            for header in ['Update File: a.py', 'Add File: ../../documentation/plans/1.0/progress.md']:
                self.assertIsNone(guard.decide('apply_patch', {'command': '*** '+header}, str(wt), **options))
            self.assertIsNotNone(guard.decide('apply_patch', '*** Delete File: ../../a.py', str(wt), **options))

    def test_bash_canonical_hook_input(self):
        self.assertIsNotNone(guard.decide('Bash', {'command': 'git reset --hard'}, '/tmp'))
        self.assertIsNotNone(guard.decide('Bash', {'command': 'pytest && git commit -m ok'}, '/tmp'))
        self.assertIsNone(guard.decide('Bash', {'command': 'git status --short'}, '/tmp'))

    def test_real_worktree_hook_with_main_only_stamp(self):
        with tempfile.TemporaryDirectory() as td:
            main = Path(td) / 'main'; wt = Path(td) / 'wt'; home = Path(td) / 'codex'
            main.mkdir()
            def git(*args):
                subprocess.run(['git', '-C', str(main), *args], check=True, capture_output=True)
            git('init'); git('-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '--allow-empty', '-m', 'init')
            git('worktree', 'add', '-b', 'unit', str(wt))
            (main/'documentation').mkdir(); (main/'documentation/.dev-pipeline.json').write_text('{}')
            payload = {'tool_name': 'apply_patch', 'cwd': str(wt), 'tool_input': {'command':
                       '*** Begin Patch\n*** Add File: '+str(main/'bad.py')+'\n+x\n*** End Patch'}}
            result = subprocess.run(['sh', str(PLUGIN/'hooks/guard.sh')], input=json.dumps(payload),
                                    text=True, capture_output=True, env=dict(os.environ, CODEX_HOME=str(home)))
            decision = json.loads(result.stdout)['hookSpecificOutput']
            self.assertEqual(decision['permissionDecision'], 'deny')
            self.assertTrue((home/'dev-pipeline-feedback/.guard/main.jsonl').exists())
            self.assertFalse((main/'bad.py').exists())

    def test_progress_hook_uses_payload_cwd(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / 'project'; project.mkdir()
            target = project / 'documentation/plans/1.0/progress.md'
            target.parent.mkdir(parents=True); target.write_text('# Progress\n')
            payload = {'cwd': str(project), 'tool_name': 'apply_patch', 'tool_input': {'command':
                       '*** Begin Patch\n*** Update File: documentation/plans/1.0/progress.md\n@@\n-a\n+b\n*** End Patch'}}
            subprocess.run(['sh', str(PLUGIN/'hooks/progress-page.sh')], input=json.dumps(payload),
                           cwd=td, text=True, check=True, capture_output=True)
            self.assertTrue(target.with_suffix('.html').exists())

    def test_session_hook_payload_cwd(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)/'project'; (project/'documentation/plans/1.0').mkdir(parents=True)
            result = subprocess.run(['sh', str(PLUGIN/'hooks/session-start.sh')],
                                    input=json.dumps({'cwd': str(project), 'source': 'compact'}),
                                    cwd=td, text=True, capture_output=True, check=True)
            self.assertIn('open iteration 1.0', result.stdout)
            self.assertNotIn('mcp__ccd_session__', result.stdout)

    def test_installer_idempotence_conflicts_and_retired_switch(self):
        with tempfile.TemporaryDirectory() as td:
            env = dict(os.environ, CODEX_HOME=td)
            custom = Path(td)/'agents/impl-lite.toml'; custom.parent.mkdir(); custom.write_text('# user role\n')
            def run(*args):
                return subprocess.run(['bash', str(PLUGIN/'install-agents.sh'), *args],
                                      env=env, capture_output=True, text=True)
            self.assertEqual(run().returncode, 0)
            config = Path(td)/'config.toml'; first = config.read_text()
            self.assertEqual(run().returncode, 0)
            self.assertEqual(config.read_text(), first)
            tomllib.loads(first)
            self.assertEqual(custom.read_text(), '# user role\n')
            self.assertEqual(len(list(custom.parent.glob('*.toml'))), 33)
            self.assertEqual(run('--autonomous-chats').returncode, 2)
            self.assertEqual(config.read_text(), first)
            self.assertEqual(run('--invalid').returncode, 2)

    def test_legacy_approval_cleanup_preserves_user_settings(self):
        with tempfile.TemporaryDirectory() as td:
            config = Path(td)/'config.toml'
            keep = '[plugins."custom".tools.x]\napproval_mode = "approve"\n'
            legacy = '# dev-pipeline: stage chats without approval (install-agents.sh --autonomous-chats)\n[plugins."codex-app-tools@openai-bundled".mcp_servers.codex_app.tools.create_thread]\napproval_mode = "approve"\n'
            config.write_text(keep+legacy)
            subprocess.run(['bash', str(PLUGIN/'install-agents.sh'), '--no-autonomous-chats'],
                           env=dict(os.environ, CODEX_HOME=td), check=True, capture_output=True)
            self.assertEqual(config.read_text(), keep)
            self.assertEqual(config.with_name(config.name+'.dev-pipeline.bak').read_text(), keep+legacy)


if __name__ == '__main__':
    unittest.main()
