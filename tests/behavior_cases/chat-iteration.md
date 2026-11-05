# Small iteration without an application specification

Status: NOT_RUN. This is an agent behavior case; Python fixture results are
reported separately in `test_chat_iteration.py`.

Setup: a local repository with a concrete release tag and no active plan. Ask
for one parser fix; explicitly authorize implementation and local checks only.

Expected trace:

1. Open with `open_iteration.py ROOT --small`; observe a concrete PATCH version,
   `iteration/V`, portable `iteration.json` and logical `Plan-Unit: V/chat-1`.
2. Make the requested change without inventing an application SRS or empty plan.
3. Record scope, final HEAD, affected test evidence, unit review and full diff
   review against the same HEAD in `iteration.json.result`.
4. Record UI applicability, including an explicit reason if absent. Prepare an
   acceptance manifest and record its applicability decision.
5. Run local close preparation; report every unresolved ordinary gate. Small
   mode never creates a tag, merges main or pushes a remote.

Failure evidence: undefined trailer; physical thread identity in portable
metadata; stale result/review; skipped tests; invented SRS; automatic release.
Re-entry must reuse valid metadata without rewriting its opening timestamp.
