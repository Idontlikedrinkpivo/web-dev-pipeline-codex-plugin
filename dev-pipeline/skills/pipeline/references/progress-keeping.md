# Keeping progress

Read before every long stage and again after compaction. Shape and vocabulary:
`references/progress-files.md`; keeping the run moving: the last section of
`references/unattended.md` (every long run reads it).

## Updates

- **When.** Create the file before the first step or dispatch, every row
  `⏳ ждёт`, run the script, open the link in the built-in browser
  yourself when there is one, and paste the line before the first step
  starts. A run resumed after a break or a context compaction rebuilds
  the rows from what is on disk, sets anything half-done back to
  `⏳ ждёт`, and pastes the line again before it goes on.
- **After each item.** Every time an item is finished — its row reaches
  done, stopped or returned — run the script and paste its line, so a user
  who closed the page or stepped away reopens it from the last message,
  not by scrolling to the start. A stop or a question to the user carries
  the line too, as its last line. Any message that mentions the progress
  file carries the line; a file name in plain text or in backticks opens
  nothing.
- **The server** is stopped at the iteration's close
  (`references/closing-cleanup.md`) or when the user says they are done
  watching: `python3 "<pipeline skill folder>/scripts/progress_server.py"
  documentation/plans/<version> --stop`.
- **The file is never named without its line.** «Обновил прогресс в
  progress-design.md — файл можно открыть» is wrong: the name opens
  nothing, and the user has to search for the file. Where a subagent
  changes the rows (the Figma builder, the test writer, the test runner),
  paste the script's line each time its dispatch returns.

## How

Change it with the **Edit** tool the moment a row changes — one
call per row or line, then refresh the bar and count with `progress_set.py` where they are not derived — and
**Write** only to create it (a shell write to a progress file is refused by the plugin's hook,
`hooks/guard.py`). Never from the shell (`python`, `sed`,
`cat >`), and never by a script that rewrites the file on a timer: the
page is rebuilt by the plugin's hook on Edit and Write only, so a file
changed any other way is fresh on disk and stale on the page the user
watches. Four scripts are the exception, and all redraw the page
themselves: `progress_e2e.py` (`work` → `references/progress-file.md` →
The e2e section), `progress_mutation.py` (the top of
`progress-mutation.md`, from the mutation logs), `progress_link.py` (stamps
the state before printing the chat line), and
`progress_set.py <file> <done> <total> [--section
"<heading>"]`, which sets the bar, count and state time in its section — never copy a
hundred-cell bar into an Edit by hand: one cell off and the Edit fails.
Rows still change with Edit, after a fresh Read of the file. After a
compaction this rule is the first one lost: re-read it before the next
change of the file; `progress_link.py` names a bar that disagrees with the
count, and validates status words and count lines. The agent writes rows and state text;
scripts write bars, counts and times. Start the timestamp as «обновлено …»; the four scripts replace it with the time.
For derived files, edit the rows and run `progress_link.py`; the page computes the bar and count.

## Subagents and watchers

- **A subagent's rows are watched, not trusted.** A subagent deep in its
  task forgets the progress file, and then the user sees a hang. So while
  a dispatch that owns rows runs and writes files, the session watches its
  output folder with the Monitor tool — a loop that prints each file as it
  changes, e.g. `while sleep 20; do git status --porcelain --
  documentation/ui/test-cases; done | awk '!seen[$0]++'` — and on each new
  line sets that item's row to `🔄 в работе` if the subagent has not
  (without Monitor: a background `sleep 30`, then the same check). When
  the dispatch returns, it reconciles every row, the bar and the count
  with what is on disk before the chat line, and says in that line what it
  corrected. Output that is not files (Figma) is reconciled on return,
  from the report.
- **Every watcher ends with its work.** A Monitor or a background wait the
  run starts carries its own end: it watches until a condition that the
  work's end makes true (the queue's last result, a done marker, the
  process gone) and then exits, never only until its timeout. The run keeps
  the ids of the watchers it started and, when it ends — finished, failed
  or stopped — stops any still running (TaskStop) before its last line. A
  watcher left behind keeps waking the session for nothing; an agent that tries to end with one still running
  must inspect available agent/process tools and stop its own tasks before reporting;
  unknown status blocks transfer, and no watchers.py hook is promised.
- **Results from background work** (stands, long commands) wake the agent,
  and the agent edits: watch their output with the Monitor tool, which
  wakes the session on each new line, or bounded shell-session polling through the Codex runtime mapping;
  do not invent a Monitor or watcher tool the host does not expose.
- **A subagent** that changes rows gets the path in its packet as
  `PROGRESS FILE` and changes only its rows, the bar and the count line;
  the title, the other sections and the state line stay the session's.
