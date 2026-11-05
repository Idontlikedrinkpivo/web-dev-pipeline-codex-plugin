# Packet policy behavior cases

These are manual future-run cases, not evidence of an executed experiment. Structural tests check the
written routing and experiment contract only. Both cases below are NOT_RUN in U25.

| Case | Setup | Expected observation | Status |
|---|---|---|---|
| B1 | Dispatch a unit touching only `useSearch.ts`, with no screen/component source or auth goal. | Packet selects TypeScript and React core machine/reviewer rules and dependencies; it omits unrelated frontend screen/profile and web-design packs. Short skills can be read whole. Reviewer retains all applicable anchors. | NOT_RUN — requires a real dispatch and observed reading trace. |
| B2 | Provide paired reviews of the same auth diff with an independently confirmed authorization bypass. Candidate uses fewer known units but misses the mandatory high-risk finding. | Reject candidate immediately, preserve evidence and rollback to baseline; savings cannot override a security miss. Unknown U13 usage remains null and cannot justify an effort change. | NOT_RUN — requires a separately authorized paired experiment; no model or effort change in U25. |
