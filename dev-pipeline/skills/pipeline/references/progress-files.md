# Progress files

- [Which stages keep one](#which-stages-keep-one)
- [Rules for every file](#rules-for-every-file)
- [Statuses](#statuses)
- [The files](#the-files)

Read this and `references/progress-keeping.md` before a stage that keeps a progress file creates it. A long stage —
one that works through many items of one kind (screens, documents, cases,
units, steps) while the user waits — keeps one, so the user sees where it is
without asking and can tell a slow step from a stuck one.

## Which stages keep one

| Stage | File in `documentation/plans/<version>/` | One row per | Who changes the rows | Title (before «— итерация …») / label |
|---|---|---|---|---|
| `ui-design` — style tiles, drawing, restyle, redraw | `progress-design.md` | screen, plus the direction tiles | the Figma builder as it draws each screen; the session as it verifies | Прогресс макетов / **Макеты** |
| `screen-spec` | `progress-screen-specs.md` | screen | the session, around each dispatch | Прогресс ТЗ на экраны / **ТЗ на экраны** |
| `ui-test-cases` write | `progress-test-cases.md` | section of the case set, plus «Без интерфейса» | the writer, as it finishes each section | Прогресс тест-кейсов / **Тест-кейсы** |
| `ui-test-cases` run | `test-run.md` | case | the runner — `ui-test-cases` → Mode run | Прогресс UI-тестирования / **UI-тестирование** |
| `security-audit` | `security-audit.md` (the report itself) | scanner, area, the verify pass | the session — `security-audit` → `references/report.md` | Аудит безопасности / **Аудит безопасности** |
| `repo-scaffold` | `progress-scaffold.md` | step | the session | Прогресс каркаса проекта / **Каркас** |
| `work` | `progress.md` | unit, then fix | the session — `work` → `references/progress-file.md` | Прогресс выполнения плана / **План** |
| `work` — mutation runs at the close | `progress-mutation.md` | part or share of the run, plus each part not measured | `scripts/progress_mutation.py` from the logs; the survivors section — the session (`work` → `references/health.md` → Progress) | Прогресс мутационной проверки / **Мутации** |
| `deploy-topology` | `progress-deploy.md` | step | the session | Прогресс развёртывания / **Релиз** |

The stages that only ask questions (`grill-me`, `doc-review`,
`docs-consistency`) keep no file: the chat is their progress, and each
question names its place («Замечание 3 из 8»). A stage that writes one
document keeps none, nor does the architecture: one writer settles all its
documents at once, so their rows moved in lockstep and told the user nothing.

## Rules for every file

- **Where.** In the iteration's open folder `documentation/plans/<version>/`,
  in git with the folder (`push_branch.py` commits it). Creating the file writes into
  `plans/`, so a stage that finds no open folder fixes the iteration's
  version first (`pipeline` → Service version) — on a fresh clone or work
  picked up from another person, from the iteration branch `where_am_i.py`
  names (`pipeline` → `references/team.md`).
- **Shape.** The title «Прогресс … — итерация <version>»; right under it
  the bar alone in a ```` ```text ```` block — a hundred cells, `█` done,
  `░` the rest, then the percent, ⌊done × 100 / total⌋ (`work` →
  `references/progress-file.md` → The progress bar); then the count line
  with its label; then the table; under the table one line starting «Состояние:» (only `test-run.md` uses «Verdict:»)
  and ending «обновлено …». The agent writes the state, never the time:
  `progress_link.py` and `progress_set.py` stamp it, including the template’s «…».
- **The page.** Each progress file has its page beside it, the same name
  in `.html` (`progress-screen-specs.md` → `progress-screen-specs.html`):
  the bar drawn as a bar, the count, the status counts — one per row of
  the main table, the first table with a «Статус» column under the file's
  first bar, by the status's words («✅ прошёл: 144») — then the file in
  full. **For the stage files whose rows are documents, screens or steps** —
  design, screen specs, test cases, scaffold, deploy, the
  audit — **the page computes the bar and the count from those rows itself**:
  ✅ and ⏭ whole, 🔍 two thirds, 🔄 and 🔁 a third, ⏳ and ⛔ nothing.
  «Готово» counts only ✅; skips are separate («Готово: 6 из 11 · пропущено 5»).
  A hint under every bar names its measure. The header shows the state on
  its own line with a bold «Состояние:» or «Verdict:». Measured:
  agents changed the rows and left the bar, so these pages stood at 0% through
  whole stages. In those files only the rows matter; their bar line is not
  read. The plan's, the UI run's and the mutation run's bars are kept by their
  scripts, as below; it reloads itself every 5 seconds. The plugin's hook rebuilds the
  page after every Edit or Write of its file, a subagent's included. The
  Markdown file stays the source the agents edit; **the link the user gets
  is always the page**, never the `.md`.
- **The chat line is printed, never written by hand.**
  `python3 "<pipeline skill folder>/scripts/progress_link.py" <the .md>`
  rebuilds the page and prints the one line to paste — the stage's name,
  the count from the file's count line, and the clickable link:

  ```text
  ТЗ на экраны: 5 из 10 · разрывов: design 9 · [progress-screen-specs.html](http://127.0.0.1:8790/progress-screen-specs.html)
  ```

  Codex always starts or reuses the folder's local HTTP server; `--desktop`
  remains compatible. Before printing, the script stamps the file's state and
  rebuilds the page. `--count "<text>"` selects another section's count.
  Paste the line as printed. A subagent does not post it; the session does
  when its dispatch returns. Unknown table statuses and missing «N из M»
  under a bar go to stderr (derived files need no stored count).
- **One set of statuses** in every progress file (below), so the user reads
  every file the same way.
- **A new run** of the same stage in the same iteration rewrites the file.
  It is never committed and never cited by a document. The one exception
  is `security-audit.md`: it is the audit's result as well as its progress,
  so a re-audit updates it in place (`security-audit` →
  `references/report.md`).

## Statuses

Every row of every progress file — a unit, a screen, a document, a
section, a scanner, a fix, a stand — uses only these seven. A stage may add
a short detail after a colon or « · » (`🔄 в работе: печать`), never a new word or emoji. `🔍` names the kind of
check instead of the word «проверка» when it has one: `🔍 ревью`, `🔍 аудит`, `🔍 разбор`:

| Status | Means |
|---|---|
| `⏳ ждёт` | not started |
| `🔄 в работе` | started: dispatched, drawing, writing, running, being fixed |
| `🔍 проверка` (`🔍 ревью`, `🔍 аудит`, `🔍 разбор`) | done by its maker, being checked: the session's inspection, a review, an audit, a triage |
| `✅ готово` | finished and accepted; the bar counts these |
| `🔁 возвращено: <что>` | sent back for rework after a check |
| `⛔ остановлено: <причина>` | cannot go on without a decision or a missing input, or could not run |
| `⏭ пропущено: <почему>` | not needed, out of the run's scope, or moved to the report |

The plan’s e2e section also uses `✅ прошёл` and `⛔ есть падения`.
The other exception is a test case's **outcome** in a UI test run's
`test-run.md`, whose table is the defect report: `✅ прошёл`,
`❌ не прошёл`, `⛔ заблокирован: <причина>`, `⏭ не автоматизирован:
<причина>`, and the triage results (`ui-test-cases` →
`references/run-report.md` → Statuses). While a
case waits or runs it uses `⏳ ждёт` and `🔄 в работе` like any row.

## The files

### `ui-design` — `progress-design.md`

````markdown
# Прогресс макетов — итерация 2.1.0

## Направление

| Вариант | Образец | Статус |
|---|---|---|
| A «Хвойный тихий» | 501:2 | ✅ готово |
| B «Тёплый графит» | — | 🔄 в работе |

Выбор: ждёт ответа

## Экраны

```text
██████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 18%
```

Готово: 2 из 11

| S-n | Экран | Работа | Статус | Кадр |
|---|---|---|---|---|
| S-1 | Вход | редизайн | ✅ готово | 412:10 |
| S-2 | Расписание переговорных | редизайн | ✅ готово | 415:2 |
| S-3 | Мои брони | редизайн | 🔄 в работе | — |
| Общее | Общие состояния | draw | ⏳ ждёт | — |

Состояние: рисует figma-opus, страница «✅ Экраны · «Хвойный тихий»» · обновлено …
````

«Направление» appears only when the visual-direction step runs; its rows
change `⏳ ждёт` → `🔄 в работе` → `✅ готово`, and «Выбор» names the
chosen option. Screen statuses: `⏳ ждёт`, `🔄 в работе`, `✅ готово`
(the builder), `🔁 возвращено: <что>`, `⛔ остановлено: <причина>` (the
session, when its check of a drawn screen fails). «Работа» is the screen's mark
(`новый экран`, `правка`, `редизайн`, `перекраска`, `переименование слоёв`).
The page computes the bar from the rows (The page, above).

### `screen-spec` — `progress-screen-specs.md`

````markdown
# Прогресс ТЗ на экраны — итерация 2.1.0

```text
██████████████████████████████████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 50%
```

Готово: 5 из 10 · разрывов: design 9, API 0, SRS 0

| S-n | Экран | Статус | Элементов | Разрывы |
|---|---|---|---|---|
| S-1 | Вход | ✅ готово | 12 | — |
| S-2 | Расписание переговорных | ✅ готово | 41 | design 6 |
| S-3 | Мои брони | 🔄 в работе | | |
| S-4 | Переговорные | ⏳ ждёт | | |

Состояние: пишет screen-writer S-3 · ревью ТЗ не запускалось · обновлено …
````

Statuses: `⏳ ждёт`, `🔄 в работе` (dispatched), `🔍 проверка` (the
session's inspection), `✅ готово`, `🔁 возвращено: <что>`,
`⛔ остановлено: <причина>`. The state line names the `doc-review` gate
over the set: не запускалось → идёт → its verdict.

### `ui-test-cases` write — `progress-test-cases.md`

````markdown
# Прогресс тест-кейсов — итерация 2.1.0

```text
██████████████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 30%
```

Написано: 3 из 10 разделов · кейсов: 142

| № | Раздел | Файл | Статус | Кейсов |
|---|---|---|---|---|
| 1 | Вход, сессия и выход | 01-login-session.md | ✅ готово | 38 |
| 2 | Расписание переговорных | 02-room-schedule.md | 🔄 в работе | |
| — | Без интерфейса | README.md | ⏳ ждёт | |

Состояние: пишет ui-test-writer · обновлено …
````

Statuses: `⏳ ждёт`, `🔄 в работе`, `✅ готово`. The «Без интерфейса» row
counts the acceptance criteria listed there.

### `repo-scaffold` — `progress-scaffold.md` and `deploy-topology` — `progress-deploy.md`

````markdown
# Прогресс каркаса проекта — итерация 0.1.0

```text
██████████████████████████████████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 50%
```

Сделано: 3 из 6

| Шаг | Что | Статус |
|---|---|---|
| 1 | Папки | ✅ готово |
| 2 | Манифест и инструменты | ✅ готово |
| 3 | Правила границ | ✅ готово |
| 4 | Локальный запуск и схема | 🔄 в работе |
| 5 | Точка входа | ⏳ ждёт |
| 6 | Карта проекта | ⏳ ждёт |

Состояние: шаг 4 · проверка качества не запускалась · обновлено …
````

The rows are the stage's own steps: for `repo-scaffold` its sections 1–6,
for `deploy-topology` use the title «Прогресс развёртывания — итерация <version>»,
label «Релиз», and one row per Step, 1–9 with 7a («Сборка образов»
under Step 8 can run for minutes — its row says so while it runs). Statuses: `⏳ ждёт`,
`🔄 в работе`, `✅ готово`, `⏭ пропущено: <почему>`, `⛔ остановлено:
<причина>`. The state line carries the closing check: the quality gate for
the scaffold, the compose-contract tests and the release folder for the
topology.

### `work` mutation runs — `progress-mutation.md`

````markdown
# Прогресс мутационной проверки — итерация 2.3.0

```text
███████████████████████████████████████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 55%
```

Проверено: 868 из 1562 мутантов · убито 782 · выжило 51 · таймаут 29 · без покрытия 6

| Часть | Что мутируется | Потоки | Статус | Мутантов | Проверено | Убито | Выжило | Таймаут | Без покрытия |
|---|---|---|---|---|---|---|---|---|---|
| Доменные правила | src/domain/booking.ts:40-72 | 4 потока | 🔄 в работе | 412 | 206 | 196 | 9 | 1 | — |
| Защиты на базе · доля 1 | src/guards/a.ts:1-80 | 1 поток · база app_test_mut_1 | 🔍 разбор: таймауты 8% — перегрузка? | 300 | 300 | 255 | 20 | 25 | — |
| Защиты на базе · доля 2 | src/guards/b.ts:1-90 | 1 поток · база app_test_mut_2 | ✅ готово | 310 | 310 | 291 | 12 | 3 | 4 |
| Извлечение текста | — | — | ⏭ пропущено: не измерено — отдельный процесс | — | — | — | — | — | — |

Состояние: идут: Доменные правила · бюджет: 8 потоков из 10 ядер · обновлено …

## Выжившие и эквивалентные

| Мутант | Часть | Решение | Куда | Статус |
|---|---|---|---|---|
| guard.ts:12 `>` → `>=` | Защиты · доля 2 | тест дописать | финальное ревью, F-3 | ⏳ ждёт |
````

Everything above «Выжившие и эквивалентные» is the script's, rewritten from
the logs on each call; the section below is the session's, kept with Edit.
The bar counts the mutants tested. Statuses: `⏳ ждёт`, `🔄 в работе`,
`🔍 разбор: таймауты N%` (the machine was overloaded — `work` →
`references/health.md`), `✅ готово`, `⛔ остановлено: <причина>` (no log,
or a run that ended early), `⏭ пропущено: не измерено — <причина>`.
