# Application configuration and stand inputs

The application owns the catalogue. Put the schema beside config in its own module and re-export it from config.
For Zod use [the TypeScript template](env-doc-typescript.md). For pydantic-settings use
[the Python template](env-doc-python.md). Install the adapted generator, tests and commands in the **project**.

Each application entry has a parser, block, required flag, secret flag, one Russian line of purpose, an optional
default and a production example. Include variables consumed by other shipped processes, including the frontend.
Keep Compose-only inputs in a short adjacent list (name, secret, purpose). Reference entries by name for test/dev
membership. Keep default values in the schema. Startup and docs derive required keys from required entries
without defaults. Treat an empty string like an absent input **before parsing**, including numeric or enum values.
Keep the mock guard, requirement conditions and cross-field checks in config. Never include secret values in errors.

## Generated artifacts

`env:doc` writes three tracked outputs. `env:check` renders in memory, lists every missing or stale path and
exits nonzero, without writing. Preserve everything outside the marked tables, and reject missing, duplicate
or unpaired markers. Neither command opens machine-local env files or loads application settings.

- `deploy/prod.env.example` contains the production variables in schema block order, including frontend inputs.
  A secret example is empty or an angle-bracket placeholder.
- `documentation/deploy/deploy.md` contains the generated production variable tables between paired
  `<!-- env-doc:start -->` and `<!-- env-doc:end -->` markers (preserve existing paired block markers on migration).
- Root `.env.example` lists exactly the documented local inputs for **each** stand. A key may occur in both
  sections. The only section titles are the filenames. Examples are empty except safe machine defaults.

Both env outputs have the same layout. Omit inapplicable markers and separate pairs and blocks by a blank line.

```dotenv
# ===== .env.dev.local =====

# [required] [secret] Токен внешнего сервиса
API_TOKEN=

# Интерфейс сайта на этой машине
DEV_BIND=127.0.0.1
```

## Stand and runtime contract

Keep fixed stand values in Compose `environment:`. Machine-local files hold only secrets and per-machine
values. Compose overrides `env_file`: never shadow a local input with a fixed value. Use `${VAR:-default}`
where Compose needs interpolation, with `--env-file` for the matching stand. Empty external model addresses
select the test stub. Bind ports on loopback, with `DEV_BIND` configurable only for the dev site.
The test file is optional and created empty at 0600 by Make if absent. The dev file is required.
An operator supplies production credentials and separate DATABASE_URL values for the migration owner and
the data-only backend. Preserve the documented schema/search_path. Host tests use their own TEST_DATABASE_URL.
Host-side CI reaches the standalone test DB through loopback and keeps its schema/search_path and mock gate.
Document LOG_LEVEL (info), SHUTDOWN_TIMEOUT_SEC (25) and any enabled tracing settings in the schema.
Allow the backend at least five extra seconds to drain in the stand's stop_grace_period.

## Project acceptance tests

Compare all three outputs byte-for-byte with a fresh render. Mutate each artifact and assert check reports the
path, exits nonzero and leaves it untouched. Check headings, marker order, immediate adjacency to NAME=value,
blank lines, uniqueness within each block and placeholder-only secrets. Validate schema names across application
and Compose entries, one-line purposes, parseable defaults, required keys and empty-value behavior.
Compare the per-stand documented local keys to its actual supported inputs (env_file consumers plus Compose
interpolation). Parse the tracked Compose files, using synthetic local files in tests. Reject fixed overrides of
a local input. Test both stands, a legacy dev file with extra keys, first creation/mode and preservation of an
existing test file. Exercise the release target with a stale output and a Docker spy: it must fail before Docker.

## The fail-fast rules, as a checklist for the app's own config/settings code

Write these as validation in the same place the app already parses its
config (a `Settings` class, a config module, whatever the stack's convention
is) — not as a compose-time check, not as a comment asking someone to
remember:

1. **Env selector is required.** No default. An unset selector must crash
   at startup, not silently pick one environment's behavior.
