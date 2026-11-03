# Running dev-pipeline under Codex

This is the Codex runtime contract for the plugin's skills, references and
agent packets. Where inherited Claude Code tool names occur, use the mappings
below. Host instructions and actual tool schemas always take precedence.

## Stages and chats

Separate stage chats keep each stage's context fresh. When the user requests
this workflow, use pipeline/references/parent-session.md: the parent coordinates,
and stage chats run the skills and their named executors. An explicit agreement
to the stage-chat list authorizes creation of that list; never pre-open an
unapproved list or treat tool availability as authorization. Use a fresh prompt,
not fork_thread, for stage chats. Thread permissions never override host rules.

Without chat tools or without a request for separate chats, run stages in the
current chat with named executors. Save progress and resume.md at boundaries;
after compaction read pipeline and the active skill again. If a fresh chat is
needed, save the handover and ask the user to open it, or create it when asked.

## Tool mappings

| Inherited term | Codex action |
|---|---|
| Skill, `dev-pipeline:<skill>` | Read the skill's SKILL.md and follow it; find the path in the available skills list or this plugin's skills/ directory. User invocation: `$dev-pipeline:<skill>`. |
| Agent, `subagent_type: <name>` | Use the available spawn_agent tool with `agent_type: <name>`, a unique task_name and the worker packet as message. Use `fork_turns: "none"` where supported: the packet is the complete input. Never replace a missing custom role with default/worker/explorer. |
| Agent's model | Omit model and reasoning_effort overrides; the custom TOML owns them. Roles are installed into `${CODEX_HOME:-~/.codex}/agents/` by install-agents.sh. If unavailable, report the missing role and installation command; do not perform its task as a fallback. |
| Foreground or run_in_background: false | Wait for completion in the same turn. A wait timeout is not completion. Read the final report before proceeding. |
| Several agents | Spawn independent packets up to the host's concurrency limit; queue remaining packets. Wait for every required result. Assign explicit file ownership and tell writers they share the repository and must preserve others' edits. |
| Nested Agent | Spawn the named role with a fresh packet if supported. If refused, return BLOCKED with the complete pending packet; the parent dispatches that role, returns its result and resumes the original agent to verify and finish. Never claim DONE while printing or verification is pending. |
| SendMessage to an agent | Use send_message for steering, followup_task to resume an idle agent where available; otherwise follow the host's agent messaging schema. |
| TaskStop | Use the host's close/stop tool when available. interrupt_agent interrupts a turn but leaves the agent reusable: inspect its state before merging or cleaning a worktree. Never treat an interruption alone as completed work. |
| Monitor, background watcher | Use agent completion notifications and bounded waits; inspect progress files after results. Poll shell sessions with write_stdin. Stop shell processes through their session/process controls, not an agent-stop tool. |
| isolation: worktree | Create a git worktree in a writable location before spawning, specify its absolute working directory in the packet and every command. Request approval if the location requires it. Integrate and remove only that agent's worktree after it stops. |
| Read, Grep, Glob | Read files with available filesystem/shell tools; prefer rg for searches and read large files in bounded sections. |
| Edit, Write | Use apply_patch. Shell tools use exec_command; do not assume Claude's Bash schema. Hooks receive the compatible canonical Bash/command shape. |
| Read-only agent | Instruct it to avoid edits; snapshot status/diff before and after. Preserve existing user and concurrent edits; never revert files based only on git status. Attribute unexpected changes before undoing anything. |
| ToolSearch | Discover deferred tools through the host's tool catalog/search facility. Inspect their actual schema; do not guess tool names or arguments. |
| SKILLS ROOT | Absolute path to this plugin's skills/ folder. `<folder of this SKILL.md>` means the folder containing the skill being read. |
| Project instructions and verify | AGENTS.md and .agents/skills/verify/. Read legacy project files only when needed for an existing project. |
| Built-in code review | Codex /review when available. |
| Built-in browser, preview_start, navigate | Discover available browser tools and read their browser skill. Open the served http://127.0.0.1:<port>/ URL using the actual schema. Without browser tools, give the HTTP link; do not claim it was opened. |
| Progress HTML links | Use the HTTP URL printed by pipeline/scripts/progress_link.py. The Codex build starts or reuses the local server automatically; never replace that URL with a repository file link, whose HTML preview can be blocked. If the server fails, report the error and resolve it before claiming the page opens. |
| Figma or Context7 tools | Discover by capability, not a fixed MCP prefix. Use connected tools first. If the needed capability or login is absent, report the precise blocker; never invent a successful edit. |
| reflect | Read rollouts under CODEX_HOME/sessions and archived_sessions. Feedback belongs under CODEX_HOME/dev-pipeline-feedback. Log availability and formats vary; missing logs do not prove no activity. |
| opus, sonnet, haiku | Historical Claude measurements, not available Codex model names. The actual role model is in agents/<name>.toml; models.json documents the mapping. Explain a requested Claude model's absence instead of silently claiming to use it. |

For explicitly requested sidebar chats, discover create_thread, wait_threads,
read_thread and send_message_to_thread in the Codex app catalog. Use the
returned IDs and schemas; do not guess a current chat ID from a title. Prefer
compact wait_threads snapshots, and preserve user input/approval requests.
These app tools are optional and are not required for the normal pipeline.

## Codex model selection

Plugin-root models.json owns explicit role:<name> settings and _stages chat recommendations. Role TOML settings govern agents only; stage chats follow parent-session.md model-selection consent and creation arguments. Use executor-catalog/references/model-economics.md for Codex reasoning and evidence limits; inherited Claude model benchmarks and alias restrictions do not apply.
