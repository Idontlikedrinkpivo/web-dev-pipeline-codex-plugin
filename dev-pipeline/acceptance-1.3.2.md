# Приёмка исправлений образов Codex 1.3.2

Дата: 2026-11-06. Проверен исходник этого репозитория; Claude-репозиторий использовался только для чтения.

## Изменения

- deploy-topology/assets/nginx: запись только /tmp, динамический resolver и переменная backend, runtime-лимиты,
  FQDN для кластера, проверка CA/имени HTTPS-backend, доверенный X-Forwarded-Proto, закрытые management paths.
  Access log без query, Referer, Location и credential headers. Новый статический runtime.go преобразует
  native stderr в JSON-категории без исходного текста и переводит TERM/INT в graceful QUIT мастера nginx.
  Рабочие процессы ограничены 25 секундами, аварийный предел адаптера — 28 секунд, ошибка не скрывается кодом 0.
- images.md, compose-shape.md, deploy-doc.md, env-and-config-contract.md и SKILL.md: образ с оболочкой рекомендуется
  вариантом B; shellless требует runtime-монтирования всего conf.d. Полный dockerignore, версия/commit в ENV,
  тесты вне dist, обновление баз на каждом выпуске, worker heartbeat, heap/pool budgets, масштабирование,
  пути/объём записи, сборка, DBA/миграции и отдельные артефакты build/scan. Tar и формат тегов сохранены.
- image_preflight.py: export без shell, состав образа/CDN/upstream, изолированный случайный Compose-проект,
  UID 5000, read-only/tmpfs, DB-down/restart/recovery, frontend без DNS backend и после пересоздания,
  защищённые management URLs при здоровом backend, тихие успешные пробы, метрики, секреты, остановка.
  Ошибки 5xx остаются в логах. Чужие проекты/volumes и writable host mounts не используются.
- trivy_images.py и trivy_reports.py: точные локальные образы, vuln+secret всех уровней, image-config secrets,
  свежие раздельные отчёты и строгая идентичность. Секрет блокирует всегда; CRITICAL — до исправления или
  явного принятого риска с digest/CVE/пакетом/целью/согласовавшим/датами. Из отчётов убираются secret excerpts.
  Старый валидатор дополнен реальным Metadata.ImageID; конфликт идентификаторов остаётся ошибкой.
- FastAPI/Fastify, scaffold, архитектура, frontend: секреты, первый администратор из Secret, интеграции/TLS/CA,
  proxy/base URL, docs off, внешнее состояние/locks, app_build_info и pool metrics, запрет CDN.
  Fastify обрабатывает idle pool error и не пишет query в стандартной 404-диагностике.
- env_files.py: check обнаруживает ручную правку несекретных значений/комментариев; секреты при генерации сохраняются.
- upgrade-docs: шесть записей 1.3.2; files_match проверяет каждый компонент, чтобы новый образ не скрывал старый.
- README и plugin.json: независимая версия Codex 1.3.2. Изменения старых задач сохранены отдельно.

## Выполнено

| Проверка | Результат |
|---|---|
| python3.12 -m unittest discover -s tests -v | 307 тестов, 124.174 с, OK |
| check_plugin.py | 0 замечаний; SKILL.md не более 500 строк (deploy-topology — 487) |
| git diff --check | Без замечаний |
| tests/live_image_acceptance.py | Все сценарии прошли на linux/arm64, Docker Desktop 29.2.1 |
| Состав готовых образов через export | Хорошие прошли, лишний .md и статический upstream отклонены |
| Изолированный preflight stand | UID 5000, read-only, только /tmp; DB-down 200/503, restart/recovery; секреты: пустой/короткий/заглушка; exit 0 |
| Отрицательные стенды | Успешные пробы в логах и статический upstream отклонены |
| nginx/backend | Старт без backend; появление; пересоздание с принудительно другим IP без рестарта frontend |
| Runtime лимиты | 1k → 413; тот же образ с 4k → 200; backend timeout 1s → 504; CLIENT_TIMEOUT 2s на незаконченных заголовках |
| Остановка nginx | SIGTERM во время трёхсекундного запроса: клиент получил 200, контейнер завершился 0 |
| Логи nginx | Все строки JSON; тестовый token из query отсутствует и в access, и в диагностике |
| Runtime adapter | Собран Go 1.27.3 (официальный архив с проверенным SHA-256) для linux/arm64 и linux/amd64; arm64 выполнен в контейнере |
| tests/live_service_examples.py | Реальные фрагменты FastAPI/Fastify исполнены как процессы с временной PostgreSQL 16 |
| FastAPI и Fastify | service_check, health/Prometheus/JSON/request_id/SIGTERM; build/pool metrics, docs 404, safe query logs, DB outage/restart/recovery, SIGINT 0 |
| Реальный Trivy 0.67.2 | Два локальных базовых образа: HIGH 60, CRITICAL 0, секретов 0; полный runner завершился 0 |
| Скан-гейт на фикстурах | Секреты всех пяти уровней блокируют; CRITICAL без риска/не тот digest/истёкший риск блокируют; пустой/чужой отчёт не проходит |
| Обновление проектов | Старые и новые nginx/документы/образы, включая смесь старого и нового компонента; ручной env drift и сохранение секрета |

Для процессов использовались FastAPI 0.162.0, uvicorn 0.54.0, SQLAlchemy 2.1.8 с asyncio extra и asyncpg 0.32.0;
Fastify 5.12.8, prom-client 15.1.3 и pg 8.23.1 установлены во временной папке. Это проверка примеров, не обновление
зависимостей какого-либо пользовательского проекта.

## Ограничения доказательств

Не запускались: shellless-образ; реальные backend Docker-образы FastAPI/Fastify; linux/amd64 frontend-контейнер;
HTTPS-backend с валидным/невалидным CA и проверка proxy allowlist на живом ingress; Kubernetes/Helm;
параллельные миграции конкретного приложения, нагрузочные замеры, фоновые worker/scheduler.
Настройки и требования для них добавлены, но живой успех им не приписывается.

Trivy сканировал кешированные базы python:3.12-slim и nginx-unprivileged, а не релиз приложения. 60 HIGH
остаются находками; это не утверждение, что базы готовы к production. Положительная секретная находка
проверена фикстурой отчёта, не настоящим секретом. Обновление старого пользовательского проекта не выполнялось.

Обнаруженные при живых проверках ошибки исправлены: WORKDIR=/ у nginx; изменение случайного опубликованного
порта после рестарта Docker; Metadata.ImageID вместо ArtifactID в Trivy; query в стандартном 404-логе Fastify.
Чужие рабочие изменения не отменялись. Установленная копия плагина и удалённый Git не менялись.
