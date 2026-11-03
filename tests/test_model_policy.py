"""Codex roles and new stage chats use explicit task-based model settings."""
import importlib.util
import json
from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]/'dev-pipeline'


class ModelPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT/'models.json').read_text())
        self.roles = {p.stem:tomllib.loads(p.read_text()) for p in (ROOT/'agents').glob('*.toml')}

    def test_each_role_is_explicit_and_generated_toml_matches(self):
        names = {key.removeprefix('role:') for key in self.policy if key.startswith('role:')}
        self.assertEqual(names, set(self.roles), 'new roles require an explicit Codex setting')
        for name,role in self.roles.items():
            with self.subTest(role=name):
                selected = self.policy['role:'+name]
                self.assertEqual(role['model'],selected['model'])
                self.assertEqual(role['model_reasoning_effort'],selected['effort'])

    def test_every_stage_has_a_valid_chat_profile(self):
        spec = importlib.util.spec_from_file_location('model_policy_sessions',ROOT/'skills/pipeline/scripts/subsessions.py')
        stages = importlib.util.module_from_spec(spec);spec.loader.exec_module(stages)
        self.assertEqual(set(self.policy['_stages']),set(stages.STAGES)|{'parent'})
        for profile in list(self.policy['_stages'].values()) + [self.policy['role:'+n] for n in self.roles]:
            self.assertIn(profile['model'],{'gpt-6.1-sol','gpt-6-luna'})
            self.assertIn(profile['effort'],{'low','medium','high','xhigh','max'})

    def test_difficulty_escalation_increases_reasoning_without_affecting_mechanics(self):
        order = {'low':0,'medium':1,'high':2,'xhigh':3,'max':4}
        def effort(role):return order[self.roles[role]['model_reasoning_effort']]
        self.assertLess(effort('impl-lite'),effort('impl-medium'))
        self.assertLessEqual(effort('impl-medium'),effort('impl-hard'))
        self.assertLess(effort('impl-hard'),effort('impl-critical'))
        self.assertEqual(self.roles['mechanical-worker']['model'],'gpt-6-luna')
        self.assertLess(effort('doc-typist'),effort('srs-author'))

    def test_increased_effort_does_not_silently_use_a_different_model(self):
        content_roles=['impl-medium','impl-hard','impl-critical','impl-ui','srs-author',
                       'screen-writer','docs-consistency-checker','ui-test-runner']
        for role in content_roles:
            self.assertEqual(self.roles[role]['model'],'gpt-6.1-sol')
            self.assertIn(self.roles[role]['model_reasoning_effort'],{'high','xhigh'})


if __name__ == '__main__':
    unittest.main()
