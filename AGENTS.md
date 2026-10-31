# The Codex build of the dev-pipeline plugin

This repository is built from the Claude Code plugin (the repository «Web dev plugin (claude)»: its
`claude/claude-code-skills/` and the Codex layer in its `codex/`) by `codex/build.py` on every release. A
release rewrites `dev-pipeline/`, `README.md`, `LICENSE` and this file whole.

You may change it here. Before the next release the maintainer reads every commit made here since the last
release commit and carries each change back, so the rebuild keeps it. Changes are sorted **by where they are**:

- **Codex's own places** — `dev-pipeline/skills/executor-catalog/references/codex-runtime.md`, the «Codex runtime»
  paragraph of each agent in `dev-pipeline/agents/`, the «Codex runtime» note at the top of each `SKILL.md`,
  `dev-pipeline/skills/pipeline/references/parent-session.md`, `dev-pipeline/install-agents.sh`,
  `dev-pipeline/models.json`, `dev-pipeline/hooks/hooks.json`: what is about Codex — its tools, chats, models,
  sandbox, folders — goes here, and stays Codex's.
- **Everywhere else** — a rule, a script, a hook, a skill's text: a change here is taken as general and carried
  into the Claude plugin too, so both versions get it. When something about Codex's environment has to sit in such
  a file, keep it short and say in the commit that it is about Codex; it is then kept as a Codex-only edit.

Also:

1. Say in each commit what broke or what Codex does differently — the reason is carried back with the text.
2. Keep `tests/` here: the build does not touch it, and the release runs it on every build
   (`python3.12 -m unittest discover -s tests -v`).
3. Do not rename or move files: the build writes them by their Claude paths.
