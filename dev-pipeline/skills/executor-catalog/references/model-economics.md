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
