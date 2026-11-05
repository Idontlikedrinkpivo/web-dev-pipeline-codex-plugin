# Приёмка 1.3.0 — U27

Статус: **реализация завершена; R PASS; итоговое ревью PASS**. B/L — NOT_RUN,
готовность внешнего выпуска не подтверждена.

## Проверяемое состояние

Проверенный source commit: `38260160232c337050da39806004bd45a06332fb`.
Committed tree: `ba940b2b042d52fe7a54e36824a6c11095131137`.
Общий прогон выполнен на том же содержимом исходников перед его фиксацией;
последующие изменения касаются только отчётов.

- Working source SHA-256 (415 files): `c1a167cb4d8f5721fb5b449a5c00d1bc989ca32193ca40de3004ef6239321553`.
- Case SHA-256 (18 files): `c2b9dd1caf537ea9832c722c11e8be09b857df4401b6742228b3d572ce2c8ac3`.
- Plan SHA-256: `3c081107c66bae16a9c2bb9ac11bc1d8eabfc9a78ac8b924311bbd193a9dee93` (не изменён).
- Python 3.12.13; Git 2.50.1 (Apple Git-155); macOS; local-origin Git fixtures.

Working source hash включает сохранённые пользовательские изменения agent TOML;
они не вошли в наши коммиты. Поэтому committed tree и рабочий source hash — разные
виды свидетельств. AGENTS.md и README.md также сохранены без включения их
пользовательских правок в коммиты реализации.

Рабочий source hash: SHA-256 упорядоченных записей `relative-path NUL
sha256(file-bytes) LF` для обычных файлов `dev-pipeline/` и `tests/`, исключая
`__pycache__`, `.pyc` и `tests/behavior_cases/`. Case hash: тот же алгоритм для
`tests/behavior_cases/*.md`, `plan.md`, `audit-scope.md`, `reflect-supplement.md`
из этого каталога. `acceptance.md` исключён из хеширования во избежание
самоссылки. Фикстуры обезличены; реальные журналы/ID не добавляются.

Среда: временные bare local origin и независимые clones, реальный Git,
`sys.executable`, stdlib unittest, без mock Git/живых app flows/install.
Команда focused run: `PYTHONDONTWRITEBYTECODE=1 python3.12
dev-pipeline/skills/work/scripts/run_check.py u27-handoff-focused -- python3.12
-m unittest discover -s tests -p 'test_handoff_acceptance.py' -v`.
Полный suite выполнен координатором, результат FINAL ниже.

## Журнал свидетельств

| Код | Actual | Evidence |
|---|---|---|
| FULL-1 | Прочитан результат координатора: 238 tests, 3 failures, 235 ok. Все падения — прежнее ожидание английского ключа `design` в localized `show` harness. Общий PASS не получен. | `.git/pipeline-work/checks/final-full-20261105-173814-411200.log` |
| U27-1 | После исправления проверяются registry key/authorized/child ID и канонический title в show; check/work subset также сохранён. 5 tests, 31.244s, OK, exit 0. | `.git/pipeline-work/checks/u27-handoff-focused-20261105-174226-286309.log` |
| RT-1 | Прочитан focused runtime результат: 50 tests, 6.356s, OK. | `.git/pipeline-work/checks/runtime-reflect-focused-20261105-172849-095961.log` |
| FINAL | PASS: 251 tests, 122.458s, OK, exit 0; включает все R-модули, H1/H2/PARTIAL/CONT и регрессии F1–F3. | `.git/pipeline-work/checks/final-fixes-20261105-175912-447519.log` |

Первый запуск run_check не стартовал tests из-за sandbox-запрета записи
журнала; повтор из временного cwd завершился, но исключён из acceptance evidence.
Штатный U27-1 выполнен из checkout после разрешённой эскалации записи журнала.

## Сквозные R-сценарии

Каждый test name ниже существует в `tests/test_handoff_acceptance.py`.

