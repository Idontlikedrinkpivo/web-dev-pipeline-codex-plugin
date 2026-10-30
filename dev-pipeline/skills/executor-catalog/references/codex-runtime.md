# Running this plugin under Codex

This plugin is written for Claude Code and built for Codex by
`codex/build.py`. Its rules, packets, statuses, documents and stages are the
same under both. Only the tools differ: read each Claude Code term in the
skills and references as the Codex action below.

| The text says | Under Codex |
|---|---|
| the `Skill` tool, invoking `dev-pipeline:<skill>` | read that skill's `SKILL.md` (its path is in your skills list under `dev-pipeline:<skill>`) and follow it. Codex namespaces a plugin's skills as Claude Code does; the user types a skill as `$dev-pipeline:<skill>` |
| `dev-pipeline:<agent>` — an agent's full name in Claude Code | the plain `<agent>`: a Codex custom agent has no plugin prefix, its name is the `name` in its `.toml`. The build already strips it from dispatch lines |
| the `Agent` tool, `subagent_type: "<name>"`, an executor row's name | spawn the custom agent `<name>` (installed as `~/.codex/agents/<name>.toml` by the plugin's `install-agents.sh`) with the packet as its task, and wait for its result before going on. If no agent by that name is installed, stop and say so — never run the work on the built-in `default`, `worker` or `explorer` instead |
| `install.sh`, «install the `dev-pipeline` plugin» for a missing agent | the agents come from the plugin's `install-agents.sh` (README → Установка), not from the plugin itself: name that script to the user |
| the call passes no `model`; the agent file holds it | the same: name no model when spawning — the `.toml` holds `model` and `model_reasoning_effort` |
| `run_in_background: false`, «in the foreground» | wait for the agent's result in the same turn |
| several `Agent` calls in one message | spawn them together and wait for all of them |
| a nested dispatch — a writer nests `doc-typist`, an implementer nests `mechanical-worker` | spawn the nested agent from inside the agent — checked on a user's machine: two levels work (an agent spawning an agent), and a spawned agent can ask its parent a question and wait. Codex's docs do not describe nesting; `install-agents.sh` sets `[agents]` `max_depth = 2` in `~/.codex/config.toml`, a key Codex's docs leave out (in its source it limits the nesting depth of the original multi-agent mode, default 1, and the `multi_agent_v2` mode ignores it). If a nested spawn is refused, the agent returns its settlement in its report and the session spawns the nested agent with that packet |
| `isolation: "worktree"` on a parallel dispatch | before spawning, make one worktree per agent: `git worktree add ../<repo>-wt-U<n> -b wt/U<n> HEAD`; start its packet with `WORKING DIRECTORY: <that path> — work and run every command there`; bring each branch home as `work` says, then `git worktree remove` it and delete the branch |
| a read-only agent (tools `Read, Grep, Glob, Bash`) | the rule rests on its instructions: a custom agent runs in the session's own sandbox (`sandbox_mode` in an agent file does not apply) and an agent file has no documented key that removes the edit tool. After it returns, check `git status`; any change it made is reverted and named in the report |
| the Edit tool, the Write tool | edit a file with a patch (`apply_patch`); create a file the same way |
| the Monitor tool, a background `sleep` watcher | no tool here notifies you: check the watched files yourself after each agent returns and before every message to the user. «Stop the watcher» means stop checking |
| TaskStop | stop the spawned agent and confirm it stopped |
| a nested session: `mcp__ccd_session__start_session` (`pipeline` → `references/parent-session.md`) | a separate chat: `mcp__codex_app__create_thread` with only the prompt it needs — never `fork_thread`, which carries this chat's history and defeats the fresh context. Codex chats sit side by side in the sidebar, not under the parent; name each «<version> · <stage>» so the set reads in order. Whether Codex lets a chat open a chat in a turn the user did not begin is not yet checked — if the call is refused, follow the rule as written: a waiting reserve chat opened in the user's turn, or ask the user |
| `SendMessage` to a session, «wake it with a message» | `mcp__codex_app__send_message_to_thread` to that chat's id. Codex asks the user to approve each such message — shown only when they open that chat — unless they ran `install-agents.sh --autonomous-chats`; when a report to the parent waits for approval, tell the user once in the parent that this switch lets stages run without them |
| `wake_when_done`, «a note comes back when its turn ends» | `mcp__codex_app__wait_threads` on the chats you opened, or `read_thread` before saying anything about one |
| `mcp__ccd_session_mgmt__get_session` `self` — the parent's id for a nested session's prompt | this chat's id: from `mcp__codex_app__list_threads` (the current chat), or the id the parent gave you |
| `mcp__ccd_session_mgmt__set_session_title`, `archive_session` | `mcp__codex_app__set_thread_title`, `set_thread_archived` |
| `<folder of this SKILL.md>` in a command | the folder that holds the `SKILL.md` you are reading |
| `SKILLS ROOT` in a packet, «the parent of the dispatching skill's base directory» | the plugin's `skills/` folder, as an absolute path: the parent of the folder that holds the `SKILL.md` you are reading (the folder with `executor-catalog/`, `work/` and the other skills). Codex prints no «Base directory» line; take the path from your skills list |
| `.agents/skills/verify/` | the project's own skills live in `.agents/skills/` under Codex (in Claude Code the same skill sits in `.claude/skills/`; read either when only one exists) |
| `codex plugin marketplace upgrade` | how this plugin updates under Codex |
| Claude Code's built-in `/code-review` | Codex's `/review` |
| `reflect` | reads this project's Codex sessions (rollout files under `~/.codex/sessions/`) with the Codex build's `sessions.py`; the feedback file is `~/.codex/dev-pipeline-feedback/<project>.md` |
| model names in `executor-catalog` (`opus`, `sonnet`, `haiku`) and its measurements | they name the Claude originals and were measured there. The Codex model of each row is in its `.toml`; the map is the plugin's `models.json` |
