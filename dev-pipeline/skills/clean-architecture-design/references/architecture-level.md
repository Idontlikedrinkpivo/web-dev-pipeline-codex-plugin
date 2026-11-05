# Step 2. Decide how much architecture is justified

Read at Step 2 — the orchestrator before grading (Orchestrator step 4) and
the foundation writer before recording «Уровень».

**Modest is the CRUD recommendation**, with `domain/`, `application/`
and `adapters/` and a linted edge. A CRUD entity can stay short
(constructor checks, no service). This is a recommendation, not a mandatory
floor: the user may choose an explicit lighter level, including the existing
Framework-first + one boundary for a durable service.

An explicit choice in the request/ANSWERS, or the existing «Уровень» row on
an increment, answers the level question: do not ask again. Record the
tradeoffs (framework coupling, fewer isolated use-case tests, and the cost
of extracting another boundary later), the chosen machine-checkable boundary
and constraints in «Уровень». Keep that choice unless a real requirement conflict
exists. Name the requirement and the boundary that cannot satisfy it in one
question; wait for the answer before changing level. A preference for more
layers, longevity alone or a trigger's label is not such a conflict.

The foundation records one level as the «Уровень» row of §1 «Ключевые
решения»; every mode then **stays inside its limits** — the scope
decision is worthless if the domain model or a scenario adds the
ceremony of the level above. The limits are about what the design
contains, never about how long a document is:

| Level | When | What the design contains | Limits |
|---|---|---|---|
| **Framework-first + one boundary** | a named throwaway prototype (days to weeks), or the user's explicit lighter choice for a durable system with recorded tradeoffs and constraints; never selected silently | framework shape kept; the few real rules in one framework-free `domain/` module; one lint rule on that edge; reads via the ORM directly | no ports folder, no output DTO (the framework's request/response model is the boundary), ≤ 1 lint rule |
| **Modest** | the default: any system that outlives a prototype and has no Full trigger, from plain CRUD to a handful of real rules | `domain/`, `application/`, `adapters/`; rich entities for the real rules; ports as plain interfaces next to the use cases; framework models as storage models; reads via query functions in adapters, no use case | ≤ 3 lint contracts; a frozen input type per write use case, entity or read model out, no output-DTO layer; no `Clock`/`IdGenerator`/`UnitOfWork` unless a named test or a multi-aggregate save needs it |
| **Full** | recommended for **any Full trigger below**, subject to the explicit-choice rule above | all of the above plus input and output types on the use-case boundary, write ports in `application/ports/` as their own lint layer, separate storage models with mappers, domain events where the requirements need them | one artifact per file |

**Full triggers** — any one recommends Full even on a two-person team;
with an explicit lighter choice, assess the actual requirement before raising a conflict:

- a versioned public or partner API: an external consumer the team does
  not deploy depends on it. A `/v1` URL prefix alone is not one;
- sensitive data that different audiences must not see (query ports per
  audience): two or more actor groups with different field sets across
  several read models. Hiding the owner or some fields on other users'
  rows is a projection in one read model, not audiences;
- a mandatory external report that must not be lost. A notification
  retried until delivered is an outbox, not a report.

**Otherwise recommend Modest when no level is already chosen.** Long life or many rules without a trigger stay
Modest. "We want Clean Architecture", "so we don't have to rewrite it
later", and "we write code with an AI agent" are not promotions; they
raise the enforcement bar (foundation §6), not the layer count. Never
build layers "for later" — add the next boundary after friction appears,
and say in `open-questions.md` what that friction would look like.