2. **The mock gate refuses outside test.** If the mock-fixtures variable is
   set and the env selector is not `test`, crash with a message naming both
   values — this is the one rule most likely to matter, because it is the
   rule that turns "someone copied a compose file wrong" into "prod served
   fixture data" if it is missing.
3. **Security flags that assume a network topology contradict, not just
   default.** A flag like "cookies require HTTPS" being true is not itself
   proof a TLS terminator exists — but that flag being true while a paired
   "we are behind TLS" flag is false (or vice versa) is a real
   contradiction worth crashing on, where the app can express one.
4. **No default for a prod/dev secret.** A missing required secret is a
   startup crash naming the variable in the app
   — an empty string that silently "works" until the first real call fails
   is worse than a crash at boot.
5. **Resource-budget arithmetic, if the architecture named one.** Worker
   count × per-worker connection/resource usage ≤ the configured limit,
   checked at startup. A misconfiguration should fail the readiness check
   before it exhausts a shared resource under load.
6. **An optional variable still has a type.** Unset means the default; set
   to something outside its set — `LOG_LEVEL=verbose`,
   `SHUTDOWN_TIMEOUT_SEC=30s` — is a startup crash naming it, so a typo in
   the operators' manifest does not quietly run with the default.

## Platform acceptance rules (IMG / CFG / FS / LC / OBS / RES / SEC)

These rules apply from scaffold and implementation, not only when packaging:
- Required secrets have no defaults. A missing/empty secret, known placeholder (`change-me`, `admin`, `secret`)
  or a required secret under 32 characters fails startup with the variable name, never its value.
  First-admin credentials come only from env/Secret, never seeded fixed credentials in code/config/migrations.
- Each integration has URL, connect/read/response timeout, pool size and `<INTEGRATION>_ENABLE`. No real host,
  IP or personal email in defaults. Secrets are env or separate files, not the shared non-secret config file.
- TLS verification is always enabled. Corporate CA is a mounted file configured by `<INTEGRATION>_SSL_FILE`,
  SSL_CERT_FILE / REQUESTS_CA_BUNDLE / NODE_EXTRA_CA_CERTS. Never `verify=False`, `ssl=False`,
  `rejectUnauthorized:false` or NODE_TLS_REJECT_UNAUTHORIZED=0. Outbound destinations and data categories need
  explicit approval before user data leaves the agreed contour; document host/port/protocol/purpose.
- `TRUSTED_PROXIES` is an explicit network allowlist (empty means trust nobody); `PUBLIC_BASE_URL` determines
  externally generated links. Secure-cookie and forwarded IP/scheme follow these settings, not arbitrary headers.
- Generated API pages are disabled in prod; admin interfaces are disabled or authenticated. No reload/debug/demo
  or mock mode in prod. Keep the machine-readable OpenAPI in the release, independent of runtime docs routes.
- Sessions, rate limits, shared caches, locks and queues live externally. If only one replica is possible, write
  why. Scheduled jobs use distributed locks with ownership/expiry appropriate to the job.
- Migration runners serialize concurrent invocations (DB advisory lock or one separately managed migration job),
  record completed versions, and document clean-DB and parallel-start tests. Migrations are a separate command by
  default; if auto-run exists, MIGRATIONS_ENABLED=false disables it. Dependency outage is not a missing-config
  error: valid config with unavailable DB/Redis stays live and unready, retries boundedly and recovers.
- Node heap is budgeted from the container memory limit with native overhead; document NODE_OPTIONS and measured
  memory per process. Pool sizes and concurrency obey the replica budget. Export pool and queue metrics when used.
- Runtime paths and peak write volume are documented, including concurrent upload buffers. Persistent paths are
  configurable outside /tmp, with capacity, access mode and backup needs. Never file logs.

Describe all application settings once in the typed schema. APP_VERSION/CI_COMMIT_SHORT_SHA are baked build provenance, read by code; operators do not override them.
