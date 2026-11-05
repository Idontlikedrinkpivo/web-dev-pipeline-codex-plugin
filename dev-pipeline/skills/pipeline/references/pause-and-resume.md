# Pause and resume

Read for a user-requested stop, actual ownership transfer, or recovery after
compaction. [checkpoint-state.md](checkpoint-state.md) owns schema and the
`checkpoint.py capture` / `restore` API; [context.md](context.md) owns automatic
same-chat continuation. A context threshold is not a requested pause.

## The note

Keep `documentation/plans/<version>/resume.md`, `work-run.md` and
`context-handover.md` in this checkout's plans folder. Record logical run/source
IDs, full HEAD, branch, plan hash, phase, exact next action, BASE/review range,
Low batches, open findings and failed attempts, decisions and remaining gates.
Physical host/thread/process IDs, log paths and active dispatches belong only in
checkout-local `runtime.json`. Delete resume.md only when the run really closes.

## Pausing

1. Stop the writers/checks for a real handoff and verify their actual status with
   available agent/process tools. Unknown ownership/status blocks transfer; a
   report alone does not prove children or shell jobs stopped. Name any service
   intentionally kept running in local runtime state.
2. Capture owned paths using `checkpoint.py capture` under the accepted schema.
   Keep source bytes, modes and index unchanged. A local-only pause has a complete
   local snapshot; legacy local patches remain local evidence only. Do not reset,
   add intent-to-add entries or clear somebody else's changes to make a pause.
3. A transferable pause needs the complete owned portable checkpoint payload,
   reports and manifest committed to the iteration branch, plus verified remote
   reachability of that exact commit. Workflow permission for this close/handoff
   may authorize commit + push via `push_branch.py`; a general request to code
   alone does not. No permission/tool/remote proof means local-only or explicitly
   incomplete transfer, never «готово и отправлено». Stage only iteration reports
   and explicitly owned checkpoint payload; foreign edits remain untouched.
4. HANDOVER requires explicit successor confirmation and stopped writers/checks.
   A real stop/handoff/new ownership starts the next reflect window; a continuing
   same-chat CHECKPOINT adds durable events without opening a new window.

## Picking up

Read the portable reports and `run-state.json` from this checkout; verify Git,
manifest identity, full captured HEAD, plan hash, completeness and payload hashes
before any dispatch. Export the Git-carried payload before explicitly selecting
its captured base if a later reports commit changed HEAD. Call `checkpoint.py
restore` only on its verified compatible target; dirty/divergent/partial state
is refused for inspection. Never automatically apply a legacy patch or assume
another machine has a local details file. Reconcile reality before proceeding.
Continue the saved phase: 100% unit commits still leave final checks, full review
and fix/re-review rounds. Do not redispatch work whose ownership is unknown.

The recipient may select any dependency-ready stage, regardless of who wrote its
inputs. Main/merge/tag/release need their own authorization. Source rebase
conflicts stop; generated-only conflicts use the accepted push recovery path.
