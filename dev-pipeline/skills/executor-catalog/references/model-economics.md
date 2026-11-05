# Codex model policy

This file describes the Codex build only. Claude model benchmarks and its
alias-separation policy do not establish quality or savings for Codex.
The authoritative settings are models.json in the plugin root:
role:<name> entries generate agents/<name>.toml; _stages configures chat
recommendations. Change the Codex build layer, not Claude agent frontmatter.

## Assignments and reasons

- GPT-6.1 Sol is the baseline for writing, design, review and complex tools.
- GPT-6 Luna low stays on code-explorer and mechanical-worker: extraction
  and fully settled edits, with explicit scope and verification.
- Sol low: doc-typist. Sol medium: simple implementations, low design/plan
  writers, structural reviews, UI case transcription, routine reports and
  Figma edits. Sol high: implementation with local decisions, complex UI,
  SRS, cross-document checks, screen specs, UI execution and diagnostics,
  medium design/plan writers, audit and substantive review.
- Sol xhigh: High design/plan writers, adversarial High reviews and
  impl-critical after difficulty escalation. No default max or ultra;
  the pipeline already owns its delegation and verification structure.

Low → Mid → High implementation keeps Sol: medium → high → high. Mid and
High differ in packet scope and verification; not every grade needs a new
model. Escalation to impl-critical increases effort to xhigh and carries the
previous report. A missing product decision is still a blocker for the user,
not a reason to spend more reasoning on inventing it.

The reviewer may use the same Sol model as the writer. Independence comes
from a fresh packet/context, adversarial checks, executable tests and scanner
evidence; neither another alias nor higher effort guarantees finding defects.

Stage chat settings are separate from role settings. Read _stages when
presenting the stage-chat list; use the explicit model-selection consent and
creation procedure in pipeline/references/parent-session.md. A role TOML
controls subagents, not the parent or stage chat. Running chats are not
silently reconfigured by updating this file.

## Evidence and limits

These are initial task-based settings, not measured winners. Supported effort
levels were checked against the local Codex model catalog and official docs.
Actual model access depends on the account. Never substitute a model silently.

Do not claim API prices describe ChatGPT subscription quota. Compare total
work per accepted result: first-pass acceptance, substantive defects missed,
rework, elapsed time and observed usage. High/xhigh can cost more time and
reasoning. Keep them only where representative tasks justify the extra work.
The typist also uses Sol: its only possible savings are lower reasoning effort
and narrower context, against an additional dispatch and rereading. Measure
that tradeoff before adding or removing nesting. Terra/Astra are candidates
for a separate controlled comparison, not automatic replacements in this policy.

## Paired strict-review effort experiment

This is a protocol for a future authorized experiment. Do not run this experiment as part of U25;
models.json and agents/*.toml remain unchanged, as do current role defaults and effort.

Predeclare baseline and candidate settings, fixed task/diff hashes, packet/rules/checks, rubric, sample size,
aggregation and stop conditions before collecting evidence. Use same-task/same-diff pairs with the same
baseline inputs in fresh independent contexts; randomize order and retain both reports. Only the declared
effort variable differs. Use at least 5 pairs per representative task class, including auth/security and
query/transaction risk, and report all pairs, failures and exclusions with reasons. Do not change the rubric
or remove difficult pairs after seeing results.

Score against an independently adjudicated finding set: material misses are omitted or wrongly dismissed
defects affecting correctness, security or the contract, with severity recorded; style preferences do not count.
Measure material miss rate (missed material findings / reference material findings) and returns/re-review
rate (reviews requiring correction / reviews), plus re-review rounds and first-pass acceptance. Record each
pair's elapsed time and known units through accepted completion, including returns and re-review costs;
do not count just the first cheap dispatch. Keep U13 telemetry's unknown/incomplete usage as null, never zero,
and state coverage, units and source. Known tokens are not subscription quota or money.

Reject the candidate immediately for any missed mandatory high-risk finding (for example authorization
bypass, secret exposure or unsafe transaction retry), even if cheaper. Stop on quality regression, retain
evidence and rollback to the baseline; do not silently change running chats. Other acceptance requires
nonworse material miss and return rates AND at least 10% reduction in comparable known units or elapsed time
over the predeclared paired sample. Report the selected aggregate, both cost/time metrics, sample size,
per-class results and uncertainty (paired dispersion/interval and missing-data coverage). Incomplete pairs
or null metrics cannot justify a change; collect complete evidence instead. A small sample or an interval
crossing the acceptance boundary is inconclusive, not statistical proof. Only an explicit subsequent policy
decision backed by complete quality and savings evidence may change defaults; monitor and rollback on a
later quality regression.
