# Stage chats in Codex — fresh context for each stage

The pipeline always runs this way — the user's choice: the parent chat
coordinates, and every stage runs in its own fresh chat with its own skill and
named subagents. There is no «all in this chat» option. Only without chat tools
(a CLI with no chat creation) do the stages run in the current chat, as
executor-catalog/references/codex-runtime.md describes.

At an iteration's start or continuation the parent asks once which stage
chats to open — the same wherever the work starts: a new project, a stage the
user asked for directly, a continued iteration, a clone another person picked
up (chat IDs from another machine reach nobody, so the list is rebuilt). Only
the stages left from the current point are listed, numbered, so no chat opens
for work already done or not wanted (Russian, as the user reads it):

```text
**Чаты этапов итерации <version>**

Пайплайн всегда идёт так: этот чат ведёт итерацию, а каждый этап — в своём
свежем чате. У этапа чистый контекст: он видит только свои документы и не
тащит переписку прошлых этапов; правила этапа не теряются при сжатии
переписки; весь план итерации виден в боковой панели. Codex может спросить
подтверждение на создание каждого чата.

Сейчас: <first open point, from where_am_i>. Уже сделано: <done stages; «ничего» on a start>.
Осталось:
1. <title>
2. <title> — если <condition>
…

Какие открыть? Ответьте «все» или номера нужных этапов.
```

## Establish the stage list

1. Read where_am_i.py and the stage chain. Continue the open iteration rather
   than guessing state from chat history. Agree the version when needed.
2. Build the remaining stages. Fixes a check sends back (UI tests, the audit) run
   inside that check's own chat, by agents — no chat of their own. Use pipeline/scripts/subsessions.py <project> <version> plan
   and show to maintain documentation/plans/<version>/sessions.md. Read the
   script's usage before calling it. It records status; it does not create chats.
3. Ask the question above once, with these titles; a stage the user asked for
   directly is marked «— вы просили». «все», or the numbers chosen, authorizes
   exactly those chats. A stage left out is not run in this iteration; when it
   is a gate a chosen one needs, say so in one line and ask once more.
4. Discover the Codex app's create_thread, wait_threads, read_thread,
   send_message_to_thread and title/archive tools. Use their returned schemas,
   including project/workspace, host and chat IDs. If the current parent ID is
   not provided by the host, do not infer it by matching a title: use completion
   polling from the parent and read_thread to retrieve the stage report.
   The host controls model and effort for new chats. Follow its model-selection
   rules and omit overrides when the user has not explicitly requested them;
   do not claim that a child inherited the parent's settings unless verified.
5. Create only the agreed chats with fresh prompts, the correct project and
   local workspace. Never fork the parent history. Record each returned chat ID
   immediately with subsessions.py set. For queued worktree setup, wait for its
   result before recording a runnable chat ID. Do not assume a created chat has
   already run. Report created chats using the host's required UI directives.

## Run and wait

A stage with unresolved dependencies starts with a waiting prompt; it must not
run until told to start. Prefer creating a ready stage just in time when that
is covered by the agreed list, rather than keeping idle chats indefinitely.

Send the ready stage its packet. Use send_message_to_thread only within the
user-authorized workflow. Surface approval or user-input requests to the user;
never change global approval settings to make a blocked tool succeed.

Wait with compact wait_threads snapshots. Keep each returned cursor and hostId
and supply afterCursor on the next wait; do not repeatedly read whole chats.
Bound waits so the parent can communicate progress. Retrieve the final report
and verify files before starting the next stage; a timeout or an unchanged
snapshot is not completion. A stage message to its parent is optional: the
parent's wait/read path must work without one.

For each stage packet include:

```text
Ты — чат этапа <stage> итерации <version> dev-pipeline.
Проект: <absolute project path>. Скиллы: <absolute skills root>.
Запусти <skill>, прочитай его SKILL.md и codex-runtime.md.
Источники: <documents and reports>. Состояние: <progress file and resume.md>.
Зависимости: <ready now, or wait for an explicit start message>.
Веди этот этап и вопросы пользователю здесь. Не открывай следующие чаты.
Результат: статус DONE/BLOCKED/STOPPED, изменённые файлы, проверки,
решения пользователя, следующий этап и точка продолжения.
Перед завершением запиши все решения в файлы и выполни проверки этапа.
Если требуется ответ пользователя, не выдавай этап за завершённый.
```

The parent verifies the report against files/git, marks the row closed or
blocked, and starts the next dependency-ready stage within the agreed scope.
Independent stages can run concurrently only with explicit file ownership.
Ask the user before transitions wherever the stage's skill requires it; do not
silently change an agreed transition rule.

## Handover and cleanup

Before context fills, save decisions, progress and resume.md; run the handover
check using the saved artifacts. Resume in a fresh authorized chat with only
the packet and file paths. If another chat is outside the agreed list, ask the
user to create it or approve its creation. Do not open reserve chats to bypass
a refusal. After compaction, each chat reloads its skill and on-disk state.

Do not archive chats automatically on completion. Use set_thread_archived only
when the user asks for archival, for the selected chats. Keep the parent small:
short status/report packets, files as the source of truth, no copied transcripts.
