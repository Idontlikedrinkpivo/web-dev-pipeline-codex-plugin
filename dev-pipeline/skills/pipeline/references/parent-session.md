# Stage chats in Codex — fresh context for each stage

When the user selects separate stage chats, the parent coordinates and each selected
stage runs in a fresh chat with named subagents. Tool availability alone authorizes
nothing. Without this choice or without chat tools, continue in the current chat
as executor-catalog/references/codex-runtime.md describes.

## Which one am I

The first step of any chat that starts pipeline work, a stage asked for
directly included; the first stages' SKILL.md (brainstorm, srs-writer) send
here before they read anything.

- A chat whose first message names a parent («Ты — чат этапа …», «ты —
  подсессия», «родительская сессия — …») runs its stage.
- Any other chat searches the tools for create_thread before deciding it is
  absent. Found and separate chats explicitly selected → this chat coordinates
  the selected stages under this file. Otherwise the stages run in this chat.

At an iteration's start or continuation the parent asks once which stage
chats to open — the same wherever the work starts: a new project, a stage the
user asked for directly, a continued iteration, a clone another person picked
up (chat IDs from another machine reach nobody, so the list is rebuilt). Only
the stages left from the current point are listed, numbered, so no chat opens
for work already done or not wanted (Russian, as the user reads it):

```text
**Чаты этапов итерации <version>**

Можно вести выбранные этапы в отдельных чатах: этот чат ведёт итерацию,
а каждый выбранный этап — в своём свежем чате. У этапа чистый контекст: он видит только свои документы и не
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

The agreed chats are grouped in one custom sidebar section for the iteration,
with the parent first and the stages in sessions.md order. Tell the user this
when presenting the list. Project membership is preserved.

## Establish the stage list

1. Read where_am_i.py and the stage chain. Continue the open iteration rather
   than guessing state from chat history. Agree the version when needed.
2. Build the remaining stages. Fixes a check sends back (UI tests, the audit) run
   inside that check's own chat, by agents — no chat of their own. Use pipeline/scripts/subsessions.py <project> <version> plan
   and show to maintain `<absolute-git-dir>/pipeline-work/<version>/<chat-key>/sessions.md`. Read the
   script's usage before calling it. `plan` records proposed stages only; `show`
   never expands consent. `authorize <stage>...` explicitly replaces the selected
   subset (empty revokes it); `set` requires authorization. Old opened rows remain
   historical facts, not authorization. Canonical stage numbers/order stay stable.
   Offer all ready stages regardless of historical author; file ownership limits
   simultaneous writers only. These commands do not create chats.
3. Ask the question above once, with these titles; a stage the user asked for
   directly is marked «— вы просили». «все», or the numbers chosen, authorizes
   exactly those chats. A stage left out is not run in this iteration; when it
   is a gate a chosen one needs, say so in one line and ask once more.
4. Discover the Codex app's create_thread, wait_threads, read_thread,
   send_message_to_thread and title/archive tools. Use their returned schemas,
   including project/workspace, host and chat IDs. If the current parent ID is
   not provided by the host, do not infer it by matching a title: use completion
   polling from the parent and read_thread to retrieve the stage report.
   Read _stages in the plugin-root models.json for each stage key in sessions.md.
   Include the recommended model and effort in the proposed chat list and ask:
   «Использовать указанные рекомендуемые модели и effort или ваши настройки?»
   Explicit acceptance of the named configuration authorizes those overrides;
   a bare request to open chats without that model choice does not. A user's
   specific model request wins. When recommendations were explicitly selected,
   pass model and thinking (the _stages effort) to create_thread. Otherwise omit
   overrides and use host defaults. Never claim the child inherited the parent's
   settings unless verified. Existing running chats are not silently changed.
5. Create only the agreed chats with fresh prompts, the correct project and
   local workspace. Never fork the parent history. Record each returned chat ID
   immediately with subsessions.py set. For queued worktree setup, wait for its
   result before recording a runnable chat ID. Do not assume a created chat has
   already run. Report created chats using the host's required UI directives.

## Keep the sidebar in stage order

Project chat lists are sorted by recent activity, so creation order and title
numbers alone cannot keep the stages in order. Never repeatedly rename chats
or send messages merely to manipulate recency; never change global sidebar sorting.

After creating the agreed chats, discover list_threads, create_sidebar_section,
move_thread_to_sidebar_section and reorder_section. Use their actual schemas:

1. Inspect existing sections and the IDs recorded in sessions.md. Reuse a section
   already containing these iteration chats. A matching name alone is not proof
   of identity; if it is ambiguous, create a distinct section instead of moving
   unrelated work. For a new section use «<project name> · <version>».
2. Move this iteration's parent and confirmed stage chat IDs into that custom
   section. Keep their project associations and existing titles. Do not move a
   whole project or chats from another iteration. Do not guess the parent ID;
   if unavailable, order the known stages and report that limitation.
3. Use reorder_section to place the parent first, then stages in the canonical
   sessions.md row order (not activity order or an alphabetical title sort).
   Include every current chat in that section exactly once as the tool requires;
   preserve the relative order of any other user-added chats after the iteration
   chats. Fetch fresh inventory before reordering so no item is silently dropped.
4. Inspect the resulting section item order before claiming success. When an
   additional stage is authorized later, insert it at its canonical position and
   verify again. Ordinary stage messages need no reorder: the section is manual.

If the host lacks manual section ordering, keep the canonical numbered list in
sessions.md and tell the user that the host controls sidebar recency. Do not
promise a fixed order based only on reverse creation, names or timing. Sidebar
organization does not start work, authorize more stage chats or resolve gates.

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
Чужой документ здесь не правь и его писателя не запускай: родителю отправь «РЕШЕНИЕ · <было> → <стало> · решил <кто> · владелец: <этап> · жду», а как владелец после записи ответь «РЕШЕНИЕ ЗАПИСАНО · <документ> · коммит <sha> · задеты: <документы других закрытых этапов, повторяющие старое решение, или «нет»>».
Результат: статус DONE/BLOCKED/STOPPED, изменённые файлы, проверки,
решения пользователя, следующий этап и точка продолжения.
Перед завершением запиши все решения в файлы и выполни проверки этапа.
Если плагин дал сбой, сразу запиши его в этот чат с наблюдаемым результатом.
Если требуется ответ пользователя, не выдавай этап за завершённый.
```

