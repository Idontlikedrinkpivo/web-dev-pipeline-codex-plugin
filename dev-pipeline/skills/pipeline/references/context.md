# Context checkpoints in Codex

Read at the start of long stages and after compaction. This is the Codex
contract; do not apply Claude's clear_session instructions. The available Codex
chat tools do not clear or compact a running chat. Never send `/compact` through
send_message_to_thread or execute it in a shell: that is text, not a host command.
A user can invoke `/compact` in the app. A fresh create_thread prompt starts with
fresh history; fork_thread and resuming the old chat retain history.

## Keep input small

Use named agents with fresh packets, short reports (~2,000 characters) and detail
files. Run checks through work/scripts/run_check.py. Send long searches, diffs
and scanner output to files and read needed sections. Keep the parent's reports
short; it does not need the stage's transcript.

## Measure this chat

After each safe item boundary (a committed plan unit, a finished screen, a
completed audit area), before dispatching the next item, run:

```bash
python3 <skills-root>/reflect/scripts/context_size.py <project-dir> --next Mid --json
```

It uses CODEX_THREAD_ID; if unavailable, pass the host-provided full ID with
--thread-id. Never infer an ID by matching titles. Without an ID the reader
accepts only one unambiguous main chat, never the latest neighbouring chat.
Default threshold: min(300,000 tokens, 70% of the recorded model window), with
300,000 only when window telemetry is absent; --limit replaces only that baseline.
`--next 0|Low|Mid|High` estimates a policy reserve of 10k/25k/50k/75k tokens,
capped at 20% of a known window. `--reserve <positive tokens>` overrides it;
impossible capacity is rejected. These are estimates, not measured task costs.
CHECKPOINT means current >= baseline or current + reserve >= known window.
JSON includes baseline, reserve, decision and reason; argparse errors are not
valid CHECKPOINT measurements. Exact CODEX_THREAD_ID/--thread-id is required.
Exit 0: continue. Exit 2 (CHECKPOINT): use the procedure below. Exit 3 (UNKNOWN):
context has not been measured; save progress, attempt to resolve the ID/telemetry
once and do not report a reset or treat it as zero. If still unknown, mention
the limitation once and use automatic same-chat continuation below. UNKNOWN and
CHECKPOINT alone are not reasons to stop the run or request a user message.
A checkpoint request never cancels an in-flight item or bypasses its review.

## Save at a safe boundary

1. Follow [checkpoint-state.md](checkpoint-state.md): use `checkpoint.py capture`
   with the accepted state schema at unit, wave, Low-fix, final-checks,
   whole-review and review-fix boundaries. A same-chat CHECKPOINT preserves the
   logical source and next action with `paused: false`; it does not require a
   transfer, a reflect window or stopping owned active work.
2. Save portable `work-run.md`, `resume.md`, `context-handover.md`, full HEAD,
   plan hash, BASE/review ranges, Low batches/findings, remaining gates and exact
   next action. Physical host/thread/process IDs and dispatch/log paths stay in
   checkout-local runtime state, never portable reports. Preserve staged and
   unstaged work using verified payload; never reset or auto-apply a legacy patch.
3. Only a real HANDOVER needs confirmed successor ownership and stopped writers
   and checks. Inspect actual available agent/process tools; unknown status is
   not permission to transfer. Publication alone proves neither commit nor push;
   transferable handoff follows [pause-and-resume.md](pause-and-resume.md).

The last implementation commit is also a boundary, not the end of work. For
21/21 committed units, save the next action as the remaining final checks,
whole-run review, fix/re-review rounds and run report, in the skill's order;
never invent U22 or mark the stage DONE while its final gates are pending.
Run handover-check only when actually transferring ownership to another chat;
a same-chat checkpoint only saves state and continues, without a new digest
or handover agent on every unit above the threshold.

## Continue with fresh history

Use this path only when the human explicitly requested new continuation chats
for this run, and the host accepts that authorization. Agreement to the original
stage list or «продолжай план» alone is not permission to open extra chats.
Ask for this optional choice when establishing the stage list (parent-session.md),
not after silently assuming it. Respect tool refusals; do not use another API,
raw app database, child CLI or config edits to bypass them.

With a parent, the old stage returns HANDOVER_READY with the checkpoint and ends
its turn. The parent verifies its turn ended, agents/jobs stopped and saved files
match Git, then creates one continuation chat for this stage. Without a parent,
the old chat may create its explicitly requested successor with a waiting prompt
and then end its own turn. The successor must wait_threads/read_thread the old
ID until its turn has completed before any mutation. If status is unavailable,
do not start the successor. Reconcile its state before any fallback; never run
two coordinators against the same checkout. A real overlap/ownership problem
may block work; the context threshold alone may not.

Use create_thread (never fork_thread), the same verified project, host, local
checkout and branch, no new worktree. Discover list_projects and tool schemas;
if the tool cannot target that checkout, do not create a chat elsewhere; use
same-chat continuation instead, provided no successor is already running.
Pass only paths, stage/iteration, logical source_id and the next-item checkpoint, not
history or a transcript. Keep model defaults unless specific overrides were
explicitly chosen by the user. Record the returned real thread ID, or clientThreadId while setup is queued;
wait for setup before treating it as runnable. On timeout keep that pending ID
and inspect it before retrying; never create a second successor. Emit the host's created-thread directive. The parent updates this
stage's sessions.md ID (not a new stage/part row), retains physical old/new IDs in checkout-local runtime metadata, inserts the successor at the stage's sidebar position and
tracks that successor. Do not archive the old chat without a separate request.

The successor reads AGENTS.md, the active SKILL.md, codex-runtime.md, resume.md,
context-handover.md and the progress/report paths. It verifies branch, HEAD, plan
hash and Plan-Unit commits against the live checkout. Drift is reconciled before
any dispatch. It runs work's plan_state/readiness gates, skips committed units
and resumes the exact next item with fresh named agents. It does not replay
completed work or replan. Mark the handover resumed only after verification.

## Automatic same-chat continuation (default fallback)

When new continuation chats were not explicitly requested, chat tools are absent,
or creation fails before a successor exists, continue this run automatically
in the current chat. No extra authorization is needed to finish the already
requested plan. The threshold is a checkpoint trigger, not a hard stop.

1. Save the checkpoint at the safe boundary. Mark native-compaction-pending;
   this records saved state, not proof of a refreshed context. If a successor
   already exists or setup is pending, resolve who owns the run before proceeding.
2. Keep the coordinator lean and dispatch the exact next action now, in this
   turn: fresh named executors/reviewers, file paths and short packets. Do not
   replay history, reread the whole plan, wait idle for compaction, end with
   «выполните /compact» or ask «напишите продолжай». If all units are committed,
   proceed to final checks and whole-run review; 21/21 does not skip those gates.
3. Let Codex perform its native automatic compaction at its own threshold. The
   plugin cannot choose its exact timing. Do not claim that saving the checkpoint
   or dispatching a fresh subagent cleared the coordinator's history.
4. After host compaction reload the active skill, codex-runtime.md, checkpoint,
   resume/progress/report and live Git/readiness gates, then continue the saved
   next action. Until then update the existing checkpoint after completed items;
   do not repeatedly stop, ask permission or create a handover on every high reading.

Manual /compact is optional if the user requests it. Pause only for a real
blocker under the active skill (missing decision, failed permissions, host
context-exhaustion error, uncertain ownership), or a user-requested stop.
A host context error must be reported honestly with the saved checkpoint;
it is not proof that compaction happened. Never simulate a host command by
sending `/compact` as a chat message or running a separate CLI on the live chat.
