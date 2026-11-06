"""Opt-in: execute the actual FastAPI/Fastify reference snippets against disposable PostgreSQL.
Requires --python (venv with FastAPI deps), --node-dir (npm prefix with Fastify deps).
Does not build backend container images; records that distinction explicitly.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[1];SKILLS=ROOT/'dev-pipeline/skills'
spec=importlib.util.spec_from_file_location('pf',SKILLS/'deploy-topology/scripts/image_preflight.py')
pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf)

def freeport():
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]
def run(*cmd):return subprocess.run(cmd,check=True,capture_output=True,text=True,timeout=90).stdout.strip()
def blocks(stack):return re.findall(r'```(?:python|typescript)\n(.*?)\n```',(SKILLS/f'{stack}/references/service-endpoints.md').read_text(),re.S)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--python',required=True);parser.add_argument('--node-dir',type=Path,required=True);args=parser.parse_args()
    db='dp-service-'+uuid.uuid4().hex[:10];dbport=freeport()
    with tempfile.TemporaryDirectory(prefix=db) as tmp:
        root=Path(tmp); py=root/'py/bootstrap';py.mkdir(parents=True);(py/'__init__.py').touch()
        code=blocks('fastapi');(py/'observability.py').write_text(code[0])
        (py/'settings.py').write_text('''import os
class Settings:
    database_url=os.environ['DATABASE_URL']
    port=int(os.environ['PORT'])
    log_level=os.environ.get('LOG_LEVEL','info')
    shutdown_timeout_sec=25
    app_version='fixture'
    commit_sha='fixture'
    trusted_proxies=''
''')
        imports='''from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine
from .settings import Settings
from .observability import APP_BUILD, RequestContext, build_service_router
'''
        (py/'main.py').write_text(imports+code[1])
        (py/'serve.py').write_text(code[2].replace('<package>.',''))
        node=root/'node';node.mkdir();(node/'bootstrap').mkdir();(node/'node_modules').symlink_to(args.node_dir/'node_modules',target_is_directory=True)
        (node/'package.json').write_text('{"type":"module"}')
        code=blocks('typescript-fastify');(node/'bootstrap/service-routes.ts').write_text(code[1])
        server=code[0];i=server.index('const app ='); imports=server[:i]
        (node/'bootstrap/server.ts').write_text(imports+'import { registerServiceRoutes } from "./service-routes.js"\nexport function buildServer(deps: any) {\n'+server[i:]+'\nreturn app\n}\n')
        (node/'bootstrap/config.ts').write_text('''export function loadConfig(env: NodeJS.ProcessEnv) { return {
 databaseUrl: env.DATABASE_URL, port: Number(env.PORT), logLevel: env.LOG_LEVEL ?? "info",
 trustedProxies: [], appVersion: "fixture", commitSha: "fixture", shutdownTimeoutSec:25
} }
''')
        (node/'index.ts').write_text(code[2])
        try:
            run('docker','run','-d','--rm','--name',db,'-p',f'127.0.0.1:{dbport}:5432','--tmpfs','/var/lib/postgresql/data',
                '-e','POSTGRES_PASSWORD=fixture-only','-e','POSTGRES_USER=fixture','-e','POSTGRES_DB=fixture','postgres:16-alpine')
            for name,cwd,command,url in [
                ('FastAPI',py.parent,[args.python,'-m','bootstrap.serve'],f'postgresql+asyncpg://fixture:fixture-only@127.0.0.1:{dbport}/fixture'),
                ('Fastify',node,['node','--import','tsx','index.ts'],f'postgresql://fixture:fixture-only@127.0.0.1:{dbport}/fixture')]:
                port=freeport();env=dict(os.environ,PORT=str(port),DATABASE_URL=url,PYTHONDONTWRITEBYTECODE='1')
                check=subprocess.run([sys.executable,str(SKILLS/'repo-scaffold/scripts/service_check.py'),'--port',str(port),'--expect-ready','--',*command],
                                     cwd=cwd,env=env,capture_output=True,text=True,timeout=90)
                if check.returncode:raise AssertionError(name+' service_check: '+check.stdout+check.stderr)
                print('PASS '+name+' service_check: health, Prometheus, JSON, request id, SIGTERM',flush=True)
                with tempfile.TemporaryFile(mode='w+') as log:
                    proc=subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT)
                    base=f'http://127.0.0.1:{port}'
                    try:
                        pf.wait(base+'/health/ready',200)
                        status,metrics=pf.get(base+'/metrics');assert status==200 and 'app_build_info' in metrics and 'db_pool_connections' in metrics
                        assert pf.get(base+'/docs')[0]==404
                        pf.get(base+'/unknown?token=should-not-be-logged')
                        run('docker','stop',db)
                        pf.wait(base+'/health/ready',503);assert pf.get(base+'/health/live')[0]==200;assert proc.poll() is None
                        proc.terminate();assert proc.wait(timeout=30)==0
                        proc=subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT)
                        pf.wait(base+'/health/live',200);pf.wait(base+'/health/ready',503)
                        # --rm removed the old DB: recreate at the same fixed host port.
                        run('docker','run','-d','--rm','--name',db,'-p',f'127.0.0.1:{dbport}:5432','--tmpfs','/var/lib/postgresql/data',
                            '-e','POSTGRES_PASSWORD=fixture-only','-e','POSTGRES_USER=fixture','-e','POSTGRES_DB=fixture','postgres:16-alpine')
                        pf.wait(base+'/health/ready',200)
                        proc.send_signal(signal.SIGINT);assert proc.wait(timeout=30)==0
                        log.seek(0);assert 'should-not-be-logged' not in log.read()
                        print('PASS '+name+' build/pool metrics, docs off, safe query logs, DB outage/restart/recovery, SIGINT',flush=True)
                    finally:
                        if proc.poll() is None:proc.terminate();proc.wait(timeout=30)
        finally:subprocess.run(['docker','rm','-f',db],capture_output=True,timeout=30)
    print('PASS actual service snippets (host processes, not backend container images)')

if __name__=='__main__':main()
