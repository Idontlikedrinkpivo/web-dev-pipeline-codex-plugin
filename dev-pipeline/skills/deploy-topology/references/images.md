# Images: what each container's image holds and how they are handed over

Read this at Step 2 and Step 8. The images are an SPA frontend on unprivileged nginx and a backend in
its runtime, handed over as one tar. Match the shapes below; do not add labels or ports they do not have —
each extra one is a fact the operators must check and nobody asked for. What every image holds, and why:

- **An unprivileged process with a numeric `USER`** — a Kubernetes platform's preflight (`runAsNonRoot`)
  can verify only a number.
- **A root filesystem the process never writes** — the test and prod files run it `read_only`, as a
  restricted namespace does.
- **Pinned bases, checked against the registry** — a remembered or floating tag builds a different image
  tomorrow.
- **Healthchecks through the image's own runtime** — no `wget`/`curl` to install, and a shell-less image
  has none.
- **The SQL migrations at their repository path** — the backend image carries
  `documentation/db/migrations/`, the one place migrations live, not a copy in the code tree.
- **A tag with the app version and the build date**, nginx's upload size and timeouts from the SRS NFRs,
  and a variant without a shell when the project chose one.

Contents:

- Which images
- Shell or no shell — asked once per project
- Checking a tag
- A vulnerable base (Step 8, item 5)
- Backend image — with a shell (TypeScript)
- Backend image — with a shell (Python)
- Backend image — without a shell
- Healthchecks through the runtime
- Frontend image — the reference (SPA)
- Frontend image — without a shell
- Version, date, tag
- Architecture
- Hand-over: one tar and the release folder

## Which images

One image per container of the architecture (foundation §1 «Состав
системы», the containers view). The project's answer to the shell question
(below) picks the column; both run as a numeric non-root UID:

| Container | Image | With a shell | Without a shell | UID |
|---|---|---|---|---|
| Backend API (and its `migrate` one-shot — same image, other command), TypeScript | `<project>-backend` | `node:<pinned>-alpine` | `gcr.io/distroless/nodejs<major>-debian<N>:nonroot`, built on `node:<pinned>-<codename>-slim` of the same Debian branch | 1000 / 65532 |
| Backend API, Python | `<project>-backend` | `python:<pinned>-slim` | `gcr.io/distroless/cc-debian<N>:nonroot` with a uv-managed CPython from a build stage on the same branch | 10001 / 65532 |
| SPA client (React + Vite) | `<project>-frontend` | `nginxinc/nginx-unprivileged:<version>-alpine-slim` | an nginx image with no shell, by digest (e.g. `cgr.dev/chainguard/nginx`) | 101 / 65532 |
| SSR client (Next.js) | `<project>-frontend` | `node:<pinned>-alpine` with `output: "standalone"`, shaped like the backend; no nginx | the backend's distroless Node shape | 1000 / 65532 |

No client in the architecture → only the backend image. `<project>` is the
kebab-case project name. Base references are exact — a version tag, or a
digest where the vendor publishes only moving tags — never `latest` alone
or a bare major (Step 2).

The UID is a number in the Dockerfile's last `USER` line: Kubernetes'
`runAsNonRoot` can verify only a numeric user, so `USER node` or
`USER nonroot` fails the platform's check even though it is not root.

## Shell or no shell — asked once per project

An image without a shell holds the runtime and the app only: no `sh`, no
package manager, no `wget`/`curl`. Scanners find less in it, and some
platforms accept nothing else; the cost is that nobody can `docker exec …
sh` into it. The app behaves the same either way.

Before asking, look for the answer: the «Образ» row of «Карточка сервиса»
in `documentation/deploy/deploy.md`, else the base of existing Dockerfiles,
else the progress file's Step 2 row of an interrupted run. Found — reuse it
without asking. Not found — ask once, the first time this stage writes
Dockerfiles, per `pipeline` → `references/question-format.md`:

