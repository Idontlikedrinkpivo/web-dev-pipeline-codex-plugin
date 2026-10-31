# The Codex build of the dev-pipeline plugin

This repository is built from the Claude Code plugin (the repository «Web dev plugin (claude)»: its
`claude/claude-code-skills/` and the Codex layer in its `codex/`) by `codex/build.py` on every release. A
release rewrites `dev-pipeline/`, `README.md`, `LICENSE` and this file whole.

You may change it here. Before the next release the maintainer reads every commit made here since the last
release commit (`claude/tools/codex_sync.py`) and carries each change back, so the rebuild keeps it:

- **a general change** — a rule, a script, a hook or a fix that would be as right under Claude Code — goes into the
  Claude plugin's source and comes back here in every build;
- **a Codex-only change** — Codex's tools, its chats, its models, its sandbox, its folders — goes into the Codex
  layer of the build.

To make that sorting exact:

1. One subject per commit. Start its message with `[general]` or `[codex]`; a commit with both kinds lists them
   under those two headings in its body, one line per change.
2. Say why, in one line per change: what broke or what Codex does differently. The maintainer carries the reason,
   not only the text.
3. Keep `tests/` here: the build does not touch it, and the release runs it on every build
   (`python3.12 -m unittest discover -s tests -v`).
4. Do not rename or move files: the build writes them by their Claude paths.
