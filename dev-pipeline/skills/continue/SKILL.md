---
name: continue
description: >-
  Picks a project back up: reads the files on disk to tell where the pipeline stopped — which stage, what is done,
  what is stale — and offers the next step. Use for «продолжим», «где я», «что дальше», «на чём остановились», a new
  session on a project already started. Not for starting a new project (`brainstorm`) or a plugin update (`upgrade-docs`, `upgrade-code`).
---

> **Codex.** This skill was written for Claude Code. Read its tool terms — the `Agent` tool and `subagent_type`, `isolation: "worktree"`, Monitor, TaskStop, the Edit tool — as `../executor-catalog/references/codex-runtime.md` (beside this skill's folder) says, before the first agent you spawn, watcher you start or file you edit.

# Continue the project

A new session remembers nothing of the last one; the project's files do. This command reads them and puts the user
back at the right stage.

1. Read the `pipeline` skill and follow its «Where am I» exactly — the files on disk are the evidence, never what an
   earlier session seemed to say.
2. When a long run was stopped (`work`, the UI test run, the security audit), its `resume.md` beside the progress file
   is read first, as `pipeline/references/pause-and-resume.md` says.
3. Answer in plain Russian: where the project is, what is done, what is stale or waiting, and the next step — asked as
   `pipeline` → «Asking before a transition» asks it (run, skip, or stop). Start nothing before the answer.