```text
**Вопрос 1. Образы с оболочкой или без**

В образе без оболочки нет `sh`, утилит и пакетного менеджера: зайти в
контейнер командой `docker exec … sh` нельзя, зато сканер находит в нём
меньше уязвимостей, а платформы с правилом «образ без оболочки» его
принимают. Приложение работает одинаково (`distroless` — образ только с
рантаймом: Node или Python, без утилит ОС).

  A. Без оболочки — distroless; проверки делает сам рантайм или кластер.
  B. С оболочкой — alpine / slim; тоже без root и с защитой контейнера.

Рекомендую B: оболочка помогает эксплуатации проверять и диагностировать контейнер.

Ответьте сообщением: буква или свой текст.
```

Recommend B by default, keeping A/B in this order. Recommend A only when explicitly required by the
user or the target platform; explain that requirement. Reuse an existing project choice. Record the selected
shape in the service card and Step 2 progress row.

## Checking a tag

Every base reference is checked against its registry before it goes into a
Dockerfile — never written from memory or from another project:

```bash
docker buildx imagetools inspect node:<version>-alpine
docker buildx imagetools inspect gcr.io/distroless/nodejs<major>-debian<N>:nonroot
```

- The tag exists, and its manifest list holds the card's architecture
  (`linux/amd64`, or `linux/arm64`).
- A moving tag — distroless publishes no patch tags; some vendors give only
  `latest` for free — is pinned by the `Digest:` line it prints:
  `FROM gcr.io/distroless/nodejs22-debian13:nonroot@sha256:<digest>`. A
  digest is immutable, so two builds of one commit still match.
- **Distroless: the newest Debian branch.** `debian<N>` is the highest `N`
  the registry has for this runtime and the card's architecture (2026-10:
  `debian13`). An older branch keeps fixes later or never: on 2026-10-23
  `nodejs22-debian12` carried a CRITICAL in `libssl3` that Debian had
  fixed, which stops every hand-over at Step 8, item 5, while `nodejs22-debian13`
  had no HIGH or CRITICAL. The build stage sits on the same branch
  (`node:<pinned>-trixie-slim` for `debian13`, `bookworm` for `debian12`)
  so native modules link against the glibc the runtime has.
- The Node major of a distroless runtime equals the build stage's: native
  modules are compiled for that ABI.
- After the first build: `docker image inspect --format '{{.Config.User}}
  {{json .Config.Entrypoint}} {{json .Config.Cmd}}' <image>:<tag>` — the
  user is the number the card names, and the entrypoint is what `CMD`, the
  healthcheck and the `migrate` command assume.

Repeat these registry checks before **every release**; update the same supported line to its current patched
base/digest, rebuild, and scan the exact result. Record resolved digests with the build. Never reuse a published
tag for different bytes: if a second build falls in the same tag minute, wait for the next minute.

No access to the registry here: say so and leave the placeholder for the
user rather than a remembered tag.

## A vulnerable base (Step 8, item 5)

Any CRITICAL blocks hand-over, whether in the base or application dependencies, fixed or unfixed.
A secret at **any severity** always blocks it: remove, rotate and rescan; a risk acceptance cannot waive a secret.
An empty/missing/malformed report or failed scanner is not a clean scan. The gate is
`scripts/trivy_images.py` (complete per-image evidence is still checked by `security-audit/scripts/trivy_reports.py`).
A CRITICAL can pass only with explicit approved risk: image digest, CVE, package, target, approver, reason,
acceptance date and expiry date, kept beside the reports. HIGH remains in the report for review.

For a CRITICAL in the base image, First try what changes nothing in the app: a fresh digest
of the same tag, then the newest Debian branch (distroless) or a newer
patch tag; rebuild and rescan. Still there — the hand-over stops with one
question per `pipeline` → `references/question-format.md`. Its text is the
same whether Step 8 runs in this stage or inside `upgrade-code`, which has
no audit question of its own to share:

```text
**Вопрос 1. Критическая уязвимость в базовом образе**

Сканер нашёл в образе `<project>-backend` критическую уязвимость
`<CVE>` в пакете `<пакет> <версия>`: <исправлена в версии … / исправления пока нет>. Платформа может не принять такой
образ на проверке перед установкой.

  A. Перейти на базу `<чистая база>` и пересобрать — сканер её проверил.
  B. Подождать исправленную базу — комплект не передаём, пока сканер не чист.
  C. Передать как есть — риск записывается в «Принятый риск» с датой.

Рекомендую A: <почему>.

Ответьте сообщением: буква или свой текст.
```

