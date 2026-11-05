# Checkpoint state — schema 1

`scripts/checkpoint.py` owns capture/restore and the versioned manifest. Workflow
consumers supply the state; this module does not pause agents, create chats, run
reflect, commit, push, reset, clean or silently transfer ownership.

## Public API and CLI

```python
capture(checkout, version, chat_key, state, owned_paths, *,
        event='CHECKPOINT', successor_id=None, ownership_confirmed=False,
        writers_stopped=False, checks_stopped=False, runtime=None,
        local_only=False) -> dict

restore(checkout, version, chat_key, checkpoint_id, *, source=None) -> dict
```

`CheckpointError.code` is the stable failure discriminator. `restore` returns
`{status: 'restored' | 'already-restored', checkpoint_id: ID}`. `source=None`
means recovery from this checkout/chat's local snapshot. An explicit `source`
directory means a verified checkpoint; it may be exported from Git on another
machine. A local snapshot additionally requires its exact checkout/gitdir/chat/
host identity. A legacy `.patch` is local-only, never a portable checkpoint.

```bash
python3.12 checkpoint.py capture --checkout ROOT --version 1.3.0 \
  --chat-key PHYSICAL_CHAT --state state.json --owned src/a.py --owned tests/a.py
python3.12 checkpoint.py restore --checkout ROOT --version 1.3.0 \
  --chat-key PHYSICAL_CHAT --checkpoint-id ID --source EXPORTED_CHECKPOINT
```

Capture also accepts `--runtime FILE`, `--event`, `--successor-id`, `--local-only`,
`--ownership-confirmed`, `--writers-stopped`, and `--checks-stopped`. Successful
stdout is JSON. Expected failures return nonzero with `{error: CODE, message}`.
Argument syntax errors use argparse's stderr and exit 2.

`local_only=True` (`capture --local-only`) is internal Git recovery, not logical
handover or publication. It publishes only an immutable checkpoint at
`paths.local/checkpoints/ID`, with `completeness: {local: true, portable: false,
scope: 'local'}`. It captures the full local Git-visible dirty inventory without
changing the source index, and never creates or updates portable checkpoints,
`run-state.json`, report aliases or portable event history. The default remains
the local plus explicitly owned portable capture described below.

## Portable input and manifest

`state` has exactly these fields. Unknown fields fail closed rather than leaking
unclassified physical metadata into portable state.

| Field | Meaning |
|---|---|
| `run_id`, `source_id`, `unit` | Stable logical identifiers, never a real host/thread/process ID. |
| `phase` | `unit`, `wave`, `low-fix`, `final-checks`, `whole-review`, or `review-fix`. |
| `next_action` | Exact next action, including unfinished checks/review/fix rounds. |
| `review` | `{base: FULL_SHA, head: FULL_SHA}` for the review range. |
| `low_batches` | Already reviewed Low batches, unit membership, base/head ranges and findings. |
| `findings` | Open/closed findings and previous fix attempts/results. |
| `decisions` | Decisions made during this run and their document owners. |
| `reports` | UTF-8 text for `work-run.md`, `resume.md`, and `context-handover.md`. |

Capture adds `schema_version: 1`, unique `checkpoint_id`, `version`, full `head`,
`branch`, SHA-256 of this checkout's `plan.md` (`plan_sha256`), `paused`, `events`,
`completeness`, `inventory`, and `payload`. Input collections are copied.

`events` is the run's stable event history. Each record has unique `event_id`,
`type` (`CHECKPOINT`, `HANDOVER`, `RESUME`, `COMPACT`), `source_id`, and nullable
`successor_id`. CHECKPOINT keeps the logical source, null successor, unchanged
next action, and `paused: false`; it can occur while its owned child/check runs.
HANDOVER requires a successor, explicit ownership confirmation, all writers and
checks stopped, and runtime owner status `known`. Runtime writer/check records
must each say `status: stopped`; unknown/stale ownership is never reclaimed.
HANDOVER records `paused: true`. Callers verify those claims against real tasks;
booleans alone do not stop or inspect a process. RESUME/COMPACT record links;
they do not create successor chats themselves.

## Checkout-owned storage

All roots come from `state_paths.resolve_paths`; there is no common-dir fallback.

| Portable, committed with plans | Local, under this checkout's own Git directory |
|---|---|
| `documentation/plans/V/checkpoints/ID/manifest.json` | `pipeline-work/V/CHAT_HASH/checkpoints/ID/manifest.json` |
| Separate `staged.patch`, `unstaged.patch` and `blobs/SHA256` | Complete local versions of the same payload, including foreign edits |
| `run-state.json` — current manifest publication pointer | `runtime.json` — supplied runtime metadata and physical identity |
| `work-run.md`, `resume.md`, `context-handover.md` | `restore-in-progress.json` if restore is interrupted |

The portable manifest and `run-state.json` are identical. Portable
`completeness` is `{local: true, portable: true, scope: 'owned'}`: every locally
observed change was captured locally, and the explicitly owned scope was saved
portably. This does **not** claim foreign changes were handed over. Local scope
is `local` and includes `local_identity`; never publish it as portable recovery.
Host/thread/process IDs and log paths belong only in `runtime`, not state or
report text. Callers remain responsible for keeping report prose portable.

