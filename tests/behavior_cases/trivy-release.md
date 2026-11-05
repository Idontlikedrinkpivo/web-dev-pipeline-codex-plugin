# U17 — Trivy release evidence

This case is a procedure, not proof of execution.

## R — fixture validator

Run `python3.12 -m unittest discover -s tests -p test_trivy_reports.py -v`.
Two expected images and one report must fail as incomplete. Missing, empty,
corrupt, truncated, duplicate, unexpected, wrong-image and failed-scan evidence
must fail. Independent matching reports, including `Results: []`, succeed only
for complete successful records. Digest mismatch fails. Scanner nonzero exit
codes remain nonzero. The expected-set property enumerates subsets and statuses.

## L — actual Docker and Trivy

Prerequisites: running Docker, Trivy, two independently built local release
images, and required scanner database access/cache. Record Docker and Trivy
versions. If unavailable, record `NOT_RUN` with the missing prerequisite.
Do not install tools or download images just to turn this check green.

1. Record two exact build image refs and their local IDs. Create a fresh output
   directory and use the per-image command in `scanners.md` once per image.
2. Save separate JSON reports, commands and immediate exit statuses. Write the
   manifest with both expected refs, both record paths and IDs when available.
3. Run the validator and retain output/status. Inspect that `ArtifactName` and
   `ArtifactID` match the corresponding built image. Apply existing severity
   policy to findings independently of completeness.
4. Remove one record: validation must fail as incomplete. Restore it and replace
   one report with the other's content: validation must fail identity matching.

Acceptance record: R output/log; L versions, image refs/IDs, exact commands,
reports and statuses, or explicit `NOT_RUN`. Passing R does not execute L.