A appears only when the tries above found a clean base. C goes into
«Принятый риск» of `documentation/plans/<version>/security-audit.md`, or
into the closing report when there is no audit.

## Backend image — with a shell (TypeScript)

```dockerfile
FROM node:<pinned>-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build                                  # → /app/dist

FROM node:<pinned>-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev
COPY --from=build /app/dist ./dist
COPY documentation/db/migrations ./documentation/db/migrations   # same repo-relative path the runner reads
ARG APP_VERSION=dev CI_COMMIT_SHORT_SHA=unknown
ENV APP_VERSION=$APP_VERSION CI_COMMIT_SHORT_SHA=$CI_COMMIT_SHORT_SHA
USER 1000                                          # the image's `node` user, by number
EXPOSE 3000
CMD ["node", "dist/<entry>.js"]
```

- `dist/<entry>.js` is the build output of the one file that calls
  `listen` — `src/index.ts` → `dist/src/index.js` or `dist/index.js`,
  by the tsconfig's `rootDir`/`outDir`; the manifest's `start` script
  names it. The `migrate` command is the build output of the migrate
  script the same way. Read both from the project, never from this page.
- Two stages: the build stage has the TypeScript toolchain; the runtime
  stage installs production dependencies only (`npm ci --omit=dev`, the
  manifest copied before the code so the dependency layer is cached) and
  copies the compiled `dist`. A separate build tsconfig excludes tests, fixtures and source maps; the typecheck
  config still checks tests. Do not copy the entire repository to the final stage.
- Node: set `NODE_OPTIONS=--max-old-space-size=<MiB>` in each environment, calculated from the memory limit
  with headroom for native buffers, threads and the process (start at 75%, verify with measurements).
  Document the budget; do not bake a platform memory limit into the image.
- Files stay root-owned and the process runs as 1000: it can read its code
  and cannot change it. It writes nothing but `/tmp`, which compose and
  the cluster mount as a tmpfs / `emptyDir` over a read-only root.
- The SQL migrations travel inside the image: `documentation/db/migrations/`
  is copied to the same relative path under `WORKDIR`, because the
  project's migrate command reads it by that path (`repo-scaffold` §4). The
  build context therefore includes that folder — the repo root, not a
  backend subfolder — and `.dockerignore` does not exclude it. The
  `migrate` service runs this same image with the migrate command; the app
  process never migrates on start (Step 4).
- `EXPOSE` the app port, `CMD` in exec form, so the process is PID 1 and
  gets SIGTERM itself (the entry point handles it — graceful shutdown in
  `SHUTDOWN_TIMEOUT_SEC`). The entrypoint is the base image's.

## Backend image — with a shell (Python)

```dockerfile
FROM python:<pinned>-slim AS build
COPY --from=ghcr.io/astral-sh/uv:<pinned> /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev

FROM python:<pinned>-slim
WORKDIR /app
ENV PATH=/app/.venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
COPY --from=build /app/.venv ./.venv
COPY --from=build /app/<source-dir> ./<source-dir>          # and the migrate tool's config, e.g. alembic.ini
COPY documentation/db/migrations ./documentation/db/migrations
ARG APP_VERSION=dev CI_COMMIT_SHORT_SHA=unknown
ENV APP_VERSION=$APP_VERSION CI_COMMIT_SHORT_SHA=$CI_COMMIT_SHORT_SHA
USER 10001
EXPOSE 8000
CMD ["python", "-m", "<package>.bootstrap.serve"]
```

- The system user is created in the runtime stage, so its UID is fixed
  at 10001 rather than whatever `useradd` picks next.
- `PYTHONDONTWRITEBYTECODE=1`: the root filesystem is read-only, so the
  interpreter must not try to write `__pycache__`; `UV_COMPILE_BYTECODE=1`
  compiles it at build time instead, which also shortens the start.
