#!/usr/bin/env python3
"""Check built images and an isolated DevOps acceptance stand (standard library only).

contents IMAGE... [--platform linux/amd64] [--app-root /srv/app]
stand PROJECT --config image-preflight.json

The stand descriptor is documented in references/image-preflight.md. Never reuse a
running project: resolved Compose gets a random project name, new volumes and local
random ports. No build, host writes, external volumes or fixed container names.
Exit 0: passed; 1: failed/unavailable; 2: invalid CLI syntax.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import uuid

FORBIDDEN = re.compile(
    r'(^|/)(?:\.env[^/]*|docker-compose[^/]*\.ya?ml|compose\.ya?ml|Dockerfile[^/]*|\.dockerignore|'
    r'\.git|tests?|__tests__)(/|$)|\.(?:test|spec)\.[cm]?[jt]sx?$|(^|/)test_[^/]*\.py$|'
    r'\.(?:key|pem|crt|p12|pfx|tsx|jsx|md|map)$|(^|/)config\.(?:ya?ml|json|toml)$', re.I)
CDN = re.compile(r'(?:https?:)?//(?:fonts\.(?:googleapis|gstatic)\.com|cdnjs\.cloudflare\.com|'
                 r'cdn\.jsdelivr\.net|unpkg\.com|ajax\.googleapis\.com|code\.jquery\.com|'
                 r'cdn\.tailwindcss\.com)(?:[/\s"\x27:]|$)', re.I)
PROBE = re.compile(r'/health(?:/live|/ready)?|/_healthz|/metrics')
SAMPLE = re.compile(r'^[a-zA-Z_:][a-zA-Z0-9_:]*(?:\{[^\n]*\})?\s+(?:[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|[+-]?Inf|NaN)(?:\s+\d+)?$')


def run(*args: str, timeout: int = 120) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        # Commands/config may contain secrets: do not echo argv, stderr or rendered Compose.
        raise ValueError(f'{args[0]} {args[1] if len(args)>1 else ""}: exit {result.returncode}')
    return result.stdout


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def prometheus(body: str) -> bool:
    samples = [line for line in body.splitlines() if line.strip() and not line.startswith('#')]
    return bool(samples) and all(SAMPLE.fullmatch(line) for line in samples)


def inspect_tar(archive: tarfile.TarFile, roots: list[str]) -> list[str]:
    problems = []
    for member in archive:
        name = member.name.removeprefix('./').lstrip('/')
        path = PurePosixPath(name)
        require('..' not in path.parts, 'unsafe archive path')
        own = any(name == root.strip('/') or name.startswith(root.strip('/') + '/') for root in roots)
        # Inspect nginx configs as well, but do not mistake the base CA store for project secrets.
        if member.isfile() and name.startswith('etc/nginx/') and name.endswith(('.conf', '.template')):
            content = archive.extractfile(member).read().decode('utf-8', 'replace')
            if re.search(r'^\s*upstream\s+\S+\s*\{', content, re.M):
                problems.append(f'/{name}: static upstream block')
        if not own or not (member.isfile() or member.issym() or member.islnk()):
            continue
        # Runtime dependencies may carry licences/tests; application files may not.
        if any(part in {'node_modules', '.venv', 'site-packages'} for part in path.parts):
            continue
        if FORBIDDEN.search(name) or ('documentation' in path.parts and 'migrations' not in path.parts):
            problems.append(f'/{name}: non-runtime file')
        if member.issym() or member.islnk():
            target = PurePosixPath(member.linkname)
            if target.is_absolute() or '..' in target.parts:
                problems.append(f'/{name}: app symlink needs an explicit contents review')
        if member.isfile() and name.endswith(('.html', '.js', '.mjs', '.css')):
            # Chunked read with overlap: large bundles need not fit in memory.
            handle, tail = archive.extractfile(member), ''
            while data := handle.read(65536):
                chunk = tail + data.decode('utf-8', 'replace')
                if CDN.search(chunk):
                    problems.append(f'/{name}: public CDN reference')
                    break
                tail = chunk[-256:]
    return problems


def contents(images: list[str], platform: str, app_roots: list[str]) -> None:
    problems = []
    for image in images:
        info = json.loads(run('docker', 'image', 'inspect', image))[0]
        cfg = info['Config']
        require(info['Os'] + '/' + info['Architecture'] == platform, f'{image}: expected {platform}')
        user = (cfg.get('User') or '').split(':')[0]
        require(user.isdigit() and int(user) > 0, f'{image}: numeric non-root USER required')
        env = dict(item.split('=', 1) for item in cfg.get('Env') or [] if '=' in item)
        require(all(env.get(k) and env[k] not in {'dev', 'unknown'} for k in ('APP_VERSION', 'CI_COMMIT_SHORT_SHA')),
                f'{image}: missing release version/commit')
        roots = list(dict.fromkeys(['/app', '/usr/share/nginx/html', *app_roots, cfg.get('WorkingDir') if cfg.get('WorkingDir') not in (None, '', '/') else '/app']))
        require('/' not in roots, 'specify application roots, not the entire base filesystem')
        cid = run('docker', 'create', image).strip()
        try:
            with tempfile.TemporaryFile() as file:
                subprocess.run(['docker', 'export', cid], stdout=file, check=True, timeout=180)
                file.seek(0)
                with tarfile.open(fileobj=file) as archive:
                    problems.extend(f'{image}: {problem}' for problem in inspect_tar(archive, roots))
        finally:
            run('docker', 'rm', '-f', cid)
    require(not problems, '\n'.join(problems))


def get(url: str) -> tuple[int, str]:
    # A redirect is not a working probe or protected management endpoint.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None
    try:
        with urllib.request.build_opener(NoRedirect).open(url, timeout=4) as response:
            return response.status, response.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode('utf-8', 'replace')
    except OSError:
        return 0, ''


def wait(url: str, status: int, seconds: int = 40) -> str:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        code, body = get(url)
        if code == status:
            return body
        time.sleep(.5)
    raise ValueError(f'{url}: did not reach HTTP {status}')


def quiet_logs(text: str) -> bool:
    for line in text.splitlines():
        if not PROBE.search(line):
            continue
        try:
            data = json.loads(line)
        except ValueError:
            return False
        # OBS-6: failures remain logged; only successful probes must be quiet.
        status = data.get('status', data.get('status_code', (data.get('res') or {}).get('statusCode', 0)))
        if isinstance(status, (int, str)) and str(status).startswith('5'):
            continue
        if str(data.get('level')).lower() not in {'debug', 'trace', '10', '20'}:
            return False
    return True


def isolate(config: dict, apps: list[str], ports: dict[str, list[int]]) -> dict:
    require(apps and len(apps) == len(set(apps)), 'nonempty unique apps required')
    config.pop('name', None)
    for group in ('volumes', 'networks'):
        for resource in config.get(group, {}).values():
            require(not resource.get('external'), 'external resources forbidden in preflight')
            resource.pop('name', None)  # Compose normally fills names from the original project.
    for name, service in config['services'].items():
        require(not service.get('container_name') and not service.get('privileged'), 'fixed container name/privileged forbidden')
        require(not service.get('network_mode') and not service.get('pid'), 'host/shared namespaces forbidden')
        for volume in service.get('volumes', []):
            require(volume.get('type') == 'volume' or
                    (volume.get('type') == 'bind' and volume.get('read_only')), 'writable host bind forbidden')
        service['ports'] = [{'target': port, 'published': '0', 'host_ip': '127.0.0.1', 'protocol': 'tcp'}
                            for port in ports.get(name, [])]
        service.pop('restart', None)
        service.pop('deploy', None)
        require(service.get('image'), f'{name}: build and tag images before preflight')
        service.pop('build', None)
        if name in apps:
            require(service.get('read_only') is True, f'{name}: read_only required')
            require(any(str(value).split(':')[0] == '/tmp' for value in service.get('tmpfs', [])), f'{name}: /tmp tmpfs required')
            require('ALL' in service.get('cap_drop', []), f'{name}: drop ALL required')
            require(any('no-new-privileges' in v for v in service.get('security_opt', [])), f'{name}: no-new-privileges required')
            require(not service.get('cap_add'), f'{name}: capabilities must not be added')
            service['user'] = '5000:5000'
    require(set(apps) <= config['services'].keys(), 'unknown application service')
    return config


def stand(root: Path, descriptor: Path) -> None:
    spec = json.loads(descriptor.read_text())
    apps, backend = spec['apps'], spec['backend']
    front = spec.get('frontend')
    public = spec.get('public_entry')
    require(front or public, 'API-only stand requires public_entry service/port to prove management protection')
    require(spec.get('secret_env') and spec.get('secret_error'), 'secret_env and specific secret_error regex required')
    re.compile(spec['secret_error'])
    deps = spec.get('dependencies', [])
    require(deps or spec.get('no_dependencies_reason'), 'dependencies or explicit no_dependencies_reason required')
    require(front or spec.get('no_frontend_reason'), 'frontend or explicit no_frontend_reason required')
    source = ['docker', 'compose', '--project-directory', str(root), '-f', str(root / spec.get('compose', 'docker-compose.test.yml'))]
    if spec.get('env_file'):
        source += ['--env-file', str(root / spec['env_file'])]
    config = json.loads(run(*source, 'config', '--format', 'json'))
    ports = {backend['service']: [int(backend['port'])]}
    if front:
        ports[front['service']] = [int(front['port']), int(front.get('health_port', 8081))]
    if public: ports.setdefault(public['service'], []).append(int(public['port']))
    config = isolate(config, apps, ports)
    if not deps: print('NOT_APPLICABLE dependency outage: ' + spec['no_dependencies_reason'])
    if not front: print('NOT_APPLICABLE frontend recovery: ' + spec['no_frontend_reason'])
    require(set(deps) <= config['services'].keys() and not set(deps) & set(apps), 'invalid dependencies')
    project = 'dp-preflight-' + uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix=project) as tmp:
        file = Path(tmp) / 'compose.json'
        file.write_text(json.dumps(config)); file.chmod(0o600)
        cmd = ['docker', 'compose', '-p', project, '-f', str(file)]
        def compose(*args: str, timeout: int = 180) -> str:
            return run(*cmd, *args, timeout=timeout)
        def cid(name: str) -> str:
            value = compose('ps', '-aq', name).strip()
            require(bool(value) and '\n' not in value, f'{name}: expected one container')
            return value
        def state(name: str) -> dict:
            return json.loads(run('docker', 'inspect', cid(name)))[0]['State']
        def url(name: str, port: int) -> str:
            bound = compose('port', name, str(port)).strip()
            return 'http://127.0.0.1:' + bound.rsplit(':', 1)[1]
        try:
            compose('up', '-d', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', '90', timeout=150)
            base = url(backend['service'], backend['port'])
            wait(base + '/health/ready', 200)
            status, body = get(base + '/metrics')
            require(status == 200 and prometheus(body) and 'app_build_info' in body, 'invalid Prometheus/build metrics')
            since = str(int(time.time()) + 1); time.sleep(1.1)
            for path in ('/health/live', '/health/ready', '/metrics'):
                for _ in range(3):
                    require(get(base + path)[0] == 200, 'probe failed during quiet-log check')
            time.sleep(.2)
            require(quiet_logs(compose('logs', '--no-log-prefix', '--since', since, backend['service'])), 'successful probes in logs')
            if public:
                public_url = url(public['service'], public['port'])
                for path in ('/metrics', '/health', '/health/live', '/health/ready', '/actuator/prometheus'):
                    code, body = get(public_url + path)
                    require(code in (401, 403, 404) and not prometheus(body), f'public service endpoint: {path}')
            if front:
                entry = url(front['service'], front['port'])
                require(spec.get('api_path') and spec.get('api_body'), 'api_path and api_body expected text required')
                def api_ok():
                    require(spec['api_body'] in wait(entry + spec['api_path'], 200), 'frontend did not reach expected backend')
                api_ok()
                # Check leakage with a healthy backend, not while it is stopped.
                for path in ('/metrics', '/health/live', '/health/ready', '/actuator/prometheus'):
                    code, body = get(entry + path)
                    require(code in (401, 403, 404) and not prometheus(body), f'public service endpoint: {path}')
                compose('stop', backend['service'])
                compose('rm', '-f', backend['service'])  # remove DNS record, not just stop process
                compose('restart', front['service'])
                entry = url(front['service'], front['port'])
                wait(url(front['service'], front.get('health_port', 8081)) + '/_healthz', 200)
                wait(entry + '/', 200)
                compose('up', '-d', '--no-deps', '--no-build', '--pull', 'never', backend['service'])
                base = url(backend['service'], backend['port']); wait(base + '/health/ready', 200); api_ok()
                compose('up', '-d', '--no-deps', '--no-build', '--pull', 'never', '--force-recreate', backend['service'])
                base = url(backend['service'], backend['port']); wait(base + '/health/ready', 200); api_ok()
            if deps:
                compose('stop', *deps)
                wait(base + '/health/ready', 503)
                require(get(base + '/health/live')[0] == 200, 'liveness depends on store')
                compose('restart', backend['service'])
                base = url(backend['service'], backend['port'])
                wait(base + '/health/live', 200); wait(base + '/health/ready', 503)
                require(state(backend['service'])['Running'], 'backend exited without dependencies')
                compose('start', *deps); wait(base + '/health/ready', 200)
            # Same known-good image/config; remove only secrets. An unrelated crash cannot pass.
            for secret in spec['secret_env']:
                for value in ('', 'short', 'change-me'):
                    name = project + '-secret'
                    try:
                        result = subprocess.run(cmd + ['run', '-d', '--no-deps', '--name', name, '-e', secret+'='+value,
                                                       backend['service']], capture_output=True, text=True, timeout=30)
                        require(result.returncode == 0, 'secret test could not start')
                        deadline = time.monotonic() + 15
                        while time.monotonic() < deadline:
                            st = json.loads(run('docker', 'inspect', name))[0]['State']
                            if not st['Running']: break
                            time.sleep(.2)
                        logs = subprocess.run(['docker', 'logs', name], capture_output=True, text=True, timeout=10)
                        require(not st['Running'] and st['ExitCode'] != 0 and not st.get('OOMKilled') and
                                bool(re.search(spec['secret_error'], logs.stdout + logs.stderr)), 'secret validation not proved')
                    finally:
                        run('docker', 'rm', '-f', name)
            for name in apps:
                started = time.monotonic()
                compose('stop', '-t', '30', name, timeout=40)
                require(state(name)['ExitCode'] == 0 and time.monotonic()-started < 31, f'{name}: shutdown failed')
        finally:
            compose('down', '-v', '--remove-orphans', timeout=120)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    image = modes.add_parser('contents'); image.add_argument('images', nargs='+')
    image.add_argument('--platform', default='linux/amd64'); image.add_argument('--app-root', action='append', default=[])
    live = modes.add_parser('stand'); live.add_argument('project', type=Path)
    live.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    try:
        run('docker', 'version')
        if args.mode == 'contents': contents(args.images, args.platform, args.app_root)
        else: stand(args.project.resolve(), args.config.resolve())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'FAIL: {error}'); return 1
    print('PASS: all requested checks completed'); return 0


if __name__ == '__main__':
    sys.exit(main())
