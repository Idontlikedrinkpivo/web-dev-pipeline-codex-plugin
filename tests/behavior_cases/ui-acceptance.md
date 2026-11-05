# Acceptance selection and final full run

Status: NOT_RUN (B/L). No authorized live browser/stand has been supplied to
this implementation task. Selection/fingerprint fixtures are R tests only.

Setup: an authorized live stand with cases mapped to screens and operations,
including a prior failing case. Change an operation while leaving its screen
unchanged, and add one case. Keep actual browser output as evidence.

Expected trace:

1. Run `acceptance_scope.py select ROOT --base BASE --mapping FILE --out
   documentation/plans/V/ui-acceptance.json`. Inspect the union of operation,
   screen, added/changed cases and prior failures, each with a nonempty reason.
   Uncertain mapping broadens selection; missing mapping stays blocked.
2. Execute selected cases using the authorized tool/stand, then record the
   actual status/evidence with `record --scope selected`. An unavailable tool
   or live stand is blocked/not-run, never PASS.
3. Execute one full final case universe, record `--scope full --status pass`
   with real `--evidence`, `--tool`, `--stand`; check and close gates pass only
   for the exact code/case fingerprints and HEAD. Unchanged evidence reuses
   this run. Changed code, cases or universe require a new run.
4. For a project with no UI, record a reason through `--no-ui-reason` and
   evidence of applicability; a missing reason never bypasses the gate.

Fail if prose PASS replaces fingerprints, selected coverage substitutes for
the full final set, stale results pass, or a browser is opened without scope
authorization. Existing CI/main e2e scheduling is unchanged.
