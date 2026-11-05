# What to offer at a close

At every document-stage close (2–9), run `scripts/where_am_i.py <project>`.
Use «Готовность этапов», not the default successor in the chain table.
A stage is done only when its required documents are on the branch and a
stage-close commit exists. A stamped file or a registry state alone is not proof;
«написан, этап не закрыт» is unfinished. Inputs are the closed artifacts in
[team.md](team.md#what-a-stage-needs-on-the-branch).

- Offer all unfinished dependency-ready stages together. With selected stage
  chats the parent starts the selected ready chats; in one chat the user chooses
  their order. Several selected ready stages means all are started, not just the
  first row in the chain. Existing authorization still bounds which chats may open.
- An active neighbour is named, never offered again: «схема БД делается в чате
  «<название>»». A written but unclosed stage resumes with its owner.
- Name waiting stages and missing inputs: «ТЗ на экраны ждут контракт API».
  If there is nothing to start here, say where the missing input is being made,
  finish the turn, and offer only «ждать» or «остановиться». Do not start that
  neighbour's next stage or create a duplicate branch.
- The first unfinished backend stage means schema, then API, then architecture,
  then scaffold, skipping only explicitly inapplicable stages. Never offer API
  over an unclosed schema. No storage → no schema; no HTTP → no API; no screens
  → no design branch. Name each reason. Unknown applicability is not a skip.
- Persist explicit applicability in `documentation/.dev-pipeline.json` under
  `capabilities`: boolean `storage`, `http`, `screens`. Preserve its other keys;
  missing keys mean required/unknown. A recorded `design: "без макетов …"` skips
  frames only, preserving screen specs and cases. These are user/product facts,
  never guesses from a missing file.

## Close evidence

Existing canonical close subjects are still read. For a new close add the trailer
`Stage-Closed: <key> <version>` (keys: srs, db, api, arch, scaffold, design, specs,
cases), including an empty close when nothing changed. The required artifact must
exist in that commit and on HEAD. A later document change or dirty artifact needs
closure before it becomes an input. This is especially necessary for unversioned
frames registers, cases and project maps; their presence alone does not close a stage.

The parent receives one of these exact forms:

```text
ЭТАП <этап> ЗАКРЫТ · дальше: <этапы, которые можно начать>
ЭТАП <этап> ЗАКРЫТ · ждёт: <этап> после <этап>
```

The first names every ready stage; after the user's selection, start all selected
ones. The second starts nothing: retain the dependency until its owner closes it,
then recompute readiness. A message alone does not prove a Git close.

## Three design-branch examples

1. Mockups close while schema is running next door. Say «схема БД делается в чате
   «1.0.0 · 03 схема БД»; ТЗ на экраны ждут контракт API». Nothing is ready here;
   finish, wait or stop. Do not offer API, schema again, or a second backend branch.
2. Mockups close and backend has not started. Schema and API are both unfinished;
   offer schema, whose SRS input is closed. API still waits for schema. A schema
   file marked «написана, этап не закрыт» is resumed and closed, not bypassed.
3. API closes and mockups are closed. Offer architecture and screen specs together:
   each now has its inputs. With stage chats they can run in parallel; otherwise
   the user chooses the order. Mark the API wait released in the queue.
