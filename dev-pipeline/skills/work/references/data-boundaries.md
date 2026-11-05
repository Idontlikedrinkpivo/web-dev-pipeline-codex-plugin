# Data boundaries

Shared executor and reviewer rules for application code. This reference defines
policy; it does not implement authentication, a database client or an HTTP
adapter. Stack skills keep their library-specific code and link the applicable
stable IDs below. Existing correct contract statuses remain unchanged.

## Rules

| Rule ID | Contract | Executor check | Reviewer check |
|---|---|---|---|
| DBND-1 | A state-changing request carrying cookie credentials requires the contract's CSRF strategy. SameSite alone is not universal proof of protection. | Implement the declared CSRF strategy on the server and carry its required token or headers from the client. | Trace a cookie-auth write through client and server; require evidence of the declared CSRF validation, including rejection. |
| DBND-2 | Raw SQL values use bound parameters; identifiers use an allowlist or the driver's safe composition API, never untrusted text. | Bind every value separately; reject unknown identifiers before selecting trusted SQL fragments or composing identifiers safely. | Inspect raw SQL examples and call sites for interpolated values and identifier paths that bypass the allowlist or safe composition. |
| DBND-3 | Each outbound HTTP call has a timeout and abort/cancellation within the operation budget. | Propagate cancellation and release resources; derive the timeout from the remaining operation budget and the contract. | Check stalled downstream calls and caller cancellation; verify completion is bounded and underlying work is cancelled. |
| DBND-4 | An expected duplicate becomes a named business error classified by SQLSTATE and constraint name; its status comes from the contract, never blanket SQLSTATE => 409. | Map only expected named constraints to domain exceptions with fields; preserve their causes and let other failures propagate. | Compare named-error mappings with the contract; reject generic duplicate-to-409 handlers and message-string classification. |
| DBND-5 | 40001 and 40P01 permit bounded whole transaction retry only with demonstrated idempotency and safe side effects. | Keep driver failures intact in the repository; place one shared retry wrapper around the complete use case with a fresh transaction/session. | Require an idempotency proof for the entire operation and external side effects before approving retry; reject statement-only or repository loops. |
| DBND-6 | Only exhausted safe retry maps to the contract's 503 with Retry-After; the contract defines retry limits and the header value. | Apply the declared attempts and duration limits; render the contract's response only after eligible retries are exhausted. | Check the safety gate, exhaustion path, response schema and Retry-After against the operation contract without adding default budgets. |
| DBND-7 | An unexpected or unclassified failure maps to generic contract 500; its private cause belongs in logs, never the response. | Preserve the exception cause for private logging and return only the contract's generic public detail. | Verify the response excludes driver messages, SQL, stack traces and private context while logs retain a safely redacted cause. |

## Database failure mapping

| Rule | Condition | Repository / use case | HTTP boundary |
|---|---|---|---|
| DBND-4 mapping | Expected constraint identified by SQLSTATE and constraint name | named business error with fields and preserved cause | contract status and code for that named error; never blanket SQLSTATE => 409 |
| DBND-5 mapping | 40001 or 40P01 | propagate unchanged from repository; safe whole transaction retry in shared use-case wrapper with fresh session; no automatic retry when unsafe | Apply DBND-6 only after safe retry exhausted; otherwise use the operation's explicit failure contract |
| DBND-6 mapping | safe retry exhausted | Preserve final failure and exhaustion context for the handler | contract 503 + Retry-After |
| DBND-7 mapping | unexpected / unclassified, including unexpected constraint violation | Preserve cause; do not relabel as an expected business conflict | generic contract 500; private cause in logs |

The retry unit is the whole transaction: load → decide → save, with rollback
and a fresh session for every new attempt; never one statement. The repository never loops,
and domain/use-case logic does not inspect driver codes. The
composition layer supplies the shared wrapper and persistence classification.

Before retrying, establish an idempotency proof that includes external side
effects (payments, mail, remote writes), not just database rollback. Repeatable
database work alone does not make an external effect safe. Use the operation's
declared idempotency mechanism or side-effect strategy; unsafe retry is not
automatic. Missing safety evidence or an unspecified unsafe-failure answer is a
contract gap to resolve, not permission to choose a status or rerun the effect.

The contract owns attempts and duration, backoff, the operation budget and
Retry-After. Do not invent universal retry counts, delays, timeout values or
statuses when that contract is missing. Preserve current correct application
statuses. Library exception accessors, cancellation APIs and adapter-specific
mapping code belong in the stack skills, not in this shared policy.

## Bound SQL example

Illustrative DB-API placeholder style; use the actual driver's parameter syntax.
Only fixed allowlisted identifier fragments are composed here. Unknown sort keys
are rejected before executing SQL; `email` remains a bound value.

```python
columns = {"created": "created_at", "name": "display_name"}
column = columns[sort_key]
cursor.execute(
    "SELECT id FROM users WHERE email = %s ORDER BY " + column,
    (email,),
)
```

## Evidence boundary

R structural tests prove presence, not real behavior. They check unique IDs,
required mappings, retry constraints and the sample's bound values. Future B
cases in `tests/behavior_cases/data-boundaries.md` measure whether an executor
or reviewer actually follows these rules. A passing R check is not evidence of
agent compliance, CSRF protection, transaction safety or HTTP cancellation in an
application. Consumers are wired separately; this reference alone changes no
agent's instructions.
