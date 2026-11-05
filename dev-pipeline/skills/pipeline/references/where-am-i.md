# Where am I

Read when the user asks «где я», «что дальше», «на чём остановились» with no
stage just closed in this sitting, in a fresh session, after a compaction,
and when `continue` runs. Memory of an earlier session is not evidence; the
files on disk and git are.

## Read the state

Run `python3 "<pipeline skill folder>/scripts/where_am_i.py"` from the
project's root and answer from its output. It prints, in this order:

1. **The branch** and whether the tree has uncommitted changes.
2. **The iterations.** The open one (`plans/<version>/` with no
   `summary.md`) and the closed ones. **Two open** — the first thing to do
   is one question: which iteration is current; nothing is stamped or
   committed before the answer. When the older one still has work and the
   newer one is under way in this folder, offer to finish the older one in a
   worktree of its own (`work` → `references/run-hygiene.md` → Finishing an
   older iteration) — never by switching this folder's branch back and forth. **No `plans/`** (a clone still on `main`,
   a project before its first iteration, or one whose files were never pushed): the tags `v<version>` name the
   closed iterations and the `Plan-Unit:` trailers since the last tag the
   units already landed; what stages 10–14 left is in the folder on the iteration branch — enter it first
   (below); still none there → unknown, say so rather than guessing. **An iteration branch the script names** («Итерация …
   открыта по ветке») is the open iteration — a fresh clone, or work
   another person pushed: entering it with the printed `open_iteration.py`
   command comes first, and no version number is asked.
3. **A resume note** — `resume.md` in the open folder means a long run
   (`work`, the UI test run, the security audit) stopped mid-way. Read it
   before anything else and check its claims against git, the tree and
   `docker ps` (`references/pause-and-resume.md` → Picking up); the answer
   is to continue that run from its «Следующий шаг».
4. **Progress files with unfinished rows** — a stage that stopped half
   way (`⏳ ждёт`, `🔄 в работе`, `🔍`, `🔁`, `⛔` rows). A half-done
   stage is not a done one, even when its document exists. Give its line
   with `scripts/progress_link.py` when you name it.
5. **The documents in chain order**, each with its version and gates:
   - business requirements: `grilled:`, else the state its commit names
     («docs: бизнес-требования · допрос: пропущен»); a document `updated:`
     after it was grilled has an unrun grill for its current text;
   - the SRS: its last close commit (empty when nothing was stamped —
     `doc-versioning` → `references/version-birth.md`, step 2) names both
     gates — `прошёл`,
     `пропущен` (the user chose to skip: not offered again), or
     `не запускался` (the session stopped before the question was
     answered: offer it). Commits or uncommitted edits after the stamp are
     named; a grill on them has not run;
   - every other document with a `doc-review` gate: `reviewed:`
     (`info.x-reviewed` on OpenAPI), else the state its stage's close
     commit names (`· review: пропущен`); neither — skipped or never run,
     the files cannot tell, so offer it rather than assume either;
   - **pins**: a pin behind its source with a «ломает» row after it is
     **stale** — that stage comes back first (`doc-versioning` →
     Staleness and cascade); behind by «добавляет» only is for stage 10,
     not a stale stage; «уточняет» only — the next stamp refreshes it;
   - **«написан в итерации …, этап не закрыт»** — the document was
     committed on this iteration's branch and its stage has no close
     commit after it (a new document carries the version from its writer,
     so the close commit, not the number, closes it): its stage stopped
     after the writer (`SKILL.md` → Commit each
     document as soon as it is written), here or on another person's
     machine. That stage is open and resumes: the documents of its set not
     written yet (the architecture's scenarios per area, a screen spec per
     frame), then its gates, then its stamp. A document already committed
     is not written again, and its old pins are refreshed by that stamp,
     not by a rewrite.
6. **The open iteration's checks**: the document-set check (its verdict,
   and whether any file of the set changed after it — then stage 10 has
   not run for the current set), the plan and `plan-review` (verdict, and
   «план изменён после проверки» when the plan changed since — `plan`
   runs the review again before `work`), the units with `Plan-Unit:` on
   the branch, the UI run's and the audit's verdicts (`DEFECTS` / `FIX` —
   a fix plan, `plan` MODE fix).
7. **Готовность этапов** (3–10), while SRS is closed and consistency has not passed:
   ready stages with inputs, missing inputs, neighbouring chats, local unfinished stages and explicit skips.
   Done means the document is on the branch and the stage has a close commit.
8. **Open points in order** — questions for a recipient precede that stage's point.

## The answer

The earliest local unfinished point wins: a resume note, local unfinished progress,
then a local unclosed/stale document. A stage active in a neighbouring chat is named,
never offered as a second local continuation. For branch successors use «Готовность этапов»:
one option for each ready stage; several may be selected together. Missing inputs are named,
including «идёт в соседнем чате» or «написан, этап не закрыт». With nothing ready here,
say where the input is being made, finish, and offer only waiting or stopping.
The default chain table never overrides this block. See [What to offer at a close](offer-at-close.md).

Ask it as one transition, per `pipeline` → "Asking before a transition".
Do not list every remaining stage.

Example — a fresh session, the user asks «что дальше?»; the script printed
(shortened):

```text
Ветка: iteration/1.3.0 · незакоммичено: ничего
Итерации: открыта 1.3.0; закрыты 1.2.0
Документы:
  1. бизнес-требования: допрос 2026-05-02
  2. SRS: 1.3.0 · допрос: прошёл · ревью: прошёл
  3. схема БД: 1.2.0 · ревью: 2026-05-06 · устарел: srs.md@1.2.0, сейчас 1.3.0 — ломает: BR-3: бронь не дольше 4 часов
  4. API (OpenAPI): нет
Открытые пункты (по порядку):
  - устарел документ «схема БД» — этап 3 обновляет его по журналу источника
```

The answer:

```text
**Что дальше: обновить схему базы данных**

В новой версии требований бронь теперь не длиннее 4 часов, а таблицы в
базе построены по прошлой версии: такую длинную бронь база ещё примет.
`db-schema-design` прочитает, что изменилось в SRS после 1.2.0 (правило
BR-3), и обновит схему; без этого API построится на старых таблицах.

  A. Запустить db-schema-design (рекомендую)
  B. Остановиться

Рекомендую A: всё дальше по цепочке опирается на схему.

Ответьте сообщением: буква или свой текст.
```

## Question recipients

Before open points, «Открытые вопросы по адресатам:» contains the same rows as
`open_questions.py --pending`. Blockers get «ответить до следующего этапа»;
each still-ahead recipient gets «вопросы для этапа «<этап>»: N — решить на нём»
before that stage's own point. Read the cited original files; resolved history is hidden.
