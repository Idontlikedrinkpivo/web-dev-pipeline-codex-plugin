# Plan economy behavior cases (B)

Status: **NOT_RUN**. These are agent behavior fixtures, separate from the R
mechanical tests in `tests/test_plan_economy.py`. File presence and passing R
tests do not establish planner/reviewer compliance.

Run the planner and reviewer separately with the same inputs. Record the exact
source revision, prompt, input paths, actual response, unit/grade table, verdict
and evidence before changing this status. No agent run is claimed here.

| Case | Fixture / trigger | Required planner response | Required reviewer response |
|---|---|---|---|
| B1 | Supply all A01–A34 rows from `documentation/plans/1.3.0/audit-scope.md`, the relevant existing code/design, inventory and executor grading rules. Include settled transcription, related small local changes and risky state/concurrency changes. | Cover all 34 findings. Use 0/Low for fully determined typing/pattern work, combine related tiny changes where one green commit fits, and use High for risky state with open decisions or concurrency under the cascade. Record dependencies and bounded mandatory input; no blanket escalation or exact spend claims. | Verify complete coverage and per-unit cascade evidence, including risk and compound gates. Accept economical Low batches and justified serial overlap; identify unsafe parallel dependencies/resources. Treat byte/micro advice as leads, not automatic blockers; require concrete rework evidence for P1. |
| B2 | Two small changes share one goal/pattern. One version is needlessly split; another has a cited independent green delivery boundary. Add two independent small fixes with different goals. | Merge the needless split or explain a sound separate-green boundary in `Отдельный коммит`; retain independently useful fixes when appropriate. | Judge the boundary and objective; do not reject every small unit or serial shared path. |
| B3 | A mandatory input file exceeds the measured byte trigger; another named file is planned but absent. Supply the smaller executor/reviewer window if available, and otherwise mark it unavailable. | Measure existing input, record unknown future size, account for skill input, implementation, testing, rework and shared dependencies. Bound sections first, split only at green boundaries with headroom. | Review the measurement and actual smaller window when available; preserve uncertainty otherwise. Do not convert bytes into fabricated exact tokens, cost or savings, and do not raise the grade solely for input volume. |