The parent verifies the report against files/git, marks the row closed or
blocked, and starts the next dependency-ready stage within the agreed scope.
Independent stages can run concurrently only with explicit file ownership.
Ask the user before transitions wherever the stage's skill requires it; do not
silently change an agreed transition rule.

## Context handover and cleanup

At safe item boundaries follow context.md, including exact-thread measurement,
checkpoint files and the no-overlap rule. The host has no agent-callable clear
or compact tool. Saving progress alone does not refresh context.

When agreeing the stage chats, separately offer this optional choice:
«Открывать новые чаты продолжения этих этапов при достижении порога контекста,
после сохранения прогресса? В них план продолжится со следующей задачи».
An explicit yes to this question authorizes only checkpoint continuations of
these stages in this checkout. A yes to the stage list alone does not. Record
the user's answer and scope in the iteration's context-handover.md and include
the actual permission evidence in stage packets; host authorization checks win.
Without this choice continue the authorized work in the same chat using
context.md's automatic fallback; never stop solely to request /compact.

An old stage returns HANDOVER_READY only when an authorized fresh-chat transfer
will actually happen. Otherwise it saves a checkpoint and dispatches the next
action itself, including final checks and whole-run review. The parent must not
turn a context checkpoint into a request for the user to say «продолжай».

When an old stage returns HANDOVER_READY, wait for its turn and all writers to
end, verify its saved checkpoint, then open/reuse its authorized fresh successor
as context.md specifies. Update the existing sessions.md stage ID and sidebar
position, retaining physical old/new IDs in checkout-local runtime metadata. The stage remains open;
HANDOVER_READY is neither DONE nor a reason to start the next pipeline stage.
After compaction or restart read the handover note before creating anything,
so a previously recorded successor is reused rather than duplicated.

Do not archive chats automatically on completion. Use set_thread_archived only
when the user asks for archival, for the selected chats. Keep the parent small:
short status/report packets, files as the source of truth, no copied transcripts.

## Stage-close report and dependency queue

Read [What to offer at a close](offer-at-close.md). A stage sends
`ЭТАП <этап> ЗАКРЫТ · дальше: <этапы, которые можно начать>` or
`ЭТАП <этап> ЗАКРЫТ · ждёт: <этап> после <этап>`.
Verify the close commit, recompute readiness, start all selected ready stages; a waiting
line starts nothing. Keep `после API` on screen specs while API is unclosed; on API close,
`subsessions.py ... mark <API-row> закрыт` prints released rows. No duplicate busy stages.

## What arrives from a stage chat

| Message | Parent action |
|---|---|
| `РЕШЕНИЕ · <было> → <стало> · решил <кто> · владелец: <этап> · жду` | Find the owner's chat, serialize writers, mark «идёт», forward `РЕШЕНИЕ ИЗМЕНЕНО · <было> → <стало> · решил <кто> · от <этап>`. With no owner chat, apply here through its writer. |
| `РЕШЕНИЕ ЗАПИСАНО · <документ> · коммит <sha> · задеты: <документы других закрытых этапов, повторяющие старое решение, или «нет»>` | Verify the commit, mark owner «закрыт», route affected closed documents to their owners, then tell the waiting chat `продолжай: <документ> обновлён, коммит <sha>`. |

Stage responsibility: never edit another stage's document here or start its writer.
Record and send the decision, wait for owner closure, then fix this stage's consequences.
The shared checkout needs no pull. Full protocol and the no-owner fallback:
[Под родительским чатом](decision-changes.md#под-родительским-чатом).
