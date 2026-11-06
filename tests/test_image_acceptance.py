"""Acceptance regressions: real tar bytes, scan gates, isolation and upgrade detection."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / 'dev-pipeline/skills'
sys.dont_write_bytecode = True

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec); spec.loader.exec_module(obj)
    return obj

preflight = module('image_preflight', SKILLS / 'deploy-topology/scripts/image_preflight.py')
scan = module('scan_gate', SKILLS / 'deploy-topology/scripts/trivy_images.py')
sys.path.insert(0, str(SKILLS / 'upgrade-docs/scripts'))
upgrade = module('project_format', SKILLS / 'upgrade-docs/scripts/project_format.py')

class Contents(unittest.TestCase):
    def inspect(self, files):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as archive:
            for name, text in files.items():
                data = text.encode(); member = tarfile.TarInfo(name); member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        stream.seek(0)
        with tarfile.open(fileobj=stream) as archive:
            return preflight.inspect_tar(archive, ['/app', '/usr/share/nginx/html'])

    def test_runtime_with_migrations_and_base_ca(self):
        self.assertEqual(self.inspect({'app/main.py':'pass', 'app/documentation/db/migrations/0001.sql':'select 1;',
                                      'etc/ssl/certs/ca.pem':'public root', 'app/node_modules/pkg/LICENSE.md':'licence'}), [])

    def test_each_forbidden_file(self):
        for name in ['.env.example','Dockerfile','docker-compose.test.yml','src/unit.test.js','tests/test.py',
                     'config.yaml','key.pem','src/main.tsx','README.md','documentation/architecture.md']:
            with self.subTest(name=name): self.assertTrue(self.inspect({'app/'+name:'bad'}))

    def test_cdn_and_upstream(self):
        self.assertTrue(self.inspect({'usr/share/nginx/html/app.js':'fetch("//cdn.jsdelivr.net/pkg")'}))
        self.assertTrue(self.inspect({'etc/nginx/templates/upstream.conf.template':'upstream backend { server backend:8000; }'}))
        self.assertEqual(self.inspect({'etc/nginx/templates/upstream.conf.template':'resolver 127.0.0.11;\nmap $host $up { default "http://backend:8000"; }'}), [])

    def test_prometheus_and_noisy_logs(self):
        self.assertTrue(preflight.prometheus('# TYPE app_build_info gauge\napp_build_info{version="1"} 1\n'))
        for body in ['', '<html># TYPE</html>', '# TYPE fake gauge', 'broken stuff', 'x not-a-number']:
            self.assertFalse(preflight.prometheus(body))
        self.assertFalse(preflight.quiet_logs('GET /health/live 200'))
        self.assertFalse(preflight.quiet_logs(json.dumps({'level':'info','msg':'GET /metrics','status':200})))
        self.assertTrue(preflight.quiet_logs(json.dumps({'level':'error','msg':'GET /health/ready','status':503})))
        self.assertTrue(preflight.quiet_logs(json.dumps({'level':'debug','msg':'GET /metrics'})))

class Isolation(unittest.TestCase):
    def config(self):
        return {'name':'existing', 'volumes':{'db':{'name':'existing_db'}}, 'networks':{'default':{'name':'existing_default'}},
                'services':{'backend':{'image':'api:test','build':{'context':'.'}, 'read_only':True,
                            'cap_drop':['ALL'],'security_opt':['no-new-privileges'], 'tmpfs':['/tmp'],
                            'ports':[{'target':8000,'published':'8000'}]}}}
    def test_only_new_resources_and_random_local_ports(self):
        cfg = preflight.isolate(self.config(), ['backend'], {'backend':[8000]})
        self.assertNotIn('name',cfg); self.assertNotIn('name',cfg['volumes']['db'])
        svc=cfg['services']['backend']; self.assertNotIn('build',svc); self.assertEqual(svc['user'],'5000:5000')
        self.assertEqual(svc['ports'][0]['published'],'0'); self.assertEqual(svc['ports'][0]['host_ip'],'127.0.0.1')
    def test_reject_unsafe_stands(self):
        for change in ({'container_name':'owner'}, {'privileged':True}, {'network_mode':'host'}, {'read_only':False},
                       {'cap_add':['SYS_ADMIN']}, {'volumes':[{'type':'bind','source':'/home','target':'/data'}]}):
            cfg=self.config(); cfg['services']['backend'].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError): preflight.isolate(cfg,['backend'],{})
        cfg=self.config(); cfg['volumes']['db']['external']=True
        with self.assertRaises(ValueError): preflight.isolate(cfg,['backend'],{})

class ScanGate(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)
        self.report={'SchemaVersion':2,'ArtifactType':'container_image','ArtifactName':'api:test','ArtifactID':'sha256:abc',
                     'Results':[{'Target':'app','Vulnerabilities':[],'Secrets':[]}]}
        self.manifest={'expected':['api:test'],'records':[{'image':'api:test','digest':'sha256:abc','report':'report.json','exit_code':0}],
                       'scanners':['vuln','secret'],'severities':'ALL'}
    def gate(self, risks=None):
        (self.root/'report.json').write_text(json.dumps(self.report))
        path=self.root/'trivy-manifest.json';path.write_text(json.dumps(self.manifest))
        risk_path=None
        if risks is not None:
            risk_path=self.root/'risks.json';risk_path.write_text(json.dumps(risks))
        return scan.gate(path,risk_path)
    def test_clean_and_high(self):
        self.assertEqual(self.gate(),0)
        self.report['Results'][0]['Vulnerabilities']=[{'VulnerabilityID':'CVE-X','Severity':'HIGH','PkgName':'pkg'}]
        self.assertEqual(self.gate(),0)
    def test_any_secret_blocks(self):
        for severity in ['UNKNOWN','LOW','MEDIUM','HIGH','CRITICAL']:
            self.report['Results'][0]['Secrets']=[{'RuleID':'key','Severity':severity}]
            with self.subTest(severity=severity): self.assertEqual(self.gate(),2)
    def test_critical_requires_exact_unexpired_approved_risk(self):
        self.report['Results'][0]['Vulnerabilities']=[{'VulnerabilityID':'CVE-X','Severity':'CRITICAL','PkgName':'pkg'}]
        self.assertEqual(self.gate(),2)
        risk={'digest':'sha256:abc','id':'CVE-X','package':'pkg','target':'app','approved_by':'test-owner',
              'reason':'fixture only','accepted_on':'2020-01-01','expires':'2099-01-01'}
        self.assertEqual(self.gate([risk]),0)
        self.assertEqual(self.gate([dict(risk,digest='sha256:other')]),2)
        with self.assertRaises(ValueError): self.gate([dict(risk,expires='2020-02-01')])
        self.report['Results'][0]['Secrets']=[{'RuleID':'key','Severity':'LOW'}]
        self.assertEqual(self.gate([risk]),2)
    def test_missing_scanner_and_invalid_evidence(self):
        self.manifest['scanners']=['vuln']
        with self.assertRaises(ValueError): self.gate()
        self.manifest['scanners']=['vuln','secret']; self.report['ArtifactID']='wrong'
        with self.assertRaises(ValueError): self.gate()
        self.report['ArtifactID']='sha256:abc'; self.report['Results'][0]['Secrets']=[{}]
        with self.assertRaises(ValueError): self.gate()
    def test_empty_report_is_failure_not_zero_findings(self):
        self.gate(); (self.root/'report.json').write_text('')
        with self.assertRaises(ValueError): scan.gate(self.root/'trivy-manifest.json')

class Upgrade(unittest.TestCase):
    def test_old_new_and_mixed_images(self):
        changes=json.loads((SKILLS/'upgrade-docs/changes.json').read_text())
        row=next(c for c in changes if c['id']=='platform-image-runtime')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'api').mkdir(); (root/'web').mkdir()
            old='FROM node:fixed\nUSER 1000\n'
            new=old+'ENV APP_VERSION=$APP_VERSION CI_COMMIT_SHORT_SHA=$CI_COMMIT_SHORT_SHA\n'
            (root/'api/Dockerfile').write_text(old); (root/'web/Dockerfile').write_text(old)
            self.assertTrue(upgrade.holds(root,row['applies'])); self.assertTrue(upgrade.holds(root,row['behind']))
            (root/'image-preflight.json').write_text('{}')
            (root/'api/Dockerfile').write_text(new)
            self.assertTrue(upgrade.holds(root,row['behind'])) # one new image cannot mask another old image
            (root/'web/Dockerfile').write_text(new)
            self.assertFalse(upgrade.holds(root,row['behind']))
    def test_old_new_nginx_and_deploy_document(self):
        changes=json.loads((SKILLS/'upgrade-docs/changes.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'nginx/templates').mkdir(parents=True)
            (root/'nginx/nginx.conf').write_text('events {}')
            (root/'nginx/templates/upstream.conf.template').write_text('upstream backend { }')
            row=next(c for c in changes if c['id']=='platform-nginx-runtime')
            self.assertTrue(upgrade.holds(root,row['behind']))
            (root/'nginx/nginx.conf').write_text('worker_shutdown_timeout 25s; # trusted_forwarder')
            (root/'nginx/templates/upstream.conf.template').write_text('resolver 127.0.0.11;')
            (root/'image-preflight.json').write_text('{}')
            self.assertFalse(upgrade.holds(root,row['behind']))
            path=root/'documentation/deploy/deploy.md';path.parent.mkdir(parents=True);path.write_text('# old')
            row=next(c for c in changes if c['id']=='platform-deploy-evidence')
            self.assertTrue(upgrade.holds(root,row['behind']))
            path.write_text('## Масштабирование\n## Сборка образа\nMAX_BODY_SIZE CLIENT_TIMEOUT BACKEND_TIMEOUT APP_VERSION CI_COMMIT_SHORT_SHA')
            self.assertFalse(upgrade.holds(root,row['behind']))

class EnvironmentFiles(unittest.TestCase):
    def test_regenerate_preserves_secret_and_check_rejects_manual_nonsecret_edit(self):
        import subprocess
        script=SKILLS/'deploy-topology/scripts/env_files.py'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'docker-compose.test.yml').write_text('services: {}')
            (root/'.env.example').write_text('# Template\n\n# [required] port\nPORT=8000\n# [secret] token\nTOKEN=\n')
            def call(mode): return subprocess.run([sys.executable,str(script),str(root),mode],capture_output=True,text=True)
            self.assertEqual(call('build').returncode,0)
            output=root/'.env.test.local';output.write_text(output.read_text().replace('TOKEN=','TOKEN=private-fixture'))
            self.assertEqual(call('check').returncode,0)
            output.write_text(output.read_text().replace('PORT=8000','PORT=9999'))
            self.assertEqual(call('check').returncode,1)
            self.assertEqual(call('build').returncode,0)
            self.assertIn('TOKEN=private-fixture',output.read_text())
            self.assertIn('PORT=8000',output.read_text())
            self.assertEqual(call('check').returncode,0)

if __name__=='__main__': unittest.main()