`owned_paths` lists exact checkout-relative files, including intended deletions;
directories and overlapping file/directory replacements are unsupported. The
portable payload contains only these paths. The local snapshot includes all
Git-visible dirty paths plus owned paths. Untracked inventory follows Git's
exclude rules, so ignored build output/dependencies are not recovery input.
Managed checkpoint/report outputs are excluded to avoid recursive capture.

Every inventory record has `path`, `worktree`, and nullable `index`. Worktree is
`{kind: file|symlink|missing, mode: POSIX_MODE, blob?: 'blobs/SHA256'}`. Index is
`{mode: GIT_MODE, oid: FULL_OBJECT_ID, blob: 'blobs/SHA256'}`. Raw bytes preserve
text, binary, newline-containing paths, executable modes and symlink targets;
index blobs preserve the staged/unstaged boundary. `payload` maps every payload
relative filename to its SHA-256, including both full-index binary delta files.
Restore uses verified blobs/index entries rather than trusting patch application
onto an unknown worktree. Capture never adds intent-to-add entries or resets.

## Publication, validation and refusal

Capture takes exclusive checkout-wide, chat-local and Git index locks; existing
locks are never removed as stale. It reads the source inventory/index/HEAD/plan,
writes both staged payloads, and compares the entire observation again. Drift or
unsupported state cannot publish a complete checkpoint. Unmerged indices,
submodules, intent-to-add, skip-worktree and assume-unchanged flags are rejected.
Source bytes, modes and index remain unchanged. Lock/runtime writes are local.

Payloads and manifests are fsynced, published from same-filesystem `.pending-ID`
directories by rename, then reports are replaced atomically. `run-state.json`
switches last. It is the authoritative publication pointer; an interrupted
publication can leave an unreferenced checkpoint or a newer report alias, but
the previous current manifest remains complete. Reports are also present in
each immutable manifest so the old pointer remains self-contained. Pending
directories cannot be restored as complete. Publication does not commit or push;
callers must include the complete owned checkpoint directory and reports in Git.

Restore validates schema, identity, completeness, safe inventory/payload paths,
all hashes and index object bytes **before** touching target source/index. It
requires exact captured HEAD and plan hash. Export Git-carried payload before
switching explicitly to the captured base when a later artifact commit changed
HEAD. An exact already-restored index/worktree with no unrelated dirt is a no-op.
Partial, divergent or unrelated dirty targets are refused without changes.

Restore prepares an isolated index, checks target inventory again, records its
local journal, replaces each file only while its original observed value still
matches, and atomically installs the prepared index last. It never clears user
edits or rolls back blindly. An OS failure/concurrent writer during the write
window stops with the partial state and journal intact for explicit inspection;
subsequent ordinary restore refuses that partial state. Git locks serialize Git
writers; callers must also stop non-Git writers before restoration/handover.

Stable errors: `invalid-state`, `invalid-scope`, `invalid-checkpoint-id`,
`unsafe-handover`, `locked`, `unsupported-state`, `concurrent-drift`,
`capture-incomplete`, `corrupt-payload`, `incomplete-checkpoint`, `wrong-base`,
`wrong-plan`, `dirty-target`, `legacy-local-only`, `unsupported-schema`,
`restore-incomplete`. Unknown schemas fail closed.

U2 provides schema/API and R tests. Later consumers wire all unit/wave/Low-fix/
final-check/review/fix boundaries. Agent compliance is separately specified in
`tests/behavior_cases/checkpoint.md`; file presence or green R tests is not B
acceptance.

## Reflect windows — schema 1

Checkpoint events are durable recovery history, not automatic reflect part
boundaries. A continuing CHECKPOINT or COMPACT alone never completes a reflect
part. A real stop, handoff or transfer of ownership supplies the boundary.

`reflect/scripts/sessions.py window ROOT --version V --until OFFSET_AWARE_ISO
--boundary stop|handoff|ownership` reads the next exact half-open UTC interval
`[start,end)` without publishing a report. Without a real boundary it returns
`partial`; missing journals return `unavailable`, never a complete empty run.
The stable opening is `plans/V/iteration.json:started_at`, otherwise an observed
iteration commit (provenance included); folder modification time is never used.

Publish the returned JSON in a fenced `reflect-window` block in
`CODEX_HOME/dev-pipeline-feedback/PROJECT.md`. It contains `schema_version: 1`,
`project`, `version`, `window: {start,end}`, `start_source`, `source_hash`,
`event_cursor: {count,last}`, `boundary`, `completion`, and diagnostics. Source
hashes describe the observed source window; event cursors retain source/index
provenance across checkpoint, resume and compaction records. A checkpoint ID
does not claim complete journal coverage. Physical source identities stay in
local feedback, never in portable checkpoint state.

Only contiguous complete records of the same project/version advance the
cursor, in publication order. The next start equals the previous complete end.
Partial, corrupt, gapped, overlapping or out-of-order sections do not advance
it. Minute-only legacy prose needs migration: exact seconds are unknown.
`close_iteration.py` uses this same parser and requires coverage strictly past
the final commit instant (the end itself is exclusive), using Codex feedback
only. It does not use a ten-minute allowance or Claude feedback.
