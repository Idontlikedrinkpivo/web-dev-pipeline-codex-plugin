# Portable run state and local runtime

Read by `work` at Step 1, and again after every compaction: what the run keeps besides its commits, where each
lives, and when each is written. Where the run stands is still read from git (`plan_state.py`); these hold what
git cannot — who is dispatched now, what was decided, and what the user sees.

**The portable run report** is `documentation/plans/<version>/work-run.md`,
with a separate run section and full BASE per run. Follow
[checkpoint-state.md](../../pipeline/references/checkpoint-state.md): phases are
`unit`, `wave`, `low-fix`, `final-checks`, `whole-review`, `review-fix`.
Save full HEAD, plan hash, BASE/review ranges, checked Low batches/findings,
decisions, acceptance/code hashes, remaining gates and exact next action at every
boundary and fix/re-review round. Unit completion never closes pending gates.

**Local runtime** holds physical dispatch/task/host IDs, logs and ownership in
the checkout-local Git directory from `state_paths.resolve_paths`. A dispatch is
recorded before its Agent call and removed after verified completion. After
compaction inspect actual task state before redispatch; unknown is not finished.
Legacy common-dir run reports may be read locally; export verified portable
content before transfer. Missing local files on the recipient are not success.

**The resume note.** On start read `documentation/plans/<version>/resume.md`
when a run left one (`pipeline` → `references/pause-and-resume.md` → Picking
up). Refresh it after every commit and every stop, and delete it when the run
closes (Step 7): a note left behind sends the next session after a run that
is over.

**The task list** has one task per unit in scope, named from the unit's goal
with the U-id appended (`Add order aggregate (U3)`). Do not edit the plan
document — progress lives in commits, the task list, and the progress file.

**The progress file and its line.** Create — on a resumed run, rebuild from
git — `documentation/plans/<version>/progress.md` per
`references/progress-file.md`; no unit's commit carries it — `push_branch.py` commits it at the run's stops and close (`pipeline` →
`references/service-version.md` → The iteration's files in git). The chat gets it only as **the progress line**: with the file's
count set from `plan_state.py`, run

```bash
python3 "<folder of this SKILL.md>/../pipeline/scripts/progress_link.py" documentation/plans/<version>/progress.md
```

(add `--desktop` when this session has the built-in browser) and paste the
one line it prints, as printed — never a link written by hand. Post it before
the first dispatch, and again after a resume or a compaction before the next
one: a run started without it is invisible until its first commit. Post it
after every Step 5 commit, every stop and every fix of the final review, and
as the run's last message, so a user who closed the page or stepped away
reopens it from the last message.