- `CMD` is the stack's production entry (`fastapi` →
  `references/service-endpoints.md`: JSON logging configured first, then
  uvicorn with `SHUTDOWN_TIMEOUT_SEC` as its graceful timeout) — not
  `fastapi run`, never `--reload`.
- **Workers.** One worker process per container; scale by replicas, not
  workers. An app the architecture runs with several workers needs
  `prometheus_client`'s multiprocess mode, its directory
  (`PROMETHEUS_MULTIPROC_DIR`) on a tmpfs such as `/tmp` — `fastapi` says how.

## Backend image — without a shell

TypeScript:

```dockerfile
FROM node:<pinned>-<codename>-slim AS build       # the runtime's Debian branch (trixie = 13): same glibc for native modules
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build && npm prune --omit=dev           # → /app/dist and production-only node_modules

FROM gcr.io/distroless/nodejs<major>-debian<N>:nonroot@sha256:<digest>
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/package.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY documentation/db/migrations ./documentation/db/migrations
ARG APP_VERSION=dev CI_COMMIT_SHORT_SHA=unknown
ENV APP_VERSION=$APP_VERSION CI_COMMIT_SHORT_SHA=$CI_COMMIT_SHORT_SHA
USER 65532
EXPOSE 3000
CMD ["dist/<entry>.js"]                            # the entrypoint is node itself
```

The entrypoint is the node binary (`/nodejs/bin/node` — confirm with
`docker image inspect`), so `CMD` and the `migrate` service's `command:`
are node's arguments (`["dist/<migrate-entry>.js"]`), and the compose
healthcheck calls node by that full path: `node` is not on the image's
`PATH`.

Python:

```dockerfile
FROM debian:<codename>-<pinned>-slim AS build      # the runtime's Debian branch (trixie = 13)
COPY --from=ghcr.io/astral-sh/uv:<pinned> /uv /bin/uv
ENV UV_PYTHON_INSTALL_DIR=/python UV_PYTHON_PREFERENCE=only-managed \
    UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN uv python install <python-version>            # the project's .python-version / requires-python
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev --no-editable

FROM gcr.io/distroless/cc-debian<N>:nonroot@sha256:<digest>
COPY --from=build /python /python                 # same path: the venv's interpreter link points here
WORKDIR /app
COPY --from=build /app/.venv ./.venv
COPY --from=build /app/<source-dir> ./<source-dir>
COPY documentation/db/migrations ./documentation/db/migrations
ENV PATH=/app/.venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1
ARG APP_VERSION=dev CI_COMMIT_SHORT_SHA=unknown
ENV APP_VERSION=$APP_VERSION CI_COMMIT_SHORT_SHA=$CI_COMMIT_SHORT_SHA
USER 65532
EXPOSE 8000
CMD ["/app/.venv/bin/python", "-m", "<package>.bootstrap.serve"]
```

`cc` carries glibc and libgcc, which the uv-managed standalone CPython
needs; the interpreter is copied to the same path it was installed at, so
the venv's links resolve. When the stack skill documents another minimal
Python image, use that instead.

## Healthchecks through the runtime

The compose healthcheck of `backend` asks `/health/ready` with the
image's own runtime — never `wget` or `curl`, which a minimal image does
not have (and an image without them would stay unhealthy forever):

| Image | `healthcheck.test` |
|---|---|
| Node (alpine) | `["CMD", "node", "-e", "fetch('http://127.0.0.1:<port>/health/ready').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]` |
| Node (distroless) | the same with `/nodejs/bin/node` in place of `node` |
| Python (slim or distroless, venv on `PATH`) | `["CMD", "python", "-c", "import sys,urllib.request as u; sys.exit(0 if u.urlopen('http://127.0.0.1:<port>/health/ready', timeout=2).status==200 else 1)"]` |
| Frontend nginx (alpine) | `["CMD", "wget", "-qO-", "http://127.0.0.1:8081/_healthz"]` — nginx has no HTTP client of its own; busybox's `wget` is part of this image |
| Frontend nginx (no shell) | none — the kubelet probes over HTTP and needs no binary; compose treats the running container as up |

