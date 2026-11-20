# Parallel waves

Read by `work` at Step 3 when a ready unit is `Параллельно: yes`. Serial is the default — one unit, one dispatch,
one commit — and most plans never need this file.

- **Parallel** only when all four hold (cap a wave at three):
  - the plan marks the peers `Параллельно: yes`;
  - their `Файлы` are genuinely disjoint in the current tree;
  - create a dedicated Git worktree for each stream; give the Codex worker its absolute working directory,
    `WORKTREE yes`, and repo-relative file paths; verify its checkout before it edits;
  - their focused tests share no runtime resource — or each gets its own. Files isolated in worktrees are not
    a database isolated: two streams on one compose database corrupt each other. A plan's `yes (своя БД)` /
    `yes (свой стенд)` means that is the only contention, so give it away — Streams below.
- **Never parallel** in a shared working directory: concurrent writes and
  concurrent test runs corrupt each other regardless of what the plan claims.
- **UI units after the foundation.** The first UI unit in plan order is the foundation: the generated API client,
  the app-wide error handler, shared components, styles and the dictionary of labels. It runs alone. After its
  commit, screen units the plan marks `yes (свой стенд)` run in parallel when their `Файлы`, e2e specs included,
  are disjoint — each on its own stand (ports, database). A screen executor never edits a shared component, a
  style or the dictionary: a lack of one goes into its NEEDS FROM ORCHESTRATOR, and the change is a separate unit
  in the main tree before the screen goes on.
- **Streams.** A plan's §4 may group independent chains of units into streams: a stream runs its units in order
  in one worktree, beside the others. Each stream gets, without a question to the user:
  - its own postgres container, started from the project's postgres image with the data in memory —
    `docker run -d --name <project>-s<k>-pg --tmpfs /var/lib/postgresql/data -e POSTGRES_HOST_AUTH_METHOD=trust
    -e POSTGRES_DB=<project>_test -p 127.0.0.1:<free port>:5432 <image> -c fsync=off -c synchronous_commit=off -c full_page_writes=off`, the migrations
    applied, its `TEST_DATABASE_URL` in the packet;
  - its own bucket and env when the tests need object storage, its own ports when they need a stand;
  - a line in `resume.md` → «Запущено» (container, port, bucket, worktree), so the stage's close removes
    them (`pipeline` → `references/handover-check.md` → The stage's leftovers).

  Inside a stream the executor runs only the unit's own tests, with `--maxWorkers=2` (pytest `-n 2`); the full
  suite runs once at stream or run close. Streams at once: about one per four cores,
  at most three — a full run takes every core, and two more beside it turn into timeouts. After confirming the unit commit includes all owned changes and the stream has no other edits, the stream's worktree moves onto that commit (`git -C <worktree> reset -q --hard <sha>`): its
  changes are in it, and the next unit starts from the main line with every stream's work so far.
- **Bring the wave home before Step 5.1.** Bring each worker's owned diff into the integration checkout as it returns. Verify and commit it there
  in Step 5, then advance its stream; workers do not commit their own changes.
  If that is not possible, run the wave serially instead.

Re-verify the plan's parallel claim against the tree before dispatching, then
decline parallelism under any remaining doubt. Speed is optional; a clean
history is not.