| ID | Expected | Actual / evidence | Ответственный |
|---|---|---|---|
| H1 | A: документы по архитектуру → close/push; designer clone/register → push; A pull/specs → push; user clone выбирает check/work. Переносимые отчёты присутствуют на передачах; полный origin HEAD совпадает. | PASS R U27-1; `test_sequential_human_handoff_through_architecture_mockups_specs_and_user`. Качество документов/Figma не доказывается. | U27; source failures → U2/U3/U5 |
| H2 | SRS → техдоки и дизайнер в независимых clones → combine → specs → user. Общий generated site пересобран из обоих источников. | PASS R U27-1; `test_parallel_human_handoff_rebuilds_generated_conflict_from_combined_sources`. Fixture проверяет Markdown-источники без API; не устанавливает ограничение поддержки OpenAPI. | U27; source failures → U4 |
| H2-SOURCE | Реальный конфликт SRS останавливает отправку; remote/local HEAD, незакоммиченная чужая правка и чистое rebase-состояние сохранены. | PASS R U27-1; `test_parallel_source_conflict_stops_preserving_remote_local_head_and_unowned_edit`. | U4 |
| PARTIAL | Owned staged/unstaged/new binary переносится через clone без sender/local recovery; отчёт/ranges/findings доступны; unowned edit не переносится; повторное restore идемпотентно. | PASS R U27-1; `test_partial_binary_handoff_restores_owned_layers_from_clone_without_sender`. | U2/U27 |
| CONT | Low/full-review/review-fix хранят фазу, следующий шаг, диапазоны, Low batches/findings/attempts; simulated COMPACT record и hook восстанавливают work. | PASS R U27-1; `test_low_and_whole_review_continuation_with_simulated_compaction_hook`. Это не native compaction/живой handover. | U2/U6/U8 |

## Покрытие A01–A34

R ниже означает автоматическую или структурную проверку. FINAL повторил весь
набор после исправлений итогового ревью. Структурный R проверяет текст и
маршрутизацию; поведение агента B требует отдельного наблюдаемого исполнения.
Исторический FULL-1 выше оставлен как журнал устранённого harness-сбоя.

| ID | R evidence / expected | Actual | B/L / недостающая предпосылка |
|---|---|---|---|
| A01 | `test_checkpoint.py`, PARTIAL: слои/bytes/ownership/idempotency | PASS R FINAL | B-CONT NOT_RUN |
| A02 | H1/H2/PARTIAL: portable reports/ranges из clone | PASS R FINAL | B-H1/B-H2/B-CONT NOT_RUN |
| A03 | `test_push_branch.py`: занятый индекс/ошибка commit блокируют push | PASS R FINAL | B-H1 NOT_RUN |
| A04 | H1/H2 + `test_push_branch.py`: подтверждён полный remote OID | PASS R FINAL | B-H1 NOT_RUN |
| A05 | `test_trivy_reports.py`: ровно два полных identity-linked отчёта | PASS R FINAL | L-TRIVY NOT_RUN; нет реальных двух образов |
| A06 | `test_codex_session_sources.py`, `test_sessions_digest.py`: normalized messages без double count | PASS R FINAL | реальные новые rollout не используются |
| A07 | `test_sessions_errors.py`: nested exit codes/unknown/quotes | PASS R FINAL | неизвестность не считается нулём |
| A08 | `test_reflect_windows.py`: contiguous windows/version/offsets | PASS R FINAL | live reflect handoff NOT_RUN |
| A09 | `test_context_size.py`: точный чат, резерв, UNKNOWN | PASS R FINAL | L-COMPACT NOT_RUN |
| A10 | CONT + `test_checkpoint.py`: фазы/ranges/Low/findings | PASS R FINAL | B-CONT NOT_RUN |
| A11 | CONT + `test_keep_rules.py`: durable stage/hook | PASS R FINAL | L-COMPACT NOT_RUN |
| A12 | H1/H2 + `test_subsessions.py`: proposal ≠ authorize, subset/canonical order | PASS R FINAL | L-STAGES NOT_RUN |
| A13 | `test_handoff_contract.py` (структурный), H1/H2 (local origin) | PASS R FINAL | B-H1/B-H2; external push не выполнялся |
| A14 | H2/H2-SOURCE + `test_site_rebase.py`: generated-only rebuild/source stop | PASS R FINAL | B-H2 NOT_RUN |
| A15 | `test_chat_iteration.py`: small identity/trailer/close prerequisites | PASS R FINAL | B малой итерации NOT_RUN |
| A16 | `test_ui_acceptance_scope.py`: increment union/reasons, full evidence fingerprint/invalidations | PASS R FINAL | live UI acceptance NOT_RUN |
| A17 | `test_mutation_budget.py`: обязательный охват/budget/unavailable/cancel | PASS R FINAL | B-R02 NOT_RUN |
| A18 | `test_changed_frames_contract.py` (структурный) | PASS R FINAL | L-FIGMA NOT_RUN |
| A19 | H1/H2 + `test_subsessions.py`: чужой author не фильтрует этап | PASS R FINAL | B-H1/B-H2, L-STAGES NOT_RUN |
| A20 | `test_state_paths.py`: checkout/chat isolation и legacy | PASS R FINAL | live worktree handoff NOT_RUN |
| A21 | `test_client_rule_contracts.py`, `test_data_boundary_rules.py` (структурные) | PASS R FINAL | `client-rules.md`, `data-boundaries.md` NOT_RUN |
| A22 | `test_client_rule_contracts.py` (структурный) | PASS R FINAL | hook-only mutation B NOT_RUN |
| A23 | `test_client_rule_contracts.py` (структурный) | PASS R FINAL | input/output compatibility B NOT_RUN |
| A24 | `test_architecture_policy.py` (структурный) | PASS R FINAL | `architecture-increment.md` NOT_RUN |
| A25 | `test_plan_economy.py`: empty/footprint/micro/advisory | PASS R FINAL | `plan-economy.md` NOT_RUN |
| A26 | `test_packet_policy.py`, `test_document_pointers.py` (структурные) | PASS R FINAL | `packet-policy.md` NOT_RUN |
| A27 | `test_architecture_policy.py` (структурный) | PASS R FINAL | lighter architecture/render B NOT_RUN |
| A28 | `test_codex_session_sources.py`: roots/roles/guard discovery | PASS R FINAL | реальная отсутствующая история не придумана |
| A29 | CONT + `test_checkpoint.py`, `test_reflect_windows.py`: logical events/window boundary | PASS R FINAL | L-COMPACT/B-CONT NOT_RUN |
| A30 | `test_reflect_costs.py`: guardian/unknown/windows/acceptance costs | PASS R FINAL | реальные цены/принятие unknown, не 0 |
| A31 | `test_model_policy.py`, `test_packet_policy.py` (структурные) | PASS R FINAL | paired experiment NOT_RUN; модели не менять |
| A32 | `test_client_rule_contracts.py` (структурный) | PASS R FINAL | version-specific behavior B NOT_RUN |
| A33 | `test_data_boundary_rules.py` (структурный) | PASS R FINAL | retry/error-map B NOT_RUN |
| A34 | `test_architecture_lint.py`, `test_document_pointers.py` | PASS R FINAL | смысловые architecture cases B NOT_RUN |

