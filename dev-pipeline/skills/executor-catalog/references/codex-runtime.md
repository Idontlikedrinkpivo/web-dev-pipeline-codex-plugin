# Running this plugin under Codex

This plugin is written for Claude Code and built for Codex by
`codex/build.py`. Its rules, packets, statuses, documents and stages are the
same under both. Only the tools differ: read each Claude Code term in the
skills and references as the Codex action below.

| The text says | Under Codex |
|---|---|
| the `Agent` tool, `subagent_type: "<name>"`, an executor row's name | spawn the custom agent `<name>` (installed as `~/.codex/agents/<name>.toml` by the plugin's `install-agents.sh`) with the packet as its task, and wait for its result before going on. If no agent by that name is installed, stop and say so — never run the work on the built-in `default`, `worker` or `explorer` instead |
| the call passes no `model`; the agent file holds it | the same: name no model when spawning — the `.toml` holds `model` and `model_reasoning_effort` |
| `run_in_background: false`, «in the foreground» | wait for the agent's result in the same turn |
| several `Agent` calls in one message | spawn them together and wait for all of them |
| a nested dispatch — a writer nests `doc-typist`, an implementer nests `mechanical-worker` | allowed when `~/.codex/config.toml` has `[agents]` `max_depth = 2` (`install-agents.sh` sets it). If a nested spawn is refused, the agent returns its settlement in its report and the session spawns the nested agent with that packet |
| `isolation: "worktree"` on a parallel dispatch | before spawning, make one worktree per agent: `git worktree add ../<repo>-wt-U<n> -b wt/U<n> HEAD`; start its packet with `WORKING DIRECTORY: <that path> — work and run every command there`; bring each branch home as `work` says, then `git worktree remove` it and delete the branch |
| a read-only agent (tools `Read, Grep, Glob, Bash`) | Codex cannot take the edit tool from one agent: its instructions forbid edits. After it returns, check `git status`; any change it made is reverted and named in the report |
| the Edit tool, the Write tool | edit a file with a patch (`apply_patch`); create a file the same way |
| the Monitor tool, a background `sleep` watcher | no tool here notifies you: check the watched files yourself after each agent returns and before every message to the user. «Stop the watcher» means stop checking |
| TaskStop | stop the spawned agent and confirm it stopped |
| `<folder of this SKILL.md>` in a command | the folder that holds the `SKILL.md` you are reading |
| `.agents/skills/verify/` | the project's own skills live in `.agents/skills/` under Codex (in Claude Code the same skill sits in `.claude/skills/`; read either when only one exists) |
| `codex plugin marketplace upgrade` | how this plugin updates under Codex |
| Claude Code's built-in `/code-review` | Codex's `/review` |
| `reflect` | reads this project's Codex sessions (rollout files under `~/.codex/sessions/`) with the Codex build's `sessions.py`; the feedback file is `~/.codex/dev-pipeline-feedback/<project>.md` |
| model names in `executor-catalog` (`opus`, `sonnet`, `haiku`) and its measurements | they name the Claude originals and were measured there. The Codex model of each row is in its `.toml`; the map is the plugin's `models.json` |
