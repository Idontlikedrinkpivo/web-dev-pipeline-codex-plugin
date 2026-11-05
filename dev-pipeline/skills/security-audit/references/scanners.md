# Scanners

Read in Step 1. Each scanner runs from the repository root through its
Docker image, so nothing is installed on the machine. Pull the image once
per audit, check its flags with `--help` before relying on the commands
below (tools rename subcommands between majors), and save the raw output in
one folder, created once before the first scanner:

```bash
OUT="$(git rev-parse --absolute-git-dir)/pipeline-work/security"
mkdir -p "$OUT"
```

Each container gets that folder mounted as `/out` and writes there — never a
path under `/repo/.git` or `/src/.git`: in a linked worktree `.git` is a file,
and the git folder lies outside the mounted tree. Never paste raw output into
the chat or a packet: the auditor reads the file.

## Network, proxy and caches

Every scanner downloads its rules or vulnerability database on first use,
and behind a corporate proxy that download is where a run stalls.

- **Proxy.** Pass the machine's proxy into each container, both spellings:
  `-e HTTPS_PROXY -e HTTP_PROXY -e NO_PROXY -e https_proxy -e http_proxy
  -e no_proxy`. A proxy on the machine's own `localhost` is
  `host.docker.internal` from inside a container (Docker Desktop); rewrite
  the address for the container, not on the machine.
- **Check before the run.** One quick request from a throwaway container
  through the same proxy to each source the scanners use — `mirror.gcr.io`
  and `ghcr.io` (trivy's database), `api.osv.dev` (osv-scanner),
  `semgrep.dev` (rule packs). A source that does not answer is known before
  a scanner hangs on it.
- **Cache between runs.** trivy's database lives in a named volume, so it
  is downloaded once and refreshed, not fetched whole every scan: `-v
  pipeline-trivy-cache:/root/.cache/trivy`. The volume is the audit's own
  and survives the stands' cleanup. osv-scanner and semgrep keep nothing
  to cache: they ask `api.osv.dev` and fetch the rule packs from
  `semgrep.dev` on every run, so for them the check before the run is what
  matters.
- **A download that stops moving.** Watch the download's size, not the
  clock: when it has not grown for a few checks in a row, switch to the
  fallback source — trivy `--db-repository ghcr.io/aquasecurity/trivy-db`
  (or `mirror.gcr.io/aquasec/trivy-db`, whichever was not tried); osv-scanner
  and semgrep have no mirror — and when the fallback stalls too, the row
  is `⏭ пропущено: не запускался — сеть (<источник>)` and the audit goes on with the
  rest. A scanner never holds the audit hostage.

## Dependencies — `osv-scanner`

Known vulnerabilities in the versions the lockfiles pin
(`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `uv.lock`,
`poetry.lock`, `requirements*.txt`).

```bash
docker run --rm -v "$PWD:/src" ghcr.io/google/osv-scanner:latest \
  scan source -r /src --format json > "$OUT/osv.json"
```

Without Docker: `npm audit --json` / `pip-audit -f json` (or `uvx
pip-audit`). Exit code 1 means "found something", not a failure.

Reading it: a vulnerability counts against the app only when the package
ships to production (not a dev dependency) **and** the vulnerable function
is reachable from this code — the auditor checks the second part. A fixed
version, when the advisory has one, is the fix in words.

## Secrets — `gitleaks`

Keys, tokens, passwords, private keys in the working tree **and in every
commit**: a secret deleted in a later commit is still in the history and
still has to be rotated.

```bash
docker run --rm -v "$PWD:/repo" -v "$OUT:/out" ghcr.io/gitleaks/gitleaks:latest \
  git /repo --report-format json --report-path /out/gitleaks.json --redact
```

`--redact` keeps the secret's value out of the report. Older majors spell
the subcommand `detect --source /repo`. The history scan needs the real git
folder inside the container: in a linked worktree run it from the main
working tree (`git worktree list`, first line), which holds the same history. Fixture values the test compose
file declares on purpose (`deploy-topology` → Step 6) are not findings;
anything else that looks live is P0 until the user says it is a dummy.

## Patterns — `semgrep`

Code patterns of the OWASP Top 10 and the stack's own pitfalls.

```bash
docker run --rm -v "$PWD:/src" -v "$OUT:/out" semgrep/semgrep:latest \
  semgrep scan --config p/owasp-top-ten --config p/<stack> \
  --json --output /out/semgrep.json /src
```

`<stack>`: `p/typescript` and `p/react` for a TypeScript project,
`p/python` for Python; one `--config` per pack. Exclude generated code,
`node_modules/`, test fixtures and `documentation/` with `--exclude`.

Reading it: semgrep matches shapes, not data flow. A raw SQL string built
from constants is not an injection; the auditor follows each hit to see
whether outside input reaches it.

## Docker images — `trivy` (in `deploy-topology`, not here)

The built images exist only in `deploy-topology` Step 8. Scan **each exact
release image separately**, from the locally built images before hand-over.
The multi-image release tar is transport, not a single-image scan target.
Never pass several positional image names to one Trivy invocation.

For each image, use a distinct report path in a fresh audit output directory:

```bash
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  -v pipeline-trivy-cache:/root/.cache/trivy aquasec/trivy:latest \
  image --image-src docker --severity HIGH,CRITICAL --format json "$IMAGE" > "$REPORT"
scan_status=$?
```

Capture `scan_status` immediately, including on failure (a shell with `set -e`
must explicitly handle the command). Record the exact command, status, image
ref and `docker image inspect` ID when available. Do not reuse old reports.
Trivy's default exit code leaves severity decisions to the existing policy;
if a configured severity exit is used, preserve it, never replace it with zero.
A nonzero scan status is not successful completeness evidence.

Write `trivy-manifest.json` with the full expected image list from the build
and one record per command. Paths are relative to this manifest:

```json
{
  "expected": ["project-api:1.4.0", "project-web:1.4.0"],
  "records": [
    {"image": "project-api:1.4.0", "report": "trivy-api.json", "exit_code": 0},
    {"image": "project-web:1.4.0", "report": "trivy-web.json", "exit_code": 0}
  ]
}
```

When an image ID is available, add `digest` to that record; it must match the
report's `ArtifactID` (use the same identity kind, not a registry digest in
place of a local image ID). The report must have `SchemaVersion: 2`,
`ArtifactType: "container_image"`, an exact matching `ArtifactName`, and an
array `Results`. Result entries require `Target`; any vulnerability entries
require `VulnerabilityID` and a Trivy severity. Additional Trivy fields are allowed.

Run `python3 "<security-audit skill folder>/scripts/trivy_reports.py" "$OUT/trivy-manifest.json"`.
Exit 0 confirms completeness only; apply the unchanged severity policy to the
findings. Exit 2 means incomplete/invalid evidence; a recorded scanner error
retains its nonzero exit. Missing, empty, corrupt, truncated, duplicate,
unexpected or wrong-image reports never mean zero findings. `Results: []`
is valid only with a successful scan and matching artifact identity for every
expected image. Keep the manifest, reports, command statuses and versions with
the release evidence. Fixture validation and a live two-image Docker/Trivy run
are separate checks; unavailable prerequisites mean `NOT_RUN`, not live success.

## When a scanner cannot run

No Docker and no local tool, no network for the rule packs, an image that
will not pull: write the row `⏭ пропущено: не запускался — <причина>` and name it in
the verdict line. The audit still runs its trace; the gap is the user's to
see, not the audit's to hide.
