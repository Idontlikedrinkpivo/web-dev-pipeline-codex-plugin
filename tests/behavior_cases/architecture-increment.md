# Architecture increment behavior cases (U22)

These cases require an observed orchestrator/writer run with a read trace.
Structural assertions in `test_architecture_policy.py` check policy text only;
they are not evidence of implementation behavior.

## B1 — one-area increment with a shared dependency

Status: NOT_RUN — no orchestrator/writer behavior run was exercised.

Fixture: an existing Modest service has bookings and maintenance areas;
only `bookings/create` changes. Its scenario references shared `Money` and
an existing booking repository signature. The maintenance area has no reference
from the changed operation, type or rule.

Action: request the bookings increment. Capture the initial read scope, writer
packet and actual read trace before any document is changed.

Expected: read the bookings SRS group, changed API operation/schema constraints,
affected scenario/domain sections and referenced shared foundation/dependencies
(Money, repository signature, level/stack). Do not read maintenance scenarios
or unrelated API/migration files in advance. A missing signature may cause a
read of its owner section; an expansion must name a real dependency conflict
and path. The report describes untouched scope without claiming unread content
was revalidated. Unchanged sections stay verbatim in the complete output.

## B2 — explicit durable lighter level

Status: NOT_RUN — no orchestrator/writer behavior run was exercised.

Fixture: user explicitly chooses Framework-first + one boundary for a durable
CRUD service, accepts framework coupling, fewer isolated use-case tests and
future extraction costs. No requirement conflicts with the single rule boundary.

Action: run level selection and dispatch, then resume the increment once.

Expected: carry the choice, tradeoffs and constraints to ANSWERS and «Уровень»;
continue without another level question on either run. Keep the framework
shape, framework-free rule module and one checked edge; do not introduce
ports/DTO layers from the generic examples or promote merely for longevity.

## B3 — a concrete requirement conflicts with the selected boundary

Status: NOT_RUN — no orchestrator/writer behavior run was exercised.

Fixture: the lighter design exposes one shared response shape containing
protected salary data; a new explicit requirement forbids that field reaching
the contractor audience. The current boundary cannot enforce that separation.

Action: request the affected operation increment with the existing lighter choice.

Expected: identify the salary requirement and incompatible shared response
boundary in one named question; wait for the answer before changing level.
Do not use a Full-trigger label alone as proof or silently override the choice.

## B4 — unavailable D2/PlantUML renderer

Status: NOT_RUN — renderer-unavailable writer behavior was not exercised.

Fixture: the chosen mode needs a D2 view or key-scenario PlantUML source;
the corresponding renderer is absent.

Expected: retain the real `.d2` / `.puml` source and report `svg: missing`.
Do not install a renderer, generate a placeholder SVG or claim rendering success.