## Дополнение reflect R01–R03

| ID / связь | Expected | Actual / evidence |
|---|---|---|
| R01 / U8 | После ограничения и checkpoint/compaction следующий dispatch содержит только согласованные mandatory checks/proven regressions. Optional health-2 остаётся в отчёте. | B-R01 NOT_RUN: нужен наблюдаемый следующий пакет агента; `test_work_state_contract.py` доказывает только наличие правил. |
| R02 / U16, U8 | Отмена до dispatch синхронизирует checkpoint/resume/gates/unsent packet; SKIPPED BY USER с причиной, без повторного запуска и без PASS/exhaustion. | PASS R FINAL: `test_mutation_budget.py`, 8 tests, включая `test_user_cancellation_has_reason_uncovered_ranges_and_no_commands` и `test_partial_user_cancellation_preserves_remaining_required_scope`. B-R02 NOT_RUN: агентное продолжение не наблюдалось. |
| R03 / U12 | Pins без stamp блокируют; no-row close со старой version проходит stamp; unstaged body блокирует; принятое решение после stamp блокирует до нового stamp; launch/nonzero неизвестного формата блокируют. Остальные gates действуют. | PASS R FINAL: `test_close_iteration_stamp.py`, 5 tests, включая четыре temp-Git исхода и failure injection для doc_state. Старый installed patch не считается проверкой source. |

## B/L и решение о готовности

Полные шаги, именованные роли, разрешаемые tools, expected и unmet prerequisites:
[`release-handoff.md`](../../../../tests/behavior_cases/release-handoff.md).
Все B/L — NOT_RUN. Для L-STAGES нужны явное разрешение и host tools; для
L-COMPACT — естественно наблюдаемое native compaction; для L-FIGMA — разрешённый
тестовый файл с changed/deleted frames; для L-TRIVY — два образа и Docker/Trivy.
Ни один fixture/static PASS не закрывает эти условия.

Артефакты U27 подготовлены; focused и полный R-набор прошли. Итоговое ревью
закрыто PASS после F1–F3. B/L остаются NOT_RUN. Версия 1.3.0 подготовлена в
исходниках; установленная копия 1.2.266 не обновлялась. Push, merge, tag и
публикация не выполнялись. Завершение реализации не означает READY для выпуска.
