# U27 release handoff — B/L cases

Status: NOT_RUN. These are future named-agent/host runs. The local-origin
unittests in `tests/test_handoff_acceptance.py` prove Git/state only. They do
not prove document correctness, Figma quality, live ownership, or a context reset.
No extra chats, real remote push, Figma edits, Docker builds or installs are
authorized by this file. Record source/case fingerprints and actual evidence
before changing a case status. Missing prerequisites remain NOT_RUN/BLOCKED.

| Case | Named agents / allowed tools after authorization | Expected observation | Actual / unmet prerequisite |
|---|---|---|---|
| B-H1 | srs-author, design-medium, figma-opus, screen-writer, docs-consistency-checker, impl-medium; repository reads/edits, local-origin Git; Figma only with separate permission | Participant A finishes documents through architecture and closes/pushes; designer clones and makes registered mockups; A writes screen specs; user clones for consistency/work. At every transfer inspect commit scope, full remote HEAD, portable reports and free ready-stage selection despite historical authors. Judge document/mockup quality separately. | NOT_RUN: named workflow and authorized Figma fixture unavailable. |
| B-H2 | Same named roles/tools as B-H1, independent technical/designer clones | After SRS, technical docs and mockups proceed in parallel. Combine independent sources with shared generated site; generated-only conflict rebuilds; genuine source conflict stops preserving work. Then A writes specs and user selects consistency/work. | NOT_RUN: complete named workflow not dispatched. |
| B-CONT | impl-medium, review-medium, review-full-plan; repository/state tools | Low fixes and whole-review fixes recover checked batches, full BASE/HEAD, findings/attempts and remaining gates; 21/21 units does not imply DONE. Unknown writer/check ownership blocks transfer; without permission/tools continue in the same chat. | NOT_RUN: agent continuation/ownership observation absent. |
| B-R01 | impl-medium (U8 work packet); repository/state tools | Agreed mandatory checks/proven regressions are finite. User excludes optional health-2. After checkpoint/compaction inspect the next unsent packet: excluded idea stays only in report; no extra circle. New proven blocking regressions follow convergence; mandatory gates remain. | NOT_RUN: post-compaction agent dispatch not observed. |
| B-R02 | impl-medium (U8/U16 packet); repository/state tools | User cancels narrowmutants. Before dispatch synchronize active state/checkpoint, resume, remaining gates and unsent packet. Use SKIPPED BY USER with reason/uncovered ranges; retain history/other runs. Continue other checks; cancelled mutation never restarts and no repeated confirmation occurs. | NOT_RUN: cancellation/continuation behavior not observed. |
| B-QUALITY | Roles named by existing A05–A34 behavior cases; only their authorized tools | Execute referenced cases for scanner completeness, client/data rules, scope, architecture, packet economy and changed frames. Static policy presence is distinct from compliance. | NOT_RUN: existing `tests/behavior_cases/*.md` are specifications, not execution logs. |

| Case | Live prerequisites | Expected evidence | Actual |
|---|---|---|---|
| L-STAGES | Explicit selected stage subset; available host chat tools and permission; known stopped writers/checks | Selected stages only after actual resume; no overlap; canonical titles; no historical author restriction. | NOT_RUN: no authorized live chat creation/handoff. |
| L-COMPACT | Naturally occurring native compaction during an authorized run, durable state before/after | Same logical work resumes with ranges/findings/gates. No forced clear or claim that checkpoint reset context. Simulated hook input is R evidence only. | NOT_RUN: native compaction not observed. |
| L-FIGMA | Authorized connected Figma test file, register/S/M IDs, changed and deleted frames | Preserve stable IDs; changed specs/cases match affected frames; deletion remains explicit open question. | NOT_RUN: no authorized Figma fixture/actions. |
| L-TRIVY | Docker/Trivy available, two explicitly selected release image names, permission to build/scan | Independent complete identity-linked reports for both images; missing/corrupt/partial output blocks success. | NOT_RUN: real two-image release scans not run. |

Execution record template: case, source HEAD and working-source hash, case hash,
environment, tools/permission, expected, actual, evidence path, status, owner U-ID.
Never promote a fixture, an older installed patch, or a quoted unit report to a
new B/L PASS. Preparation alone does not establish release READY.
