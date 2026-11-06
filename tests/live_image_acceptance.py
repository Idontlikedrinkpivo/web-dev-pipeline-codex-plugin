"""Opt-in live Docker acceptance for the plugin's nginx and preflight.

Usage: python3.12 tests/live_image_acceptance.py --go /tmp/sdk/go/bin/go
Uses cached nginx/python/postgres bases, builds only uniquely tagged disposable fixtures.
Requires Docker daemon access. Does not touch existing projects, networks or volumes.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'dev-pipeline/skills/deploy-topology'
spec = importlib.util.spec_from_file_location('preflight_live', SKILL/'scripts/image_preflight.py')
pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf)
NGINX='nginxinc/nginx-unprivileged@sha256:59678856b05324b7f6371f26eb1520be7fcd8bdc8ab380fc4913db8503e5a842'

def run(*args, **kwargs):
    result=subprocess.run(args, capture_output=True, text=True, **kwargs)
    if result.returncode: raise RuntimeError(f'{args[0]} failed: {result.stderr[-1500:]}')
    return result.stdout.strip()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--go', required=True);args=ap.parse_args()
    ident='dp-live-'+uuid.uuid4().hex[:10]
    tags=[ident+':web',ident+':api',ident+':files',ident+':upstream']
    with tempfile.TemporaryDirectory(prefix=ident) as tmp:
        root=Path(tmp); shutil.copytree(SKILL/'assets/nginx', root/'nginx')
        for path in (root/'nginx').rglob('*'):
            if path.is_file() and path.suffix != '.go':
                path.write_text(path.read_text().replace('<<CONF_DIR>>','/tmp').replace('<<SERVICE>>','fixture-web'))
        arch=json.loads(run('docker','image','inspect',NGINX))[0]['Architecture']
        env=dict(os.environ,CGO_ENABLED='0',GOOS='linux',GOARCH=arch,GOCACHE=str(root/'go-cache'))
        run(args.go,'build','-trimpath','-ldflags=-s -w','-o',str(root/'nginx-runtime'),str(root/'nginx/runtime.go'),env=env,timeout=180)
        (root/'index.html').write_text('<html>fixture frontend</html>')
        (root/'Dockerfile.web').write_text(f'''FROM {NGINX}
COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/templates /etc/nginx/templates
COPY nginx-runtime /usr/local/bin/nginx-runtime
COPY index.html /usr/share/nginx/html/index.html
ENV NGINX_ENVSUBST_OUTPUT_DIR=/tmp NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1 NGINX_ENTRYPOINT_QUIET_LOGS=1 LOG_LEVEL=notice TRUSTED_PROXY_CIDR=127.0.0.1/32 MAX_BODY_SIZE=1k CLIENT_TIMEOUT=2s BACKEND_TIMEOUT=1s APP_VERSION=1.3.2 CI_COMMIT_SHORT_SHA=fixture
USER 101
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/local/bin/nginx-runtime", "/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
''')
        fixture=ROOT/'tests/fixtures/image-preflight'
        shutil.copy(fixture/'server.py',root/'server.py');shutil.copy(fixture/'Dockerfile.backend',root/'Dockerfile.api')
        (root/'extra.md').write_text('must not ship')
        (root/'Dockerfile.files').write_text(f'FROM {tags[1]}\nCOPY extra.md /app/extra.md\n')
        (root/'upstream.template').write_text((root/'nginx/templates/upstream.conf.template').read_text()+'\nupstream broken { server backend:8000; }\n')
        (root/'Dockerfile.upstream').write_text(f'FROM {tags[0]}\nCOPY upstream.template /etc/nginx/templates/upstream.conf.template\n')
        # Keep compiler cache out of Docker contexts.
        (root/'.dockerignore').write_text('go-cache\n')
        project=ident
        cmd=['docker','compose','-p',project,'-f',str(root/'compose.json')]
        def compose(*values): return run(*cmd,*values,timeout=120)
        try:
            for suffix,tag in zip(('web','api','files','upstream'),tags):
                run('docker','build','--pull=false','-t',tag,'-f',str(root/f'Dockerfile.{suffix}'),str(root),timeout=180)
            pf.contents(tags[:2],'linux/'+arch,[]); print('PASS contents good images',flush=True)
            for tag in tags[2:]:
                try:pf.contents([tag],'linux/'+arch,[])
                except ValueError:print('PASS rejected '+tag.rsplit(':',1)[1],flush=True)
                else:raise AssertionError('bad image accepted')
            hard={'read_only':True,'tmpfs':['/tmp'],'cap_drop':['ALL'],'security_opt':['no-new-privileges:true']}
            config={'services':{'backend':dict(hard,image=tags[1],environment={'SIGNING_KEY':'x'*40},ports=[{'target':8000,'published':'0','host_ip':'127.0.0.1'}]),
                                'frontend':dict(hard,image=tags[0],environment={'BACKEND_SERVICE':'backend:8000','BACKEND_PROTOCOL':'http','SECURE_MODE':'plain'},
                                                ports=[{'target':8080,'published':'0','host_ip':'127.0.0.1'},{'target':8081,'published':'0','host_ip':'127.0.0.1'}]),
                                'db':{'image':'postgres:16-alpine','environment':{'POSTGRES_PASSWORD':'fixture-only'},'tmpfs':['/var/lib/postgresql/data']}}}
            file=root/'compose.json';file.write_text(json.dumps(config))
            descriptor={'compose':'compose.json','apps':['backend','frontend'],'backend':{'service':'backend','port':8000},
                        'frontend':{'service':'frontend','port':8080,'health_port':8081},'dependencies':['db'],
                        'api_path':'/api/ping','api_body':'preflight-backend','secret_env':['SIGNING_KEY'],
                        'secret_error':'configuration: SIGNING_KEY'}
            desc=root/'image-preflight.json';desc.write_text(json.dumps(descriptor))
            pf.stand(root,desc);print('PASS preflight good stand',flush=True)
            config['services']['backend']['environment']['NOISY']='1';file.write_text(json.dumps(config))
            try: pf.stand(root,desc)
            except ValueError as error:
                assert 'successful probes in logs' in str(error),error
                print('PASS preflight rejected noisy backend',flush=True)
            else:raise AssertionError('noisy stand accepted')
            config['services']['backend']['environment'].pop('NOISY')
            config['services']['frontend']['image']=tags[3];file.write_text(json.dumps(config))
            try:pf.stand(root,desc)
            except ValueError:print('PASS preflight rejected static upstream',flush=True)
            else:raise AssertionError('static upstream accepted')
            config['services']['frontend']['image']=tags[0]
            # Live nginx runtime env and shutdown; isolated project, foreign UID.
            for svc in ('backend','frontend'):config['services'][svc]['user']='5000:5000'
            file.write_text(json.dumps(config));compose('up','-d','--no-build','--pull','never')
            def entry():return 'http://127.0.0.1:'+compose('port','frontend','8080').rsplit(':',1)[1]
            pf.wait(entry()+'/api/ping',200)
            # Occupy the removed backend's address so recreation really changes DNS/IP.
            old_cid=compose('ps','-q','backend')
            info=json.loads(run('docker','inspect',old_cid))[0]
            network=next(iter(info['NetworkSettings']['Networks']))
            old_ip=info['NetworkSettings']['Networks'][network]['IPAddress']
            compose('stop','backend');compose('rm','-f','backend')
            blocker=ident+'-ip-holder'
            try:
                run('docker','run','-d','--name',blocker,'--network',network,'--ip',old_ip,'alpine:3.22','sleep','120')
                compose('up','-d','--no-deps','--no-build','--pull','never','backend')
                new_info=json.loads(run('docker','inspect',compose('ps','-q','backend')))[0]
                assert new_info['NetworkSettings']['Networks'][network]['IPAddress']!=old_ip
                pf.wait(entry()+'/api/ping',200)
                print('PASS recreated backend at different IP is found without frontend restart',flush=True)
            finally:subprocess.run(['docker','rm','-f',blocker],capture_output=True,timeout=20)
            import urllib.request,urllib.error
            def post():
                try:
                    with urllib.request.urlopen(urllib.request.Request(entry()+'/api/upload',data=b'x'*2048),timeout=10) as r:return r.status
                except urllib.error.HTTPError as error:return error.code
            assert post()==413;print('PASS MAX_BODY_SIZE=1k -> 413',flush=True)
            start=time.monotonic();assert pf.get(entry()+'/api/slow?token=never-log-this')[0]==504
            assert .7<time.monotonic()-start<2.5;print('PASS BACKEND_TIMEOUT=1s -> 504',flush=True)
            # Slow request headers exercise CLIENT_TIMEOUT, not application timeout.
            port=int(entry().rsplit(':',1)[1])
            with socket.create_connection(('127.0.0.1',port),timeout=6) as client:
                client.sendall(b'GET / HTTP/1.1\r\nHost: localhost\r\nX-Slow: ')
                start=time.monotonic();reply=client.recv(8192)
                assert b'408' in reply or reply==b'';assert time.monotonic()-start<5
            print('PASS CLIENT_TIMEOUT slow headers',flush=True)
            config['services']['frontend']['environment'].update(MAX_BODY_SIZE='4k',BACKEND_TIMEOUT='10s')
            file.write_text(json.dumps(config));compose('up','-d','--no-deps','--force-recreate','frontend')
            pf.wait(entry()+'/api/ping',200);assert post()==200;print('PASS env override same image -> upload 200',flush=True)
            # Spoofed scheme must not be trusted from the host's non-allowlisted peer; tested separately by contract.
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(pf.get,entry()+'/api/slow');time.sleep(.5)
                cid=compose('ps','-q','frontend');run('docker','stop','-t','30',cid,timeout=35)
                assert future.result()[0]==200
                state=json.loads(run('docker','inspect',cid))[0]['State'];assert state['ExitCode']==0
            print('PASS SIGTERM drains in-flight request, exit 0',flush=True)
            logs=compose('logs','--no-log-prefix','frontend')
            assert 'never-log-this' not in logs
            for line in logs.splitlines():
                record=json.loads(line);assert all(k in record for k in ('time','level','logger','msg'))
            print('PASS nginx all output JSON',flush=True)
        finally:
            subprocess.run(cmd+['down','-v','--remove-orphans'],capture_output=True,timeout=120)
            subprocess.run(['docker','image','rm',*tags],capture_output=True,timeout=60)
    print('PASS live acceptance complete')

if __name__=='__main__':main()
