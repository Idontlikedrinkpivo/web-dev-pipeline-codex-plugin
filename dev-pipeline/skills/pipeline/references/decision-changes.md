# A decision changed after its document

Read whenever a decision changes after the stage that wrote it down has
closed — in `work`, in a later stage, or in the chat between stages. The
document is updated in the same step, without the user asking, and the
change is committed before the work that depends on it goes on. A decision
that lives only in code or in the chat leaves every later stage, reviewer
and plan reading the old one, and nothing says which is true.

## What counts

- **The user answers a stop** — `BLOCKED` on a missing design decision, a
  review's `STOP`, a gap a writer or reviewer named.
- **The user changes a decision mid-stage** — «давай по-другому», «убери
  это поле», «пусть отмена будет без подтверждения».
- **A fact overrules the document** — the library cannot do what the
  design says, the installed major differs, a port or a name is taken —
  and the replacement is settled: by the user, or by the stage when that
  choice is the stage's own (an unverified version assumption checked by
  `repo-scaffold`).
- **A run shows the spec, not the code, is wrong** — the user rules so on a
  test-run defect or a review finding.
- **The user accepts a risk** on a security-audit finding («Принять риск»)
  — a row of architecture §1 «Принятые риски»: the risk, the audit's
  version and finding id, the user's reason, the date.
- **The user keeps a deviation** from the plugin's rules on a code audit
  («Оставить как принятое отклонение», `upgrade-code`) — a row of
  architecture §1 «Принятые отклонения»; or decides to fix one, and the
  document changes to how it should be before any code does.