`/health/ready` touches the database, so `up --wait` means "the app can
serve", not "the process started".

## Frontend image — the reference (SPA)

```dockerfile
FROM node:<registry-checked-version>-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM --platform=$BUILDPLATFORM golang:<registry-checked-version>-alpine AS adapter
ARG TARGETOS TARGETARCH
COPY nginx/runtime.go /src/runtime.go
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH go build -trimpath -ldflags="-s -w" -o /nginx-runtime /src/runtime.go

FROM nginxinc/nginx-unprivileged:<registry-checked-version>-alpine-slim
ENV NGINX_ENVSUBST_OUTPUT_DIR=/tmp NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1 \
    NGINX_ENTRYPOINT_QUIET_LOGS=1 LOG_LEVEL=notice TRUSTED_PROXY_CIDR=127.0.0.1/32 \
    MAX_BODY_SIZE=<NFR-or-1m> CLIENT_TIMEOUT=<NFR-or-60s> BACKEND_TIMEOUT=<NFR-or-60s>
COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/templates/ /etc/nginx/templates/
COPY --from=adapter /nginx-runtime /usr/local/bin/nginx-runtime
COPY --from=build /app/dist /usr/share/nginx/html
ARG APP_VERSION=dev CI_COMMIT_SHORT_SHA=unknown
ENV APP_VERSION=$APP_VERSION CI_COMMIT_SHORT_SHA=$CI_COMMIT_SHORT_SHA
USER 101
EXPOSE 8080
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/local/bin/nginx-runtime", "/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
```

