# The Codex version of the dev-pipeline plugin

The Codex and Claude Code versions are maintained independently. This repository is the source of truth for
the Codex version; edit and release it here.

Do not synchronize code, skills, agents, documentation, releases or version numbers between the two versions.
Do not run `codex/build.py` or `claude/tools/codex_sync.py` to overwrite this repository or carry its changes
back to the Claude Code plugin. Cross-version transfers require an explicit user request.

Also:

1. Say in each commit what broke or why the change is needed.
2. Keep `tests/` here and run the local checks before a release
   (`python3.12 -m unittest discover -s tests -v`).
3. Do not rename or move files.