Not a changed decision: a worker's local choice inside what the documents
fix (the run report's `Decisions` hold it), an implementation detail no
document names, and an edit inside the stage that owns the document — a
grill reversal or an applied review finding on the document the stage is
still writing is that stage's own work.

## The owner

| What changed | Owner document | Writer that edits it |
|---|---|---|
| product behaviour, a business rule, a limit, an actor's right, an acceptance criterion | SRS — `srs.md` and the area file | `srs-author`, `MODE grill-reversal`, the decision in `REVERSALS` |
| a table, a column, an index | DB schema, plus a new migration file — in the folder `schema.md`'s `migrations:` names when the schema was written as it is; the plan's first unit makes it applicable, so `migrate` is not run on the branch before it | `doc-typist`, `MODE revise` |
| an operation, a field, a status or error code | OpenAPI | `doc-typist`, `MODE revise` |
| a module, a layer, a port, an adapter, a configuration variable, a stack version | architecture foundation | `doc-typist`, `MODE revise` |
| an entity, an invariant, a named error | domain model | `doc-typist`, `MODE revise` |
| a step of a flow, a transaction boundary | the scenarios of the area | `doc-typist`, `MODE revise` |
| an element, a text or a state of a screen | the screen spec, and the frame when the look changes (`ui-design`, `figma-sonnet`) | `screen-writer`, as an increment of that screen (`screen-spec` → its packet) |
| an expected result of a case | the test cases (unversioned) | `ui-test-writer`, as an increment of that section |

The session does not edit a contract document by hand: the writer keeps
the template's shape and the ids that other documents cite.

## Под родительским чатом

When an iteration uses a parent and one chat per stage, only the owner's stage chat edits
its document. This overrides direct writer dispatch in every row of «Where it applies»:
SRS/API gaps in screen specs, changed behaviour in mockups, work BLOCKED, requirement defects
found by tests, upstream grill/review contradictions, and decisions between stages.
The owner has the interview and accepted wording; one writer prevents overlapping edits;
the parent sees both branches and warns affected owners; owner handover and reflect see the change.

1. The discovering stage records `<было> → <стало> · решил <кто>` under «Изменённые решения»
   in its own report. It edits only its own document, never starts another stage's writer,
   and sends the parent:
   `РЕШЕНИЕ · <было> → <стало> · решил <кто> · владелец: <этап> · жду`.
   After the parent routes it, finish the turn to the user:
   `Решение ушло в «<название чата владельца>»; продолжу, когда документ обновят`.
   If there is no owner chat, name the parent handling it; never invent a successful delivery.
2. The parent finds the owner in the iteration registry, ensures one active writer, marks it «идёт»,
   and sends `РЕШЕНИЕ ИЗМЕНЕНО · <было> → <стало> · решил <кто> · от <этап>`.
   If the owner has no chat (fresh clone or work done by another person), the parent uses the
   owner's writer itself. A different stage chat never substitutes for the owner.
3. The owner applies the ordinary steps below to its document: writer, check, commit and push
   under existing publication permissions, without a version bump. The checked owner-close commit
   carries `Stage-Closed: <key> <iteration-version>` per offer-at-close.md, so the new input is ready.
   It replies:
   `РЕШЕНИЕ ЗАПИСАНО · <документ> · коммит <sha> · задеты: <документы других закрытых этапов, повторяющие старое решение, или «нет»>`.
   The parent verifies the commit, marks the owner «закрыт», and routes affected closed documents
   to their own stage chats by the same protocol, one writer per document. Future stages read the
   updated source when they start. Do not resume dependent work while an affected input is unsettled.
4. The parent sends the waiting stage `продолжай: <документ> обновлён, коммит <sha>`.
   In the shared checkout no pull is needed. Only after the owner's commit does the waiting stage
   repair consequences in its own document; its report retains the decision and commit reference.

Without a parent, the single session still invokes the owner's writer itself as before.
The steps below run inside the owner, or in that single session; their batching never grants
one child permission to edit documents belonging to other stage chats.

## The steps

1. **Write it down first.** One line in the stage's report under
   «Изменённые решения» — `<было> → <стало> · решил <кто> · документы ·
   код по старому решению` — so a compaction or a stop mid-way cannot lose
   the decision.
2. **Find every document that states the old decision.** The owner, plus
   the documents downstream of it that repeat it: search `documentation/`
   for the changed token (an id, a column, an `operationId`, a variable)
   and read the hits, using `pipeline` → Increments («Changed → Names») for
   where to look.
3. **Edit them**, owner first, each through its writer with one
   `SETTLEMENT` line per change and nothing else. The documents `doc-typist`
   edits (schema, OpenAPI, architecture, domain, scenarios) go in **one**
   `doc-typist` dispatch for the decision — owner first in its list, every
   file's lines in the same packet — not one dispatch per document: each
   dispatch costs its start again. A downstream document
   whose change needs design judgment rather than a line edit — a scenario
   whose flow changes shape — is its stage's increment: stop and ask, with
   that stage named.
4. **Check it landed**: the new wording is in each file, the old one is
   gone, the ids that other documents cite still resolve.
5. **Commit at once**: one commit per decision, staging only those
   documents (and a new migration file or re-rendered diagram that belongs
   to them), message `docs: решение изменено — <кратко>`; inside a `work`
   run add the trailer `Plan-Unit: <version>/decision-<n>` (`<n>` the next
   free number; `work/scripts/plan_state.py` lists the iteration's
   trailers), so `code-review-full` maps the commit to the run instead of
   reading it as stray. Leave `version`,
   `updated`, `info.version`, the changelog and the pins as they are: like a
   move, this commit needs no request from the user, and the next stamp
   (`doc-versioning`) types these changes, because it compares each
   document with its last stamped state, not with `HEAD`. Edits of this
   iteration still uncommitted in the same file go into this commit too;
   the stamp types them all the same way. Before `work`, the commit is
   pushed — a changed decision is final at its commit
   (`scripts/push_branch.py`, `SKILL.md` → Commit each document).
6. **Then go on.** What runs next reads the new text.

## Work already built on the old decision

- **Code.** In `work`, a committed unit that implements the old decision
  gets a follow-up commit through its own executor, like a fix after a
  commit, carrying that unit's `Plan-Unit:` trailer, and listed in the run
  report. Outside `work`, the stage report names it as a fix for the next
  plan; when the user wants it now, it goes through `work` → "A change
  asked in chat outside a run", never typed by the session.
- **The plan.** `work` never edits the plan. A unit whose text contradicts
  the changed decision gets, in its packet, the decision as
  `CHANGED DECISIONS` — the document is already fixed and wins over the
  unit's text. A change that makes a unit pointless or needs a new one is a
  plan change: stop and ask.
- **Frames.** A change that alters what a screen shows goes to `ui-design`
  for the frame and to `screen-spec` for the spec, in that order.

## A finding against a settled decision

A review, an audit or a check may find something that a document already
decided on purpose — a limit the SRS rules out, a risk the architecture
accepted, a behaviour a decisions log fixed («предела по адресу нет»). Such
a finding is not a fix: fixing it silently reverses a decision the user
made. Every check that fixes on its own — `security-audit`, `doc-review`,
`code-review-unit`, `code-review-full`, `plan-review`, `docs-consistency` —
does this, whatever the finding's severity:

1. **Look before routing.** Search the SRS (NFR, BR), the architecture's
   decisions and accepted risks, and the project's decisions log for what
   the finding touches.
2. **When a decision covers it, ask — never fix by default.** One question
   with the decision quoted and its id, what the finding says, and two
   options: keep the decision (the finding becomes an accepted risk with
   that id as the reason) or change it (then this file, before any fix).
   Recommend from evidence — a concrete way to break the application that
   the decision did not consider — not from the finding's own advice.
3. **Nothing is fixed, planned or committed for it before the answer.**

## Where it applies

| Stage | The moment |
|---|---|
| `work` | the user's answer to `BLOCKED` or `STOP`, a change of mind mid-run, the final review's `STOP` |
| `code-review-full` | checks that every line of «Изменённые решения» landed in its documents, and that the code does not silently depart from a contract document |
| `ui-test-cases` run | a `❓ пробел в ТЗ`, or a defect the user rules is the spec's, not the app's |
| `screen-spec` | a Разрыв with owner `API` or `SRS` that the user settles |
| `ui-design` | the user changes behaviour while looking at the frames («убери поле», «другой порядок шагов») |
| `plan`, `plan-review` | a `STOP` on a documents gap: the decision goes into the document before the plan is written or revised |
| `repo-scaffold`, `deploy-topology`, `ci-pipeline` | a stack version, a port, a variable, a service name or a command that differs from the architecture |
| `grill-me`, `doc-review`, `docs-consistency` | an upstream contradiction the user rules on: the upstream document follows this file |
| between stages | «давай поменяем …» in the chat |

## Вопросы, адресованные этапу

At entry run `python3 <skills-root>/doc-versioning/scripts/open_questions.py <project> --for '<этап>'`
with the exact recipient from doc-versioning → Открытые вопросы. Pass the returned rows unchanged,
with their source paths, in the writer's `QUESTIONS TO SETTLE` packet — not to the user beforehand.
The writer first settles what the source documents and its own design judgment allow, recording each
outcome as a decision or an explicit assumption. An assumption is not a user-approved answer and
must not override a settled requirement. Only a choice reserved to the user returns BLOCKED:
one question in BLOCKER, with the other rows' decisions, assumptions or unresolved status preserved
in the report. Never disguise another user-only choice as an assumption just to avoid BLOCKED.

Ask a returned user-only question one per message, following [the question form](question-format.md):
a concrete example, options and a recommendation. Wait for that answer before the next question.
Never send the stage's questions as a numbered batch with «принимаю всё» or «только номера с поправками».
A stage without a writer follows the same order: settle what it can first, then ask the rest one by one.
A `Блокирует старт` that remains unresolved stops dependent work; it does not justify a batch interview.
Name every source row and its outcome in the report; an unanswered assumption is not a resolved row.

Reason: in a live architecture run, the stage asked all eight addressed questions before starting
the writer and offered «принимаю всё» or corrections by number. That bypassed the writer's judgment
and made individual answers ambiguous. Intake is a writer handoff, not a preliminary questionnaire.

At close change the class of each settled row in its original file to `Решено: <документ и раздел или коммит>`.
This is a changed decision without a version bump, included in the stage-close commit; keep the row for
history. Readdress unresolved rows to an explicit stage or name them in the report as unresolved; never
silently drop them. Do not collect them in a shared project file. Under a parent, changes to another
stage's question file are routed to that owner just like changes to its document; the owner records the
settlement before this stage closes. Intake never authorizes a second concurrent writer.