Copy `assets/nginx/` into the client. Fill only `<<SERVICE>>` (the log's component name) and `<<CONF_DIR>>`
(`/tmp` with shell). The defaults of MAX_BODY_SIZE, CLIENT_TIMEOUT and BACKEND_TIMEOUT are Dockerfile ENV,
from the project NFRs; absent a requirement use `1m`, `60s`, `60s` and report the assumption. Count encoded
request size (base64 is larger than the file). Concurrent buffered uploads also need space: document a `/tmp`
budget based on maximum upload size × concurrent uploads plus overhead, not just one file's size.

| Runtime setting | Meaning |
|---|---|
| BACKEND_SERVICE | `backend:<port>` in Compose; **FQDN:port** in Kubernetes. nginx's resolver does not apply search domains |
| BACKEND_PROTOCOL | `http` or `https`; HTTPS requires mounted `/etc/nginx/ssl/backend-ca.pem`, verifies the chain and hostname, sends SNI |
| NGINX_LOCAL_RESOLVERS | DNS servers from the container's resolv.conf through the base entrypoint; never a public DNS default |
| SECURE_MODE | `plain` behind the platform TLS proxy, or `secure` with mounted fullchain.pem and privkey.pem |
| LOG_LEVEL | nginx error severity, default `notice` |
| TRUSTED_PROXY_CIDR | immediate trusted proxy network, default loopback only; set it to the actual ingress network |
| MAX_BODY_SIZE | runtime request size limit; ingress limit must be at least this large |
| CLIENT_TIMEOUT | time between client reads/writes, including header/body reads; ingress timeouts must allow it |
| BACKEND_TIMEOUT | connect/write/read timeout to backend; ingress timeouts must allow it |

- The base renders templates into `/tmp`; nothing writes into `/etc/nginx`. Files are root-owned and readable
  by a foreign UID; test under `5000:5000`, read-only root, only `/tmp` writable.
- `proxy_pass` uses a variable plus resolver with bounded DNS cache; no static `upstream` block. An absent
  backend gives 502, while static content and `:8081/_healthz` still work. Test appearance and address replacement.
- Only `/api/` reaches backend. Public `/health`, `/health/*`, `/metrics` and `/actuator*` return 404.
  The cluster probes the backend's application port. Add no new management port.
- X-Forwarded-Proto is accepted only from a trusted immediate peer, otherwise nginx's own scheme is used.
  HTTPS verification is never disabled. Mount CA/cert files; do not copy them into the image.
- Access logs are JSON with time, level, logger, msg and request_id, without query, credential headers,
  Referer or Location. Successful probes are quiet; failures remain logged. The static runtime.go adapter
  converts native diagnostics to JSON categories, discarding raw lines that could contain credentials.
  Its error detail is deliberately limited. It forwards platform TERM/INT/QUIT to the nginx master's graceful
  QUIT, waits and reaps it, and kills the group only on a failed 28s deadline. nginx bounds drain at 25s.
  Nonzero nginx exit stays a failure. No Go compiler/source ships in runtime. Test TERM during an in-flight request.
- Fonts, JS and CSS are packaged locally. Public CDN links fail `image_preflight.py contents`.

## Frontend image — without a shell

Only by explicit user/platform choice. Keep the build stage above. In the runtime image, copy the static
assets and `nginx.conf` with `<<CONF_DIR>>=/etc/nginx/conf.d`; do **not** render environment settings at build.
Ship the templates as examples separately in the release's build folder, not as active runtime config.

```dockerfile
# Reuse the adapter build stage above; no shell is installed in runtime.
FROM cgr.dev/chainguard/nginx@sha256:<registry-checked-digest>
COPY --from=adapter /nginx-runtime /usr/local/bin/nginx-runtime
COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist /usr/share/nginx/html
ARG APP_VERSION=dev CI_COMMIT_SHORT_SHA=unknown
ENV APP_VERSION=$APP_VERSION CI_COMMIT_SHORT_SHA=$CI_COMMIT_SHORT_SHA
USER 65532
EXPOSE 8080
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/local/bin/nginx-runtime", "nginx"]
CMD ["-g", "daemon off;"]
```

The operator supplies **all rendered conf.d files** as a read-only mount, including runtime.conf (log level,
plain/secure selection), upstream.conf (resolver, FQDN, limits), trusted-proxy.conf, default.conf, healthz.conf,
plain/secure and backend-http/https.conf. Resolve only the named environment placeholders, preserving nginx
variables such as `$uri`; there are no Compose addresses or protocols baked in. Document this mount and ship
secret-free examples. Missing config must fail startup. Compose uses a rendered temporary directory mounted
read-only for its environment. The image reads no template environment variables itself.

Inspect the selected base ENTRYPOINT/CMD and prove `nginx -t`, UID 5000, health, TLS and graceful shutdown
with the mounted config. No shell-based healthcheck. Only `/tmp` writable. Shell-based live evidence does not
prove this shape; record it separately when not run.

## Runtime contents and workers

Copy `assets/dockerignore` to every build context and adapt only explicit runtime inputs. `.env*` has **no
exception**, including `.env.example`. Exclude nested test files, keys, certificates, Compose/Docker files,
.git, documentation and frontend sources from final images; keep DB migrations as runtime inputs. Public CA
roots belonging to the base are different from project credentials. A compiled output must itself exclude
tests, even when the build context is clean. `image_preflight.py contents` checks exported bytes, without sh.

A queue worker uses the backend image with its own command and one application process. It handles TERM/INT,
finishes or returns its in-flight job, closes connections and exits 0 within 30 seconds. With no HTTP, use a
heartbeat file under `/tmp` updated by the work loop (not an unrelated timer), checked for freshness through
Node/Python, or a minimal HTTP liveness endpoint. Document interval, threshold, resource budget and shutdown.
Schedulers are listed as singleton components and take a distributed lock; a replica restriction has a reason.
All images expose APP_VERSION and CI_COMMIT_SHORT_SHA; backend exports app_build_info.


## Version, date, tag

- `APP_VERSION` — the `version` of the project manifest (`package.json`,
  `pyproject.toml`); both images carry the same one. It is the plan
  folder's version (`documentation/plans/<version>/`) that the last plan
  unit set in the manifest, so the tag starts with that folder's name.
- Build date in UTC, `YYYYMMDD-HHMM`, taken once per build so both images
  share it.
- Tag: `<APP_VERSION>-<YYYYMMDD-HHMM>`, e.g. `1.4.0-20261004-0936`.
  Never `latest`.

## Architecture

`linux/amd64` unless the user says the cluster is ARM — then
`linux/arm64`. One platform per build: both at once needs a registry that
stores a manifest list, which is the operators' side, so it is not offered.
The value is the card's «Архитектура» row and the `PLATFORM=` line at the
top of `scripts/build-images.sh`; the sync test holds the two together.
The flag is explicit because a build on Apple silicon otherwise produces
`arm64` images that do not start on `amd64` servers, and the reverse.

## Hand-over: one tar and the release folder

Images are handed over as one file, never pushed to a registry. Write
`scripts/build-images.sh` (and a `build-images` task-runner target) that:

1. reads the version from the manifest, takes the date once, and sets
   `PLATFORM` from the card;
2. builds each image with
   `docker buildx build --platform "$PLATFORM" --load --build-arg APP_VERSION="$APP_VERSION" --build-arg CI_COMMIT_SHORT_SHA="$(git rev-parse --short HEAD)" -t <project>-<backend|frontend>:<tag> -f <Dockerfile> <context>`;
3. saves both into one archive named after the project and the service
   version, in that version's release folder:
   `docker save <project>-frontend:<tag> <project>-backend:<tag> -o release/<APP_VERSION>/<project>-<APP_VERSION>.tar`
   (e.g. `release/1.4.0/room-booking-1.4.0.tar`);
4. puts every other file the operators get beside it:
   - `documentation/deploy/deploy.md` → `DEPLOY.md`, replacing `<версия>`
     with the version and `<тег>` with the image tag;
   - `documentation/deploy/prod.env.example` → `<project>.env.example`
     (`deploy-doc.md` → The variables file);
   - `documentation/api/openapi.yaml` → `openapi.yaml`, one file: a split
     contract (a `$ref` that points at another file) is bundled, a single
     file is copied —

     ```bash
     api=documentation/api/openapi.yaml
     if grep -Eq '\$ref:[[:space:]]*["'\'']?[^#"'\''[:space:]]' "$api"; then
       npx --yes @redocly/cli bundle "$api" -o "release/$APP_VERSION/openapi.yaml"
     else
       cp "$api" "release/$APP_VERSION/openapi.yaml"
     fi
     ```
   - `documentation/operations/operations.md`, when it exists →
     `OPERATIONS.md` (`operations-doc`);
   - each actual Dockerfile and `.dockerignore` → `build/<component>/Dockerfile` and `build/<component>/.dockerignore`;
     include the build command, context path and source commit (sources are obtained from that commit separately);
   - after scanning, the complete per-image reports, manifest and any approved dated risks in `scan/`.
5. checks the folder against `DEPLOY.md`, so an operator never gets an
   instruction for a file they do not have. A file name is a backtick span
   with no space or `/` that ends in a known extension — a logger name
   (`<project>.migrate`), a field (`res.statusCode`) or `schema.table` is
   not one; a line with «создайте» names a file the operator makes, so it is skipped:

   ```bash
   missing=0
   for f in $(grep -vE '[Сс]оздайте' "release/$APP_VERSION/DEPLOY.md" \
       | grep -oE '`[^` /]+\.(tar|md|yaml|yml|example|pem|crt|key|sql|json|txt|env|local)`' | tr -d '`' | sort -u); do
     [ -e "release/$APP_VERSION/$f" ] || { echo "DEPLOY.md называет $f, а в release/$APP_VERSION/ его нет" >&2; missing=1; }
   done
   [ "$missing" -eq 0 ] || exit 1
   ```
6. prints the folder, the tar size, both image names with tags and the
   platform.

The file name carries the version so the releases sit side by side and an
older one is still there for a rollback; a rebuild of the same version
replaces its folder's contents (the build date is in the image tags inside).
`release/` is in `.gitignore` and `.dockerignore`.

The receiver runs `docker load -i <project>-<APP_VERSION>.tar`; both images
appear with their tags, and they load them into their own registry
themselves. Put that line, the tag format, the platform, the release folder
and the variable table above in the README's «Сборка образов» section.
