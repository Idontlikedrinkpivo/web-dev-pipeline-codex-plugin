---
name: continue
description: >-
  User command: says where the project stopped, from its files, and asks the next step. In chat, «где я» is pipeline.
disable-model-invocation: true
---

> **Codex runtime.** Before using this skill, read `../executor-catalog/references/codex-runtime.md`. It defines tool mappings, named-agent dispatch and stage-chat orchestration; use it for inherited Claude Code terms below.

# Continue the project

A new session remembers nothing of the last one; the project's files do. This command reads them and puts the user
back at the right stage.

1. Run `python3 "<folder of this SKILL.md>/../pipeline/scripts/where_am_i.py" <checkout or project folder>`.
   Use the printed project directory for every document, question and subsequent stage. If several projects or
   iterations match, ask which one. On pickup from another branch with a clean tree, switch to the existing
   iteration branch and rerun the reader. A status-only request reads the named ref. Reporting readiness needs
   no `open_iteration.py`, new plans folder, ignore-rule edit or commit.
2. Read the output by `pipeline/references/where-am-i.md`. Report what closed, what changed since review,
   what is waiting and which questions belong to the next stages.
3. Offer each dependency-ready branch (backend and design can both be picked), then any optional repeat gate
   and stopping. Give equal branches equal weight unless the user chose a role. Wait for the stage selection.
4. In a parent session (`pipeline` → `references/parent-session.md`), offer all dependency-ready stages,
   regardless of the author of earlier documents. Open only the explicitly selected stages in this workflow.
   `subsessions.py plan` stores proposals; `authorize <stage>...` records the selected subset; `show` and resume
   never expand it. Historical opened rows are facts, not new consent. Without chat tools continue here.
