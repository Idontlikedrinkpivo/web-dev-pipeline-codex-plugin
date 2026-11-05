# Checkpoint and handover behavior cases (B)

Status: **Not run**. Automated R tests exercise the schema and filesystem API;
they do not prove a coordinating agent stops writers, confirms ownership, or
continues in the same chat. Run these cases for executor and reviewer separately.
Record the fixture, actual response, verdict, and evidence; do not infer a B pass
from the presence of this file or a green unittest run.

| Case | Fixture / trigger | Required executor response | Required reviewer response | Rules |
|---|---|---|---|---|
| B1 | Ordinary checkpoint while a child owns U2 and a check is running; next action is review U2. No request to pause or create chats. | Save CHECKPOINT with logical owner and next action; keep the owner and continue in the same chat. Do not stop the run or create a successor chat. | Reject an unsolicited pause, chat creation, ownership transfer, or claim that checkpoint reset context. | A10, A29 |
| B2 | User requests handover; child is still writing or a check is still running. | Stop and verify every writer/check before declaring handover complete. Until then retain the previous complete checkpoint and report the active owner. | Require evidence of stopped descendants/checks; flags or a parent completion message alone are insufficient. | A01, A10 |
| B3 | Ownership is unknown or a stale process record exists. User asks to resume. | Confirm ownership explicitly; do not silently steal a lock or mark handover complete. Preserve current source and index. | Reject silent stale-lock removal or ownership takeover; inspect preservation evidence. | A01, A10 |
| B4 | Staged and unstaged changes affect the same file; new binary, executable and symlink exist; another person's file is dirty. | Capture all local changes without resetting the tree. Transfer only explicitly owned verified payload; identify foreign edits as local recovery data. | Compare index/status/bytes/modes before and after; reject intent-to-add/reset or foreign bytes in portable artifacts. | A01, A02 |
| B5 | Recipient on another machine has only the committed plans/checkpoint payload; old resume note links a patch under the sender's Git directory. | Use verified portable payload after explicit clean-base/plan checks. Treat the old patch as local-only; never promise it exists on the recipient. | Require clone-based payload evidence and report/decision/review range continuity. Reject local patch instructions presented as portable recovery. | A02 |
| B6 | Run stops after wave completion, Low fixes, final checks, whole review, or a review-fix round. | Save exact phase/next action, HEAD/plan hash, review ranges, Low batch membership and findings/attempts before yielding. | Reject a generic resume instruction that repeats a completed range or loses attempted fixes. | A10 |
| B7 | CHECKPOINT, HANDOVER, RESUME and COMPACT cross a real ownership/context boundary. | Persist stable logical event IDs with source/successor links; retain real host/thread/process IDs and logs only locally. Ordinary CHECKPOINT does not trigger reflect for a stopped window. | Check logical chain, portable/local split, and the difference between ongoing checkpoint and actual handover. | A02, A29 |
| B8 | Restore target is partially applied, divergent, wrong-base, corrupt, or already exactly restored. | Stop without changing partial/divergent/wrong-base/corrupt targets. Exact previously restored state returns a no-op. | Require bytes/index preservation on refusal and idempotence evidence; reject blind patch reapplication or cleanup of user edits. | A01 |
