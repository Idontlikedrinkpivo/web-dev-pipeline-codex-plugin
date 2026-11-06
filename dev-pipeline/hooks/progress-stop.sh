#!/bin/sh
# Stop: request the printed progress link once; never trap a resumed Stop in a loop.
command -v python3 >/dev/null 2>&1 || { cat >/dev/null 2>&1; exit 0; }
python3 "$(dirname "$0")/progress_stop.py" 2>/dev/null
exit 0
