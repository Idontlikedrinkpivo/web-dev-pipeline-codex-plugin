# Built-image acceptance

Run after building the exact release images. These checks need Docker on the host, but no shell in the image.
Never run them in the operators' cluster or against their data. Ordinary service_check.py remains necessary for
JSON log schema/request ids and detailed service behavior; this preflight adds container acceptance scenarios.

```bash
python3 <deploy-topology>/scripts/image_preflight.py contents IMAGE_API IMAGE_FRONT --platform linux/amd64
python3 <deploy-topology>/scripts/image_preflight.py stand . --config image-preflight.json
python3 <deploy-topology>/scripts/trivy_images.py --out release/VERSION/scan IMAGE_API IMAGE_FRONT
```

Use --app-root for application paths outside /app or the image WORKDIR (repeatable). The exported filesystem is
streamed without extraction. Base dependencies/CA roots are not project files. A scan of the final filesystem
cannot detect secrets in deleted layers: Trivy is mandatory as well. Public CDN references in built HTML/CSS/JS,
working config, tests, keys, Compose files and static nginx upstream blocks fail acceptance.

The project commits a secret-free `image-preflight.json` descriptor, adapted to its actual component names:

```json
{
  "compose": "docker-compose.test.yml",
  "env_file": ".env.test.local",
  "apps": ["backend", "frontend"],
  "backend": {"service": "backend", "port": 8000},
  "frontend": {"service": "frontend", "port": 8080, "health_port": 8081},
  "dependencies": ["db"],
  "api_path": "/api/acceptance-smoke",
  "api_body": "expected response from this backend",
  "secret_env": ["SIGNING_KEY"],
  "secret_error": "configuration: SIGNING_KEY"
}
```

The API smoke route is an **existing safe read** with a deterministic response; do not add a public production
route just for the script. Include synthetic test authentication in a project-specific driver if needed; never
accept a generic SPA 200 as proof of backend recovery. `secret_env` lists the keys with the 32-character rule;
`secret_error` must match the application's specific configuration error, not arbitrary stderr.
A backend without stores sets dependencies=[] and no_dependencies_reason. An API without a frontend sets
no_frontend_reason and public_entry={"service":"gateway","port":8080}: test its actual ingress/auth
protection with a healthy backend; no public management path is permitted. These explicit omissions are reported, never evidence of checks being run.

The stand uses a random Compose project, fresh named volumes and random loopback ports. Only already-built,
locally tagged images run (--no-build, --pull never). Application services must already be read_only, drop ALL,
no-new-privileges, with /tmp tmpfs; their UID is overridden to 5000. No fixed container_name, privileged/host
namespaces, external resources or writable host binds. Configuration bind mounts must be read-only. Temporary
resolved Compose may contain test secrets: mode 0600, removed at the end; it is never printed.

The checks assert readiness 200 initially, Prometheus syntax/build metric, quiet successful probes, protected
management URLs while backend is healthy, frontend health without backend DNS, backend appearance/recreation,
DB-down live=200/ready=503 including backend restart, recovery, missing/short/placeholder secret refusal with
the specific configuration error, exit 0 within 30 seconds. Cleanup removes only the random project's resources.
Use ephemeral **test** credentials; never production credentials.

Also run project-specific checks: clean DB and concurrent migrations, long in-flight request at shutdown,
CLIENT_TIMEOUT slow upload/header, upload limit 413 and runtime override, BACKEND_TIMEOUT 504, HTTPS trusted and
untrusted CA, changed backend IP (not merely a restart reusing the same IP), worker heartbeat/queue recovery,
resource measurements. A test must not report these as passed just because the generic script passed.

Acceptance fixtures must include bad image files, static upstream and noisy successful probes; also test a
public metrics route with a healthy backend, invalid Prometheus body, missing descriptor, unrelated startup
crash, stale scan report and scanner failure. Never classify a skipped or malformed check as clean.

Scanner output belongs to release/VERSION/scan. An empty directory is required to avoid stale evidence.
The runner selects vuln+secret and all severities (including image-config secrets), removes secret excerpts
from the released report, records scanner version/command/status/image ID and invokes the strict validator.
Use --trivy-image with a registry-checked supported version/digest. The default is a tested version, not proof
that it remains current; recheck it each release. Report unavailable network/DB as a failed scan.

A risk file passed by --risks is an array of approved CRITICAL exceptions with digest, id (CVE), package, target,
approved_by, reason, accepted_on and expires (YYYY-MM-DD). Approval is obtained from the owner, never fabricated
by a script. Expired/malformed risk records fail. Secrets are never waived. Keep the file and approval evidence
with the release, then rerun --check scan/trivy-manifest.json --risks scan/accepted-risks.json.
