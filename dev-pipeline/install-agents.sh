#!/usr/bin/env bash
# dev-pipeline for Codex: install the executor agents the skills dispatch by name.
# A Codex plugin carries skills, hooks and MCP servers but not custom agents, so they are installed here:
#   agents/*.toml -> $CODEX_HOME/agents/<name>.toml   (CODEX_HOME defaults to ~/.codex)
# and nested dispatch is allowed: [agents] max_depth = 2 in $CODEX_HOME/config.toml
# (a writer agent spawns doc-typist; an implementer spawns mechanical-worker).
#
#   bash install-agents.sh              install or refresh (safe to re-run)
#   bash install-agents.sh --hook       also add the session-start hook to $CODEX_HOME/hooks.json
#                                       (only when the plugin's own hook does not run in your Codex)
#   bash install-agents.sh --uninstall  remove only the agent files this script installed
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
home="${CODEX_HOME:-$HOME/.codex}"
dest="$home/agents"
mark="# dev-pipeline agent"

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
[ -n "$skipped" ] && echo "skipped (a file you made has the same name, rename it to use the plugin's):$skipped"

cfg="$home/config.toml"
touch "$cfg"
if ! grep -q '^\[agents\]' "$cfg"; then
  printf '\n[agents]\nmax_depth = 2\n' >> "$cfg"
  echo "added [agents] max_depth = 2 to $cfg"
elif ! awk '/^\[agents\]/{s=1;next} /^\[/{s=0} s && /^max_depth[[:space:]]*=/{f=1} END{exit !f}' "$cfg"; then
  echo "ACTION: $cfg has an [agents] table without max_depth — add the line  max_depth = 2  under it"
else
  echo "$cfg already sets [agents] max_depth — make sure it is 2 or more"
fi

if [ "${1:-}" = "--hook" ]; then
  hooks="$home/hooks.json"
  if [ -f "$hooks" ]; then
    echo "ACTION: $hooks exists — add a SessionStart entry by hand:"
    echo "  matcher \"startup|resume|clear|compact\", command: sh \"$here/hooks/session-start.sh\""
  else
    cat > "$hooks" <<EOF
{
  "hooks": {
    "SessionStart": [
      { "matcher": "startup|resume|clear|compact",
        "hooks": [ { "type": "command", "command": "sh \"$here/hooks/session-start.sh\"" } ] }
    ]
  }
}
EOF
    echo "wrote $hooks — review and trust it with /hooks in Codex"
  fi
fi
