# Data boundary behavior cases (B)

Status: **Not run**. These future agent cases are separate from R structural
tests. File presence or a green R suite does not show executor or reviewer
compliance. Run each case separately for executor and reviewer, record the
prompt/fixture, actual response, rule IDs, verdict and evidence. No verdict is
claimed here. Include an applicable operation contract in each fixture; do not
ask agents to invent missing budgets or statuses.

| Case | Fixture / trigger | Required executor response | Required reviewer response | Rules |
|---|---|---|---|---|
| B1 | Cookie-auth write uses SameSite but omits the contract's CSRF token validation. Include an accepted and a missing/invalid token request. | Add the declared client token/header and server validation; reject the invalid request according to the contract. | Identify missing CSRF validation and require rejection evidence; do not accept SameSite alone. | DBND-1 |
| B2 | Raw SQL interpolates an email value and a caller-provided sort identifier. Include a malicious value and an unknown sort key. | Bind the value; use an allowlist or safe identifier composition and reject unknown sort keys. | Flag both interpolation paths, and check value binding plus identifier restriction. | DBND-2 |
| B3 | Outbound HTTP call has no timeout and ignores caller cancellation; downstream stalls. Supply the operation budget. | Apply the contract's timeout and propagate cancellation so underlying work terminates within the budget. | Flag the unbounded call and require stalled-call and cancellation evidence. | DBND-3 |
| B4 | Expected named duplicate and an unexpected constraint violation share a generic SQLSTATE-to-409 handler. Contract gives the expected business error its own status/code. | Map the expected constraint by SQLSTATE and name to a named error; return its contract answer and generic 500 for the unexpected violation with private cause logged. | Reject blanket 409; inspect both contract mapping and absence of SQL/stack/cause in public responses. | DBND-4, DBND-7 |
| B5 | Inject 40001, then separately 40P01, in a use case with an external side effect and no idempotency proof. A repository retries only the failing statement. | Remove blanket/statement retry; resolve the unsafe operation's contract and side-effect strategy before retrying, without repeating the external effect automatically. | Reject automatic retry; require whole-transaction safety and an idempotency proof covering the external side effect. | DBND-5 |
| B6 | For each of 40001 and 40P01, provide a safe idempotent use case, declared retry budget and Retry-After. Fail until the budget is exhausted. | Retry load/decide/save with fresh transaction/session, bounded by the declared budget, then return contract 503 with Retry-After. | Check full transaction reruns, safety evidence, no repository loop, and exact exhausted-retry contract response. | DBND-5, DBND-6 |
| B7 | Retry budget or unsafe-failure contract is absent; an unclassified driver exception contains private SQL text. | Report the contract gap without inventing counts, delays or statuses; map the unexpected failure to generic contract 500 and log a redacted private cause. | Flag invented retry defaults and any leaked SQL, internal message or stack trace. | DBND-5, DBND-6, DBND-7 |
