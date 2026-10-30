#!/usr/bin/env bash
# dev-pipeline for Codex: install the executor agents the skills dispatch by name.
# A Codex plugin carries skills, hooks and MCP servers but not custom agents, so they are installed here:
#   agents/*.toml -> $CODEX_HOME/agents/<name>.toml   (CODEX_HOME defaults to ~/.codex)
# and nested dispatch is asked for (a writer agent spawns doc-typist; an implementer spawns mechanical-worker):
#   [agents] max_depth = 2 in $CODEX_HOME/config.toml
# Codex's docs do not list max_depth. In Codex's source it is the nesting limit of the original multi-agent mode
# (default 1) and the multi_agent_v2 mode ignores it. If a nested spawn is still refused, the agent hands its packet
# back and the session spawns the nested agent itself (codex-runtime.md).
#
#   bash install-agents.sh              install or refresh (safe to re-run)
#   bash install-agents.sh --hook       also add the session-start hook to $CODEX_HOME/hooks.json
#                                       (only when the plugin's own hook does not run in your Codex)
#   bash install-agents.sh --uninstall  remove only the agent files this script installed
#   bash install-agents.sh --autonomous-chats     let the plugin's stage chats open each other and message each
#                                       other without asking: approval_mode = "approve" for the Codex app's thread
#                                       tools (create_thread, send_message_to_thread, set_thread_title,
#                                       set_thread_archived) in $CODEX_HOME/config.toml — opt-in, a backup first
#   bash install-agents.sh --no-autonomous-chats  remove those lines again
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
home="${CODEX_HOME:-$HOME/.codex}"
dest="$home/agents"
mark="# dev-pipeline agent"

# The thread tools come from the bundled plugin codex-app-tools@openai-bundled, MCP server codex_app — so their
# approval lives under plugins."codex-app-tools@openai-bundled".mcp_servers.codex_app.tools.<tool> (checked on a
# user's machine, 2026-10-30; the top-level [mcp_servers] and [apps] tables do not reach them).
chats() {
  python3 - "$1" "$home/config.toml" <<'PY'
import pathlib, shutil, sys
mode, cfg = sys.argv[1], pathlib.Path(sys.argv[2])
tools = ["create_thread", "send_message_to_thread", "set_thread_title", "set_thread_archived"]
head = '[plugins."codex-app-tools@openai-bundled".mcp_servers.codex_app.tools.{}]'
mark = "# dev-pipeline: stage chats without approval (install-agents.sh --autonomous-chats)"
cfg.parent.mkdir(parents=True, exist_ok=True)
text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
if mode == "on":
    missing = [t for t in tools if head.format(t) not in text]
    if not missing:
        print(f"{cfg} already lets the stage chats run without approval"); sys.exit(0)
    if cfg.exists():
        shutil.copy(cfg, cfg.with_name(cfg.name + ".dev-pipeline.bak"))
    block = "".join(f"\n{mark}\n{head.format(t)}\napproval_mode = \"approve\"\n" for t in missing)
    cfg.write_text(text.rstrip("\n") + "\n" + block, encoding="utf-8")
    print(f"added approval_mode = \"approve\" for {', '.join(missing)} to {cfg} (backup: {cfg.name}.dev-pipeline.bak)")
    print("restart the Codex app; any chat can now open chats and write to them without asking — undo with --no-autonomous-chats")
else:
    lines, out, skip = text.splitlines(), [], 0
    for l in lines:
        if l == mark:
            skip = 2; continue
        if skip:
            skip -= 1; continue
        out.append(l)
    if len(out) == len(lines):
        print(f"{cfg} has no lines this script added for the stage chats"); sys.exit(0)
    cfg.write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")
    print(f"removed the stage-chat approvals this script added from {cfg} — restart the Codex app")
PY
}
case "${1:-}" in
  --autonomous-chats) chats on; exit 0 ;;
  --no-autonomous-chats) chats off; exit 0 ;;
esac

if [ "${1:-}" = "--uninstall" ]; then
  n=0
  for f in "$dest"/*.toml; do
    [ -f "$f" ] && head -n 1 "$f" | grep -qF "$mark" && rm "$f" && n=$((n + 1))
  done
  echo "removed $n dev-pipeline agents from $dest"
  exit 0
fi

mkdir -p "$dest"
n=0; skipped=""
for src in "$here"/agents/*.toml; do
  name="$(basename "$src")"
  if [ -f "$dest/$name" ] && ! head -n 1 "$dest/$name" | grep -qF "$mark"; then
    skipped="$skipped $name"; continue      # someone else's agent with the same name
  fi
  cp "$src" "$dest/$name"; n=$((n + 1))
done
echo "installed $n agents into $dest"
echo "to let stages run in their own chats without you approving each step: bash $here/install-agents.sh --autonomous-chats"
[ -n "$skipped" ] && echo "skipped (a file you made has the same name, rename it to use the plugin's):$skipped"

cfg="$home/config.toml"
touch "$cfg"
if ! grep -q '^\[agents\]' "$cfg"; then
  printf '\n[agents]\nmax_depth = 2\n' >> "$cfg"
  echo "added [agents] max_depth = 2 to $cfg (not in Codex's docs; lets an agent spawn a nested agent where Codex honours it)"
elif ! awk '/^\[agents\]/{s=1;next} /^\[/{s=0} s && /^max_depth[[:space:]]*=/{f=1} END{exit !f}' "$cfg"; then
  echo "ACTION: $cfg has an [agents] table without max_depth — add the line  max_depth = 2  under it (not in Codex's docs; lets an agent spawn a nested agent where Codex honours it)"
else
  echo "$cfg already sets [agents] max_depth — make sure it is 2 or more"
fi

hooks="$home/hooks.json"
# Codex installs each plugin version into its own folder (.../dev-pipeline/<version>/) and removes the old one, so a
# hook added by an earlier --hook points at a folder that is gone: move it to this one. The changed command is a new
# hook definition for Codex, which runs it only after it is trusted again in /hooks.
if [ -f "$hooks" ] && grep -q 'dev-pipeline[^"]*/hooks/session-start\.sh' "$hooks" \
    && ! grep -qF "$here/hooks/session-start.sh" "$hooks"; then
  sed -i.bak -E "s#[^\"\\\\]*dev-pipeline[^\"\\\\]*/hooks/session-start\.sh#$here/hooks/session-start.sh#g" "$hooks"
  rm -f "$hooks.bak"
  echo "pointed the session-start hook in $hooks at $here — trust it again with /hooks in Codex"
fi

if [ "${1:-}" = "--hook" ]; then
  if grep -qF "$here/hooks/session-start.sh" "$hooks" 2>/dev/null; then
    echo "$hooks already runs this plugin's session-start hook"
  elif [ -f "$hooks" ]; then
    echo "ACTION: $hooks exists — add a SessionStart entry by hand:"
    echo "  matcher \"startup|resume|clear|compact|fork\", command: sh \"$here/hooks/session-start.sh\""
  else
    cat > "$hooks" <<EOF
{
  "hooks": {
    "SessionStart": [
      { "matcher": "startup|resume|clear|compact|fork",
        "hooks": [ { "type": "command", "command": "sh \"$here/hooks/session-start.sh\"" } ] }
    ]
  }
}
EOF
    echo "wrote $hooks — review and trust it with /hooks in Codex"
  fi
fi
