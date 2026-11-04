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
python3 <skills-root>/reflect/scripts/context_size.py <project-dir> --json
```

It uses CODEX_THREAD_ID; if unavailable, pass the host-provided full ID with
--thread-id. Never infer an ID by matching titles. Without an ID the reader
accepts only one unambiguous main chat, never the latest neighbouring chat.
Default threshold: min(300,000 tokens, 70% of the recorded model window), with
300,000 only when window telemetry is absent; --limit allows an explicit policy.
Exit 0: continue. Exit 2 (CHECKPOINT): use the procedure below. Exit 3 (UNKNOWN):
context has not been measured; save progress, resolve the ID/telemetry and do not
report a reset or treat it as zero. If unresolved, explain the limitation once
and offer the manual checkpoint below; do not keep dispatching indefinitely.
A checkpoint request never cancels an in-flight item or bypasses its review.

## Save at a safe boundary

1. Finish the item, required checks, review and commit. Wait for every dispatched
   agent and shell job to stop. With parallel units, finish the entire active
   wave; no work may still be writing to this checkout. Blocked work follows its
   own stop rule, not this handover. Never mark the stage complete merely to reset.
2. Refresh the progress file, run report and documentation/plans/<version>/resume.md
   (pause-and-resume.md). Record the exact next item, HEAD, branch, plan path and
   hash, BASE/review range, completed units, pending reviews, decisions and any
   live services. Preserve existing user edits; don't stash/reset or reapply a
   patch to an unchanged shared checkout. Run the stage's handover-check.
3. Record a short context-handover.md beside resume.md: source thread/host IDs,
   CHECKPOINT status, checkpoint paths, HEAD, next item, successor ID if known,
   and the user's explicit continuation-chat permission, if given. Store no
   fabricated permission. This is a handover, not an iteration/stage close.

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
wait for the user; never run two coordinators against the same checkout.

Use create_thread (never fork_thread), the same verified project, host, local
checkout and branch, no new worktree. Discover list_projects and tool schemas;
if the tool cannot target that checkout, stop instead of resuming elsewhere.
Pass only paths, stage/iteration, source ID and the next-item checkpoint, not
history or a transcript. Keep model defaults unless specific overrides were
explicitly chosen by the user. Record the returned real thread ID, or clientThreadId while setup is queued;
wait for setup before treating it as runnable. On timeout keep that pending ID
and inspect it before retrying; never create a second successor. Emit the host's created-thread directive. The parent updates this
stage's sessions.md ID (not a new stage/part row), retains the old ID in
context-handover.md, inserts the successor at the stage's sidebar position and
tracks that successor. Do not archive the old chat without a separate request.

The successor reads AGENTS.md, the active SKILL.md, codex-runtime.md, resume.md,
context-handover.md and the progress/report paths. It verifies branch, HEAD, plan
hash and Plan-Unit commits against the live checkout. Drift is reconciled before
any dispatch. It runs work's plan_state/readiness gates, skips committed units
and resumes the exact next item with fresh named agents. It does not replay
completed work or replan. Mark the handover resumed only after verification.

## Manual fallback

Without permission, chat tools or a working successor: keep the saved checkpoint,
say «Контрольная точка сохранена после <item>. Выполните /compact в этом чате,
затем напишите “продолжи с <next item>”». End the turn before the next dispatch.
This is a pause requiring the user, not automatic context refresh. After the
user's compaction and continuation, reload the same files and readiness gates.
Never claim the history was cleared merely because state was saved or a message
was sent. Host automatic compaction can happen earlier; reload the skill and
on-disk state then too, without replaying already committed units.
