# Stack skills for a unit

A worker writes better code with the house rules of its language and libraries — and none of them reaches it
unless `work` names them in the packet. Pick them from the architecture's §1 «Стек» and the unit's `Файлы` (and
its «Цель» where the table says so), and list in `STACK SKILLS` the absolute path of each `SKILL.md` under
`SKILLS ROOT` (a `references/` file only where the table names it or the skill's text sends the worker to it for
this unit), plus any skill the user attached. For every entry specify main rules + named sections, their exact
headings (or the whole short file), and the files/goal that require them. The worker reads that scope from disk
before it writes code. They are not
pasted: three or four skills are tens of kilobytes the session would type into every dispatch, two per unit for a
two-phase one (`executor-catalog` → Dispatch contract → Paths, not pasted documents). A skill's
`references/version-checks.md` is never listed: Step 2b turns it into the answers in `CURRENT LIB DOCS`
(`context7.md`).

| The unit's files | Stack skills |
|---|---|
| any `.ts` / `.tsx` | `typescript` |
| React components and hooks (`.tsx`, `use*.ts`; test files are the test row) | `react`; for a screen or component source file also `frontend` with its one profile and `web-design-guidelines` (SKILL.md → Inputs) |
| Fastify routes, plugins, the server factory, the error handler | `typescript-fastify` |
| the contract test (`tests/contract/openapi.contract.test.ts`) | `typescript-fastify` and its `references/contract-test-template.ts` |
| TypeScript login, registration, password hashing, tokens, the current-user and role guards | `typescript-fastify` and its `references/auth.md` |
| Drizzle tables, repositories, queries, migrations runner | `typescript-drizzle-orm` |
| Zod schemas, the wire boundary, a form schema, env parsing | `zod-skill` |
| `*.test.ts` / `*.test.tsx`, test helpers, `vitest.config` | `vitest`; a React test file or test helper also `react` — never `frontend` or `web-design-guidelines` |
| any `.py` | `python` |
| FastAPI routers, dependencies, the app factory, exception handlers, settings | `fastapi` |
| login, registration, password hashing, tokens, the current-user and role dependencies — by its files or its «Цель» | `fastapi` and its `references/jwt-auth.md` |
| the contract test (`tests/contract/test_openapi_contract.py`) | `fastapi` and its `references/contract-test-template.py` |
| SQLAlchemy models, repositories, sessions, the unit of work; Alembic revisions and `env.py` | `fastapi-sqlalchemy` |
| `tests/`, `conftest.py` | `pytest-patterns`; a new or rewritten `tests/conftest.py` also its `references/conftest-template.py` |
| Playwright specs and config | `playwright-cli`, but not its `SKILL.md` (the browser-driving loop): list `references/test-config.md` and `references/playwright-tests.md`; add `references/test-generation.md` when the unit records specs from the running app or heals failing ones — of it only its «Inside dev-pipeline» block, §0 and §3.1–3.3 apply, and the packet says so |

A unit that touches several kinds gets every skill that applies. A stack the table does not name gets no invented
pack: `none — no stack skill for <stack>`.

The reviewer of the unit (`code-review-unit`) receives the «The reviewer checks» section of each of these skills
that has one — every language and library skill above does — so the review looks at what the linter cannot.

## Bounded reading coverage

Keep each selected skill's main rules, runtime/conflict instructions and any dependency needed to understand
the selected sections. Do not split a short file artificially: read it whole; also expand to a whole file when
the selected rules depend on it. There is no arbitrary byte limit. Selection narrows unrelated material, never
mandatory auth, authorization, security, error handling or tests triggered by the files or goal. The selection
table above still applies in full; the fixtures below show the required scope, not substitute skill contents.

| Routing fixture | Required anchors and scope |
|---|---|
| Hook-only (`use*.ts`) | `typescript` and `react`: main rules, `The machine checks` and `The reviewer checks` (use the full heading from each file); no unrelated `frontend` screen/profile or `web-design-guidelines` pack. |
| Auth by files or goal | TypeScript: `typescript-fastify` — `Which contract and layout apply`, `Rules`, `Errors`, `references/auth.md`; Python: `fastapi` — `Conventions`, `Errors as problem+json`, `Auth and configuration`, `references/jwt-auth.md`; required guards, authorization, secrets and auth tests remain mandatory. |
| Query/repository | `typescript-drizzle-orm` — `Which layout applies`, `Rules`, `Shape of a repository adapter`; `fastapi-sqlalchemy` — `Which layout governs — decide first`, applicable layout, `Session and unit of work`, `Driver errors and install`, plus `Models and column types`, `Relationships under AsyncSession` or `Migrations` when touched; preserve security/isolation and transaction/error rules. |
| Reviewer | Every applicable skill's `The reviewer checks` section is mandatory, including auth/security/query references selected for the implementer; use exact headings, keep their dependencies and the unit's independent checks. |

For test files retain the language and test-skill rows above; React tests still get `react` without a screen
pack. For a mixed unit take the union of all applicable scopes. A missing anchor or uncertain dependency means
read the containing file and resolve coverage before dispatch, not silently omit a mandatory rule.
