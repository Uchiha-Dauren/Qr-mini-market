# Полный исходный код QR Mini-Market

Все текстовые файлы проекта приведены целиком. Изображения находятся в соответствующих каталогах архива.

.dockerignore

````text
.git
.venv
venv
__pycache__
**/__pycache__
*.py[cod]
.pytest_cache
.ruff_cache
.coverage
.coverage.*
htmlcov
.env
.env.*
**/.env
**/.env.*
*.db
*.db-*
*.sqlite
*.sqlite-*
*.sqlite3
*.sqlite3-*
**/*.db
**/*.db-*
**/*.sqlite*
*.zip
*.log
.DS_Store
.idea
.vscode
build
dist
````

.env.example

````text
# Shop settings. Run commands from the repository root.
# Allowed values: development, test, production.
# Production enables secure cookies and therefore requires HTTPS.
APP_ENV=development
DATABASE_URL=sqlite:///./shop.db
CURRENCY=KZT
TIMEZONE=Asia/Almaty
PAYMENT_PROVIDER=mock_bank
PAYMENT_TTL_SECONDS=300
PAYMENT_EXPIRY_GRACE_SECONDS=30

# Server-to-server address; this is not the URL encoded into the QR code.
BANK_BASE_URL=http://127.0.0.1:8001

# Required secrets: generate each value separately; use at least 32 characters.
# The merchant API key and webhook secret must match in both services.
BANK_MERCHANT_API_KEY=
WEBHOOK_SECRET=
SECRET_KEY=
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Mock Bank settings, validated independently by the bank.
BANK_DATABASE_URL=sqlite:///./mock_bank.db

# Replace 127.0.0.1 with the computer's LAN IP before testing from a phone.
# This address is used in the QR payment link.
BANK_PUBLIC_URL=http://127.0.0.1:8001
SHOP_WEBHOOK_URL=http://127.0.0.1:8000/api/v1/webhooks/mock-bank
MERCHANT_NAME="Учебный мини-маркет"
````

.gitignore

````text
# Local configuration and credentials.
.env
.env.*
!.env.example

# Virtual environments and Python caches.
.venv/
venv/
__pycache__/
*.py[cod]
*.egg-info/
build/
dist/

# Test, coverage, and lint output.
.pytest_cache/
.ruff_cache/
.coverage
.coverage.*
coverage.xml
htmlcov/

# Local databases, including SQLite sidecar files.
*.db
*.db-*
*.sqlite
*.sqlite-*
*.sqlite3
*.sqlite3-*

# Local editor and operating system files.
.idea/
.vscode/
.DS_Store
Thumbs.db
*.log
````

Dockerfile

````text
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 market \
    && useradd --uid 10001 --gid 10001 --create-home market \
    && mkdir -p /data \
    && chown market:market /data

COPY app/ ./app/
COPY mock_bank/ ./mock_bank/
COPY migrations/ ./migrations/
COPY alembic.ini ./
COPY scripts/docker-entrypoint.sh ./scripts/docker-entrypoint.sh

RUN chmod 0555 /app/scripts/docker-entrypoint.sh

USER 10001:10001

EXPOSE 8000 8001

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD ["shop"]
````

README.md

````markdown
# QR Mini-Market

Готовый учебный мини-маркет: каталог, касса, экран покупателя, QR-оплата через отдельный Mock Bank, печатный чек, админка и отчёты. Русский интерфейс работает без CDN. Реальные деньги и данные карт не используются; чек не является фискальным документом.

Стек: Python 3.11+, FastAPI, SQLAlchemy 2, Pydantic 2, Alembic, SQLite/WAL, Jinja2 и обычный JavaScript. Проверенное окружение — Linux / Python 3.12.14. Версии прямых зависимостей закреплены в requirements. Оба сервиса запускаются отдельно и общаются только по HTTP. Полные тексты файлов собраны также в [docs/SOURCE_CODE.md](docs/SOURCE_CODE.md), без сокращений.

## Быстрый старт — Windows PowerShell

Все команды выполняйте из распакованной папки `qr-mini-market`.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m app.setup_env
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.seed
.\.venv\Scripts\python.exe -m mock_bank.seed
.\.venv\Scripts\python.exe -m app.create_user --username admin --role ADMIN
```

Введите собственный пароль дважды: 12–128 символов. Для отдельного кассира повторите команду с `--username cashier --role CASHIER`.

Первый терминал — банк:

```powershell
.\.venv\Scripts\python.exe -m uvicorn mock_bank.main:app --host 0.0.0.0 --port 8001 --no-access-log
```

Второй терминал — магазин:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

## Быстрый старт — Linux / macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m app.setup_env
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m app.seed
.venv/bin/python -m mock_bank.seed
.venv/bin/python -m app.create_user --username admin --role ADMIN
```

В первом терминале:

```bash
.venv/bin/python -m uvicorn mock_bank.main:app --host 0.0.0.0 --port 8001 --no-access-log
```

Во втором терминале:

```bash
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

`app.setup_env` создаёт `.env` с тремя независимыми случайными секретами и не заменяет существующий файл. Если `.env` был создан ранее из шаблона с пустыми полями, заполните секреты в нём самостоятельно. Пользователей по умолчанию нет. Повторный seed добавляет недостающие демо-записи, сохраняет изменённые цены, остатки и банковские балансы.

Откройте:

| Страница | Назначение |
| --- | --- |
| [Касса](http://127.0.0.1:8000/cashier) | Вход, сканирование, поиск, чек и QR |
| [Экран покупателя](http://127.0.0.1:8000/display/main) | Текущий чек терминала `main`, QR и результат |
| [Проверка цены](http://127.0.0.1:8000/price-check) | Публичный поиск без создания чека |
| [Админка](http://127.0.0.1:8000/admin) | Каталог, остатки и отчёты; роль ADMIN |
| [Магазин: health](http://127.0.0.1:8000/health) | Доступность БД магазина |
| [Банк: health](http://127.0.0.1:8001/health) | Доступность БД банка |

Остановка — Ctrl+C в обоих терминалах. Данные остаются в SQLite-файлах. `/health` проверяет соединение с БД, но не полноту миграций или доступность другого сервиса.

## Демо-сценарий

1. Войдите на кассу созданным пользователем и откройте `/display/main` во второй вкладке.
2. Добавьте три штучных товара и один весовой. Для весового товара укажите целые граммы, например 350. Поиск поддерживает кириллицу без учёта регистра; сканер вводит EAN и Enter.
3. Нажмите «К оплате». На экране покупателя появятся QR и серверный таймер. В development также доступна текстовая ссылка на банк.
4. Откройте ссылку, выберите Айдоса и оплатите. Через очередной опрос интерфейс покажет оплату; доступен печатный чек. Товар списан один раз, резерв снят.
5. Создайте чек дороже 1 000 ₸ и выберите Алию. Получите отказ из-за нехватки денег; чек снова можно изменить и оплатить.
6. Для проверки истечения поставьте `PAYMENT_TTL_SECONDS=30` в `.env`, перезапустите магазин и создайте новый QR. Банк завершит счёт как EXPIRED; магазин снимет резерв после подтверждения банка.
7. Отмена платежа возвращает чек в OPEN. Отмена всего чека закрывает его как CANCELLED.

Seed содержит 27 категорий и 47 товаров, включая весовые, товары с малым остатком и один неактивный. Демо-счета: Айдос — 500 000 ₸, Алия — 1 000 ₸, Дана — 0 ₸. Их балансы меняются при оплате и не сбрасываются повторным seed.

## Docker Compose

Создайте `.env` командой `python -m app.setup_env` (нужен только Python, зависимости для этой команды не требуются). Затем:

```bash
docker compose up --build -d
docker compose exec shop python -m app.create_user --username admin --role ADMIN
docker compose ps
docker compose logs -f
```

Команды одинаковы в PowerShell и Bash. Контейнер магазина выполняет миграции и seed перед запуском; контейнер банка создаёт свою схему и seed. Контейнеры работают от UID 10001, хранят БД в раздельных именованных томах `shop_data` и `bank_data`.

```bash
docker compose down
```

Остановка сохраняет тома. Dockerfile, Compose, healthchecks и entrypoint подготовлены и статически проверены; образ в проверочном окружении не собирался, поскольку Docker там отсутствует. При первом запуске нужен доступ к реестру образов и Python-пакетам.

## Телефон и локальная сеть

Телефон и компьютер должны находиться в одной локальной сети. Найдите IPv4 компьютера (`ipconfig` в Windows, настройки сети в macOS/Linux). Укажите, например, `BANK_PUBLIC_URL=http://192.168.1.50:8001` в `.env` и перезапустите банк. QR нового счёта будет вести на этот адрес.

На телефоне экран покупателя открывается как `http://192.168.1.50:8000/display/main`. `127.0.0.1` на телефоне означает сам телефон. В брандмауэре Windows разрешите входящие TCP 8000 и 8001 для частной сети. Изоляция клиентов гостевого Wi-Fi может мешать соединению.

`BANK_BASE_URL` — адрес банка для сервера магазина. При обычном локальном запуске оставьте localhost; Compose сам задаёт `http://mock_bank:8001`. `SHOP_WEBHOOK_URL` нужен банку для обратного запроса; Compose задаёт `http://shop:8000/api/v1/webhooks/mock-bank`. `BANK_PUBLIC_URL` всегда должен быть доступен браузеру покупателя.

## Конфигурация

`.env` читается из корня проекта; переменные процесса имеют приоритет. После изменений перезапустите соответствующий сервис.

| Переменная | По умолчанию / назначение |
| --- | --- |
| `APP_ENV` | `development`; также `test`, `production` |
| `DATABASE_URL` | `sqlite:///./shop.db` |
| `BANK_DATABASE_URL` | В шаблоне `sqlite:///./mock_bank.db` |
| `CURRENCY` | Только `KZT` |
| `TIMEZONE` | `Asia/Almaty`; даты в БД всегда UTC |
| `PAYMENT_PROVIDER` | `mock_bank`; FakeProvider внедряется только в тестах |
| `PAYMENT_TTL_SECONDS` | 300; диапазон 1–86400 |
| `PAYMENT_EXPIRY_GRACE_SECONDS` | 30; неотрицательное целое |
| `BANK_BASE_URL` | `http://127.0.0.1:8001`; HTTP(S) origin без credentials |
| `BANK_PUBLIC_URL` | Адрес в QR, обычно localhost или LAN IP |
| `SHOP_WEBHOOK_URL` | `http://127.0.0.1:8000/api/v1/webhooks/mock-bank` |
| `BANK_MERCHANT_API_KEY` | Обязательный ключ merchant API, одинаковый в сервисах |
| `WEBHOOK_SECRET` | Обязательный общий HMAC-секрет |
| `SECRET_KEY` | Обязательный отдельный ключ JWT магазина |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 60; положительное число минут |
| `MERCHANT_NAME` | Название магазина на странице банка |

Каждый секрет — минимум 32 символа без пробелов и значений-заглушек. Генератор использует 48 случайных байтов на значение. Секреты не включены в архив. В `production` cookie получает Secure, поэтому веб-вход требует HTTPS. Compose рассчитан на локальную демонстрацию; TLS-прокси нужно настраивать отдельно.

## API и права

Все бизнес-маршруты магазина имеют префикс `/api/v1`. `{id}` — UUID `public_id`, не внутренний Integer. Списки используют `{items, total, limit, offset}`, limit 1–100. Машиночитаемая схема доступна на `/openapi.json`; Swagger/ReDoc отключены, CDN не нужны.

| Метод и путь после `/api/v1` | Доступ | Назначение |
| --- | --- | --- |
| `POST /auth/login` | Публичный | JSON username/password, JWT и cookies |
| `GET /auth/me`, `POST /auth/logout` | Пользователь | Текущий профиль, выход |
| `GET /categories` | CASHIER/ADMIN | Категории |
| `POST /categories`, `PATCH/DELETE /categories/{id}` | ADMIN | Создание, изменение, деактивация |
| `GET /products`, `GET /products/{id}` | CASHIER/ADMIN | Каталог и карточка |
| `GET /products/by-barcode/{barcode}` | CASHIER/ADMIN | Точный поиск EAN |
| `POST /products`, `PATCH/DELETE /products/{id}` | ADMIN | Создание, изменение, мягкое удаление |
| `POST /products/{id}/stock-adjustments` | ADMIN | `{delta, reason: RESTOCK или ADJUSTMENT}` |
| `POST /orders`, `GET /orders`, `GET /orders/{id}` | CASHIER/ADMIN | Создание, список и чек |
| `POST /orders/{id}/items` | CASHIER/ADMIN | `{barcode или product_id, quantity}` |
| `PATCH/DELETE /orders/{id}/items/{item_id}` | CASHIER/ADMIN | Изменение quantity, удаление |
| `POST /orders/{id}/checkout` | CASHIER/ADMIN | Резерв и счёт банка |
| `POST /orders/{id}/cancel` | CASHIER/ADMIN | Отмена чека через отмену банка |
| `GET /orders/{id}/receipt` | CASHIER/ADMIN | Снимок оплаченного чека |
| `GET /payments/{id}`, `GET /payments/{id}/qr.png` | Публичный UUID | Статус и QR |
| `POST /payments/{id}/refresh`, `POST /payments/{id}/cancel` | CASHIER/ADMIN | Сверка, отмена |
| `POST /webhooks/mock-bank` | Подпись HMAC | Уведомление банка |
| `GET /public/products`, `GET /public/categories` | Публичный | Активный каталог, наличие без точных остатков |
| `GET /public/terminals/{terminal_code}/display` | Публичный | Текущий чек, QR, таймер и результат |
| `GET /reports/sales` | ADMIN | Продажи по дням, категориям, товарам |
| `GET /reports/low-stock` | ADMIN | Малый доступный остаток |
| `GET /reports/payments-needing-review` | ADMIN | Платежи с needs_review |

`GET /products` принимает `q`, `barcode`, `category_id`, `include_subcategories`, `is_active`, `limit`, `offset`. Без `is_active` авторизованный API возвращает и неактивные товары; публичный — только доступные. `GET /orders` фильтруется по `terminal_code` и `status`. Отчёт продаж принимает `date_from`, `date_to` включительно, не более 366 дней; без дат используется период с начала текущего месяца по текущую локальную дату.

Банк имеет собственный origin:

| Метод и путь банка | Доступ |
| --- | --- |
| `POST /api/merchant/invoices` | Bearer BANK_MERCHANT_API_KEY; идемпотентно по merchant_reference |
| `GET /api/merchant/invoices/{id}` | Merchant Bearer |
| `POST /api/merchant/invoices/{id}/cancel` | Merchant Bearer |
| `GET /pay/{token}` | Страница покупателя |
| `GET /api/pay/{token}` | Счёт и выбор демо-счёта |
| `POST /api/pay/{token}` | Оплата, JSON `{account_id: UUID}` |
| `POST /api/pay/{token}/cancel`, `/decline` | Отмена / имитация отказа |
| `GET /health` | Проверка соединения с БД |

Ошибки магазина: `{"error":{"code":"INSUFFICIENT_STOCK","message":"...","details":{}}}`. Невалидные данные — 422, доступ — 401/403, отсутствие — 404, конфликт — 409, истёкший QR — 410, недоступный банк — 503. Валидационные и неожиданные ошибки не раскрывают входные секреты.

API-клиент передаёт `Authorization: Bearer <access_token>`. Браузер использует HttpOnly-cookie и заголовок `X-CSRF-Token` из cookie `csrf_token` для POST/PATCH/DELETE. JWT проверяет issuer, audience, подпись и срок; роль и активность пользователя каждый раз читаются из БД. Logout удаляет cookies; ранее полученный bearer остаётся действителен до истечения или деактивации пользователя.

## Денежные расчёты и данные

- Денежные значения — целые тиыны, 1 ₸ = 100 тиынов. Цена PIECE — за штуку, KG — за килограмм; quantity KG — целые граммы.
- PIECE: `price_minor * quantity`. KG: `(price_minor * quantity + 500) // 1000`. Округляется вся позиция один раз, половина тиына вверх.
- Повторный скан увеличивает общую quantity и пересчитывает позицию по снимку цены. Изменение каталога не меняет старые чеки.
- Нулевые цены допустимы, но оплатить нулевой чек нельзя. Цены и итоги API ограничены `2**53 - 1` тиынов для точной передачи JSON в браузер; БД использует BigInteger. Итоги отчётов дополнительно передаются точной строкой `revenue_minor_text`.
- Количества ограничены `2**31 - 1`. БД запрещает отрицательный остаток, резерв больше остатка и дробные количества. Корректировка не может уменьшить запас ниже резерва.
- Единица товара после создания неизменяема. Деактивация категории скрывает товары её потомков, сохраняя историю. Категории нельзя переместить в собственное поддерево.
- EAN-8/EAN-13 проверяются по контрольной цифре. Демо-коды: `200` + 9 цифр номера + контрольная цифра. Это внутренние учебные коды.
- В OrderItem сохраняются название, EAN, единица, цена и итог. Категория в отчёте берётся из текущего каталога: снимок категории в модель не входит.

## Платёж и восстановление после сбоев

Checkout работает в три фазы: короткая транзакция резервирует все позиции и создаёт PENDING-платёж; HTTP-запрос создаёт счёт банка; отдельная транзакция сохраняет ответ. При нехватке одной позиции вся первая фаза откатывается. На терминале допускается один OPEN/PENDING_PAYMENT-чек, на чеке — один PENDING-платёж; ограничения продублированы частичными уникальными индексами.

Повторный checkout возвращает тот же платёж. Для создания счёта сохраняется аренда на 30 секунд, поэтому параллельные запросы не создают несколько исходящих попыток. Пока другой запрос получает счёт, `pay_url` может быть null; интерфейс продолжает опрос. HTTP timeout — 10 секунд.

Доказанный отказ соединения при первой попытке позволяет снять резерв и вернуть чек в OPEN. Timeout, потерянный ответ или повторная попытка после неопределённого исхода сохраняют PENDING и резерв. Восстановление использует тот же merchant_reference. Нельзя освобождать товар только потому, что магазин не получил ответ: банк уже мог принять платёж.

Банк сохраняет финальный статус, списание, bank_transaction и стабильный event_id в одной транзакции. Доставка webhook начинается после commit. События и попытки доставки сохраняются в БД; первая попытка сразу, затем повторы через 1, 5 и 25 секунд при сети/5xx. Постоянные 4xx и redirects прекращают доставку. После исчерпания повторов магазин всё ещё может сверить итог через merchant API.

HMAC-SHA256 считается по `timestamp + "." + raw_body`; допустимое отклонение времени — 300 секунд. Невалидная подпись не создаёт PaymentEvent. Валидное событие и его влияние на платёж, чек, резерв и журнал фиксируются вместе. Дубли не списывают товар повторно. Раннее уведомление до сохранения invoice_id ждёт привязки счёта. Неверные данные сохраняются для разбора, возвращают 422 и не подтверждают оплату.

Отмена сначала выполняется в банке. Если банк уже получил деньги, магазин подтверждает продажу и возвращает ALREADY_PAID. Истечение также сверяется с банком; локальный таймер не меняет статус самостоятельно. Фоновая задача каждые примерно 15 секунд проверяет просроченные PENDING после grace-периода и незавершённое создание счетов. Кнопка «Проверить оплату» выполняет ту же сверку сразу.

Поздний успешный результат для локального FAILED/EXPIRED/CANCELLED помечается `needs_review`, `review_reason=late_success`; история не переписывается. Автоматического возврата денег нет: администратор видит запись в отчёте и разбирает её вручную.

## Архитектура

```mermaid
flowchart TD
    C[Кассир] --> S[Shop FastAPI]
    D[Экран покупателя] --> S
    S --> DB[(Shop SQLite)]
    S -->|Merchant API| B[Mock Bank]
    P[Телефон покупателя] --> B
    B --> BB[(Bank SQLite)]
    B -->|Подписанный webhook| S
```

```mermaid
sequenceDiagram
    participant C as Кассир
    participant S as Магазин
    participant B as Банк
    participant P as Покупатель
    C->>S: Checkout
    S->>S: Резерв и PENDING, commit
    S->>B: Создать счёт по reference
    B-->>S: Invoice и pay_url
    S->>S: Привязка счёта, commit
    S-->>C: QR
    P->>B: Оплатить
    B->>B: Списание и событие, commit
    B->>S: HMAC webhook
    S->>S: PAID, SALE и снятие резерва, commit
    S-->>B: Принято
    C->>S: Опрос статуса
    S-->>C: Оплачено
```

ER-диаграмма магазина (bank-модели находятся в отдельной БД):

```mermaid
erDiagram
    CATEGORY ||--o{ CATEGORY : parent
    CATEGORY ||--o{ PRODUCT : contains
    USER ||--o{ ORDER : creates
    ORDER ||--o{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : snapshot
    ORDER ||--o{ PAYMENT : attempts
    PAYMENT ||--o{ PAYMENT_EVENT : receives
    PRODUCT ||--o{ STOCK_MOVEMENT : ledger
    ORDER o|--o{ STOCK_MOVEMENT : sale
```

```mermaid
stateDiagram-v2
    [*] --> OPEN
    OPEN --> PENDING_PAYMENT: Checkout
    OPEN --> CANCELLED: Отмена чека
    PENDING_PAYMENT --> PAID: Банк подтвердил оплату
    PENDING_PAYMENT --> OPEN: Отказ, истечение или отмена платежа
    PAID --> [*]
    CANCELLED --> [*]
```

| Платёж | Разрешённый следующий статус | Результат |
| --- | --- | --- |
| PENDING | SUCCEEDED | Чек PAID, stock и reserve уменьшаются, SALE |
| PENDING | FAILED / EXPIRED / CANCELLED | Чек OPEN, reserve снимается |
| SUCCEEDED | Нет | Дубликаты без повторного эффекта |
| FAILED / EXPIRED / CANCELLED | Нет | Поздняя оплата отправляется на разбор |

Основные каталоги: `app/core` — настройки/деньги/EAN; `app/db` — транзакции и UTC; `app/models`, `schemas`, `services`, `routers`; `app/providers` — контракт банка; `app/templates`, `static` — UI; `mock_bank` — автономный банк; `migrations` — схема магазина; `tests` — unit, integration и e2e.

## Проверки

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --cov=app.services --cov=mock_bank.service --cov=mock_bank.notifier --cov-report=term-missing --cov-fail-under=80
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m alembic check
```

Linux / macOS:

```bash
.venv/bin/python -m pytest -q --cov=app.services --cov=mock_bank.service --cov=mock_bank.notifier --cov-report=term-missing --cov-fail-under=80
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m alembic check
```

Тесты используют временные БД и собственные настройки; заполненный `.env` и работающие серверы им не нужны. `alembic check` требует настроенной и обновлённой рабочей БД. Актуальный протокол выполненных проверок — [docs/VERIFICATION.md](docs/VERIFICATION.md). Известное предупреждение Starlette связано с использованием требуемого httpx в TestClient; оно не скрыто фильтром.

Проверяются расчёт веса, EAN, ограничения схемы и миграции, кириллический поиск, снимки цен, конкуренция за последнюю единицу, одновременный checkout, атомарный rollback, HMAC и повторы, потерянный ответ банка, ранний webhook, неверные суммы и поздний успех, роли/CSRF, отчёты и полный HTTP-сценарий двух сервисов.

## Миграции, эксплуатация и ограничения

Магазин создаёт таблицы через `alembic upgrade head`; head — `0002_commerce`. Применённые миграции не редактируйте. `downgrade base` удаляет данные и не нужен для запуска. Проверены upgrade/downgrade/re-upgrade и соответствие metadata. Банк использует собственный `create_all` для первоначальной схемы демо; изменение уже установленной схемы банка потребует отдельной миграции.

SQLite: foreign_keys ON, WAL, busy_timeout 5000, явные транзакции. Записи используют BEGIN IMMEDIATE с ограниченными повторами при блокировке. HTTP никогда не выполняется внутри бизнес-транзакции. В PostgreSQL используются условные UPDATE, row locks и повторы serialization/deadlock; SQL миграций скомпилирован offline. PostgreSQL-сервер не тестировался; для него отдельно установите `psycopg[binary]` и используйте `postgresql+psycopg://...`.

Логи показывают переходы, ошибки провайдера и отклонённые подписи без Authorization, паролей и секретов. Команды запуска отключают access log, чтобы платёжные URL не попадали в обычный журнал запросов. SQL/traceback с исходными параметрами клиенту не выдаются.

Это демонстрация одного магазина: без фискализации, реального эквайринга, возвратов, многопользовательской изоляции магазинов, восстановления паролей и управляемого TLS. ADMIN и CASHIER работают с общими чеками магазина; публичный terminal_code открывает экран покупателя по замыслу. UUID платежа и ссылка банка дают доступ к публичному демо-счёту. JWT не имеет отдельного списка отзыва. CORS выключен; страницы магазина используют CSP, Jinja autoescape и textContent.

Следующие возможные улучшения: миграции банка, тестовый PostgreSQL в CI, управляемые возвраты, лимиты попыток входа, мониторинг очереди уведомлений и резервное копирование. Перед копированием SQLite на работающей системе используйте штатный backup SQLite либо остановите оба сервиса; один основной файл без WAL может быть неполным.

Сообщение коммита: `feat: complete QR mini-market checkout, bank emulator, web UI and reports`.
````

alembic.ini

````text
[alembic]
script_location = %(here)s/migrations
prepend_sys_path = %(here)s
path_separator = os
output_encoding = utf-8

# The database URL comes from application settings, never from this file.

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console
qualname =

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
````

app/__init__.py

````python
"""QR Mini-Market shop application."""
````

app/core/__init__.py

````python
"""Configuration and shared shop rules."""
````

app/core/barcodes.py

````python
"""Validate EAN syntax and checksums; generate local demo identifiers."""


def calculate_ean_check_digit(body: str) -> str:
    """Calculate GS1 modulo-10 for an EAN-8 or EAN-13 body without its last digit."""
    if (
        not isinstance(body, str)
        or len(body) not in (7, 12)
        or not body.isascii()
        or not body.isdigit()
    ):
        raise ValueError("EAN body must contain exactly 7 or 12 ASCII digits")
    total = sum(int(digit) * (3 if index % 2 == 0 else 1) for index, digit in enumerate(body[::-1]))
    return str(-total % 10)


def validate_ean(barcode: str) -> str:
    """Return an unchanged valid EAN; this does not verify registration or ownership."""
    if (
        not isinstance(barcode, str)
        or len(barcode) not in (8, 13)
        or not barcode.isascii()
        or not barcode.isdigit()
    ):
        raise ValueError("EAN must contain exactly 8 or 13 ASCII digits")
    if barcode[-1] != calculate_ean_check_digit(barcode[:-1]):
        raise ValueError("EAN check digit is invalid")
    return barcode


def generate_internal_ean13(sequence: int) -> str:
    """Create a deterministic demo EAN-13; callers own sequence uniqueness."""
    if type(sequence) is not int or not 1 <= sequence <= 999_999_999:
        raise ValueError("EAN sequence must be an integer between 1 and 999999999")
    body = f"200{sequence:09d}"
    return body + calculate_ean_check_digit(body)
````

app/core/config.py

````python
"""Load and validate the shop configuration without import-time side effects."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Shop settings; bank-only environment entries are intentionally ignored."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        hide_input_in_errors=True,
        frozen=True,
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = Field(default="sqlite:///./shop.db", min_length=1, repr=False)
    currency: Literal["KZT"] = "KZT"
    timezone: str = "Asia/Almaty"
    payment_provider: Literal["mock_bank"] = "mock_bank"
    payment_ttl_seconds: int = Field(default=300, gt=0, le=86400)
    payment_expiry_grace_seconds: int = Field(default=30, ge=0)
    bank_base_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8001")
    bank_merchant_api_key: SecretStr = Field(repr=False)
    webhook_secret: SecretStr = Field(repr=False)
    secret_key: SecretStr = Field(repr=False)
    access_token_expire_minutes: int = Field(default=60, gt=0)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("TIMEZONE must be a valid IANA time zone") from exc
        return value

    @field_validator("bank_base_url")
    @classmethod
    def validate_bank_base_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.username is not None or value.password is not None:
            raise ValueError("BANK_BASE_URL must not contain credentials")
        if value.query is not None or value.fragment is not None or value.path not in (None, "/"):
            raise ValueError("BANK_BASE_URL must contain only an HTTP(S) origin")
        return value

    @field_validator("bank_merchant_api_key", "webhook_secret", "secret_key")
    @classmethod
    def validate_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret) < 32 or any(character.isspace() for character in secret):
            raise ValueError("Secrets must contain at least 32 characters and no whitespace")
        if secret.casefold().startswith(("change-me", "changeme", "replace-me", "your-secret")):
            raise ValueError("Replace example secrets with independently generated values")
        return value


@lru_cache
def get_settings() -> Settings:
    """Load settings on first use; restart the process after changing configuration."""
    return Settings()
````

app/core/enums.py

````python
"""Shared domain values used by calculations and future catalog models."""

from enum import StrEnum


class ProductUnit(StrEnum):
    PIECE = "PIECE"
    KG = "KG"


class OrderStatus(StrEnum):
    OPEN = "OPEN"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class StockReason(StrEnum):
    SALE = "SALE"
    RESTOCK = "RESTOCK"
    ADJUSTMENT = "ADJUSTMENT"


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    CASHIER = "CASHIER"
````

app/core/errors.py

````python
"""Consistent public errors and logging that excludes exception input values."""

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import JsonValue
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.schemas.common import ErrorBody, ErrorResponse

logger = logging.getLogger(__name__)
HTTP_ERRORS = {
    400: ("BAD_REQUEST", "Некорректный запрос."),
    401: ("UNAUTHORIZED", "Требуется авторизация."),
    403: ("FORBIDDEN", "Недостаточно прав."),
    404: ("NOT_FOUND", "Ресурс не найден."),
    405: ("METHOD_NOT_ALLOWED", "Метод запроса не поддерживается."),
    409: ("CONFLICT", "Операция конфликтует с текущим состоянием."),
    410: ("GONE", "Ресурс больше недоступен."),
    422: ("VALIDATION_ERROR", "Некорректные данные запроса."),
    429: ("TOO_MANY_REQUESTS", "Слишком много запросов."),
    500: ("INTERNAL_ERROR", "Внутренняя ошибка сервера."),
    502: ("BAD_GATEWAY", "Ошибка внешнего сервиса."),
    503: ("SERVICE_UNAVAILABLE", "Сервис временно недоступен."),
}


class AppError(Exception):
    """An intentional error containing only data safe to expose to the client."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, JsonValue] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, JsonValue] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details or {}))
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
        headers={**(headers or {}), "Cache-Control": "no-store"},
    )


def log_safe_exception(exc: Exception) -> None:
    """Log stack locations without exception messages, source lines, or local values."""
    frames = traceback.extract_tb(exc.__traceback__)
    locations = "\n".join(f"{frame.filename}:{frame.lineno} in {frame.name}" for frame in frames)
    logger.error("Request failure (%s)\n%s", type(exc).__name__, locations)


class UnexpectedErrorMiddleware:
    """Handle failures before server middleware can log their unfiltered messages."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        response_started = False

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except Exception as exc:
            log_safe_exception(exc)
            if response_started:
                raise RuntimeError("Request failed after response started") from None
            response = error_response(500, *HTTP_ERRORS[500])
            await response(scope, receive, send)


def install_error_handlers(app: FastAPI) -> None:
    """Register handlers for domain, HTTP, and request validation errors."""

    @app.exception_handler(AppError)
    def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(HTTPException)
    def handle_http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        if exc.status_code >= 500:
            log_safe_exception(exc)
        code, message = HTTP_ERRORS.get(exc.status_code, ("HTTP_ERROR", "Ошибка запроса."))
        return error_response(exc.status_code, code, message, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    def handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [{"location": list(item["loc"]), "type": item["type"]} for item in exc.errors()]
        return error_response(422, *HTTP_ERRORS[422], details={"fields": fields})

    app.add_middleware(UnexpectedErrorMiddleware)
````

app/core/money.py

````python
"""Calculate line totals using integer minor units only."""

from app.core.enums import ProductUnit

GRAMS_PER_KILOGRAM = 1000
MAX_SAFE_MINOR = 2**53 - 1


def calculate_line_total(unit: ProductUnit, price_minor: int, quantity: int) -> int:
    """Price pieces or grams, rounding a weight-based line once, half up.

    The price is per piece for PIECE and per kilogram for KG. Quantity is
    positive whole pieces or grams. Zero-priced products are allowed.
    """
    if not isinstance(unit, ProductUnit):
        raise ValueError("unit must be a ProductUnit member")
    if type(price_minor) is not int or price_minor < 0:
        raise ValueError("price_minor must be a nonnegative integer")
    if type(quantity) is not int or quantity <= 0:
        raise ValueError("quantity must be a positive integer")

    subtotal = price_minor * quantity
    if unit is ProductUnit.PIECE:
        return subtotal
    return (subtotal + GRAMS_PER_KILOGRAM // 2) // GRAMS_PER_KILOGRAM
````

app/create_user.py

````python
"""Create an account interactively without passwords in process arguments."""

import argparse
import getpass
import sys

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.enums import UserRole
from app.core.errors import AppError
from app.db.session import create_db_engine, create_session_factory
from app.schemas.auth import CreateUserInput
from app.services.auth import create_user


def main() -> int:
    parser = argparse.ArgumentParser(description="Создать пользователя QR Mini-Market")
    parser.add_argument(
        "--username", required=True, help="3–64 символа: буквы латиницы, цифры, _.-"
    )
    parser.add_argument("--role", required=True, choices=[role.value for role in UserRole])
    arguments = parser.parse_args()
    try:
        password = getpass.getpass("Пароль (12–128 символов): ")
        if password != getpass.getpass("Повторите пароль: "):
            print("Пароли не совпадают.", file=sys.stderr)
            return 1
        data = CreateUserInput(username=arguments.username, password=password, role=arguments.role)
        settings = get_settings()
        engine = create_db_engine(settings.database_url)
        try:
            user = create_user(create_session_factory(engine), data)
        finally:
            engine.dispose()
    except (EOFError, KeyboardInterrupt):
        print("\nСоздание пользователя отменено.", file=sys.stderr)
        return 1
    except ValidationError:
        print("Проверьте имя, длину пароля (12–128) и настройки .env.", file=sys.stderr)
        return 1
    except AppError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print(
            "База данных недоступна. Проверьте DATABASE_URL и выполните alembic upgrade head.",
            file=sys.stderr,
        )
        return 1
    print(f"Пользователь {user.username} создан, роль {user.role.value}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
````

app/db/__init__.py

````python
"""Database infrastructure; importing this package does not open connections."""
````

app/db/base.py

````python
"""Declarative base and stable constraint names for future migrations."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base for shop models; each CheckConstraint must have an explicit name."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
````

app/db/session.py

````python
"""Synchronous engine and session factories with explicit transaction ownership."""

import sqlite3

from sqlalchemy import URL, create_engine, event, make_url
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry, StaticPool

SQLITE_BUSY_TIMEOUT_MS = 5000
SUPPORTED_DRIVERS = {
    "sqlite",
    "sqlite+pysqlite",
    "postgresql",
    "postgresql+psycopg",
    "postgresql+psycopg2",
}


def create_db_engine(database_url: str | URL) -> Engine:
    """Build a lazy engine; its owner must dispose it during application shutdown."""
    try:
        url = make_url(database_url)
    except ArgumentError:
        raise ValueError("DATABASE_URL must be a valid SQLAlchemy connection URL") from None
    if url.drivername not in SUPPORTED_DRIVERS:
        raise ValueError(
            "DATABASE_URL must use a supported synchronous SQLite or PostgreSQL driver"
        )

    if url.get_backend_name() != "sqlite":
        return create_engine(url, pool_pre_ping=True, hide_parameters=True)

    in_memory = url.database in (None, "", ":memory:")
    connect_args = {"check_same_thread": False, "timeout": SQLITE_BUSY_TIMEOUT_MS / 1000}
    if hasattr(sqlite3, "LEGACY_TRANSACTION_CONTROL"):
        connect_args["autocommit"] = sqlite3.LEGACY_TRANSACTION_CONTROL
    options = {"poolclass": StaticPool} if in_memory else {}
    engine = create_engine(
        url, connect_args=connect_args, pool_pre_ping=True, hide_parameters=True, **options
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection: sqlite3.Connection, _record: ConnectionPoolEntry) -> None:
        connection.isolation_level = None
        cursor = connection.cursor()
        try:
            cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA foreign_keys=ON")
            mode = cursor.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if not in_memory and mode.lower() != "wal":
                raise RuntimeError("SQLite could not enable WAL for the database file")
        finally:
            cursor.close()

    @event.listens_for(engine, "begin")
    def begin_sqlite(connection: Connection) -> None:
        statement = (
            "BEGIN IMMEDIATE"
            if connection.get_execution_options().get("write_transaction")
            else "BEGIN"
        )
        connection.exec_driver_sql(statement)

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create independent sessions; services explicitly commit or roll back each transaction."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
````

app/db/transactions.py

````python
"""Retry complete local write transactions; never run network calls inside them."""

import logging
import time
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import AppError

T = TypeVar("T")
logger = logging.getLogger(__name__)


def run_write(factory: sessionmaker[Session], operation: Callable[[Session], T]) -> T:
    """Commit a fresh session, with serialized SQLite writers and bounded retries."""
    for attempt in range(4):
        try:
            with factory.begin() as session:
                if session.get_bind().dialect.name == "sqlite":
                    session.connection(execution_options={"write_transaction": True})
                return operation(session)
        except OperationalError as exc:
            sqlite_code = getattr(exc.orig, "sqlite_errorcode", 0)
            sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
            retryable = (sqlite_code & 255) in (5, 6) or sqlstate in ("40001", "40P01")
            if not retryable:
                raise
            if attempt == 3:
                raise AppError(
                    409, "CONCURRENT_UPDATE", "Данные изменяются. Повторите операцию."
                ) from None
            logger.info("Retrying local database transaction, attempt %s", attempt + 2)
            time.sleep(0.01 * 2**attempt)
    raise AssertionError("Unreachable transaction retry state")
````

app/db/types.py

````python
"""Timezone-aware UTC values across SQLite and PostgreSQL."""

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """Store UTC and return aware values; SQLite stores naive UTC internally."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("UTCDateTime requires a timezone-aware datetime")
        value = value.astimezone(UTC)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
````

app/dependencies.py

````python
"""Request-scoped sessions and the database readiness probe."""

import logging
from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import AppError

logger = logging.getLogger(__name__)


def get_session(request: Request) -> Iterator[Session]:
    """Close the request session without implicitly committing pending changes."""
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session


def ping_database(engine: Engine) -> None:
    """Check connectivity without requiring or creating business tables."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("Database readiness probe failed (%s)", type(exc).__name__)
        raise AppError(503, "DATABASE_UNAVAILABLE", "База данных временно недоступна.") from None


def require_database(request: Request) -> None:
    """Resolve the current application's engine for the health endpoint."""
    ping_database(request.app.state.engine)
````

app/main.py

````python
"""Application factory and lifecycle-owned resources."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import Settings, get_settings
from app.core.errors import HTTP_ERRORS, install_error_handlers
from app.db.session import create_db_engine, create_session_factory
from app.dependencies import ping_database
from app.providers.base import PaymentProvider
from app.providers.mock_bank import MockBankProvider
from app.routers import auth, catalog, health, orders, pages, payments, reports
from app.schemas.common import ErrorResponse
from app.services.payments import PaymentService

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    provider: PaymentProvider | None = None,
    run_worker: bool = True,
) -> FastAPI:
    """Build an application without reading settings or opening a database yet."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        active_settings = settings if settings is not None else get_settings()
        engine = create_db_engine(active_settings.database_url)
        client = None
        worker = None
        stop = asyncio.Event()
        try:
            factory = create_session_factory(engine)
            application.state.settings = active_settings
            application.state.engine = engine
            application.state.session_factory = factory
            await asyncio.to_thread(ping_database, engine)
            active_provider = provider
            if active_provider is None:
                client = httpx.Client(trust_env=False)
                active_provider = MockBankProvider(client, active_settings)
            application.state.provider = active_provider
            service = PaymentService(factory, active_provider, active_settings)

            async def reconcile() -> None:
                while not stop.is_set():
                    try:
                        await asyncio.to_thread(service.sweep)
                    except Exception as exc:
                        logger.error("Payment reconciliation failed (%s)", type(exc).__name__)
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=15)
                    except TimeoutError:
                        pass

            if run_worker:
                worker = asyncio.create_task(reconcile())
            yield
        finally:
            stop.set()
            if worker is not None:
                await worker
            if client is not None:
                await asyncio.to_thread(client.close)
            await asyncio.to_thread(engine.dispose)
            for name in ("provider", "session_factory", "engine", "settings"):
                if hasattr(application.state, name):
                    delattr(application.state, name)

    application = FastAPI(
        title="QR Mini-Market",
        debug=False,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        responses={status: {"model": ErrorResponse} for status in HTTP_ERRORS},
    )
    install_error_handlers(application)
    application.mount(
        "/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static"
    )
    for router in (health, auth, catalog, orders, payments, reports, pages):
        application.include_router(router.router)
    return application


app = create_app()
````

app/models/__init__.py

````python
"""Import mapped classes so Alembic sees the complete shop metadata."""

from app.models.catalog import Category, Product
from app.models.commerce import Order, OrderItem, Payment, PaymentEvent, StockMovement, User

__all__ = [
    "Category",
    "Product",
    "Order",
    "OrderItem",
    "Payment",
    "PaymentEvent",
    "StockMovement",
    "User",
]
````

app/models/catalog.py

````python
"""Catalog tables and database invariants, independent of HTTP routes."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Enum, ForeignKey, String, Uuid, event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column, validates
from sqlalchemy.sql import true

from app.core.barcodes import validate_ean
from app.core.enums import ProductUnit
from app.db.base import Base
from app.db.types import UTCDateTime

MAX_PRICE_MINOR = 2**63 - 1
MAX_QUANTITY = 2**31 - 1


def utc_now() -> datetime:
    return datetime.now(UTC)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("length(name) BETWEEN 1 AND 100", name="name_length"),
        CheckConstraint("length(slug) BETWEEN 1 AND 100", name="slug_length"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="not_own_parent"),
        CheckConstraint(
            "sort_order BETWEEN -2147483648 AND 2147483647 "
            "AND sort_order = CAST(sort_order AS INTEGER)",
            name="sort_order_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[UUID] = mapped_column(Uuid(), default=uuid4, unique=True)
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    sort_order: Mapped[int] = mapped_column(default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="active_bool"), default=True, server_default=true()
    )


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("length(name) BETWEEN 1 AND 200", name="name_length"),
        CheckConstraint("length(name_normalized) BETWEEN 1 AND 600", name="name_normalized_length"),
        CheckConstraint("length(barcode) IN (8, 13)", name="barcode_length"),
        CheckConstraint(
            "description IS NULL OR length(description) <= 2000", name="description_length"
        ),
        CheckConstraint(
            f"price_minor BETWEEN 0 AND {MAX_PRICE_MINOR} "
            "AND price_minor = CAST(price_minor AS BIGINT)",
            name="price_range",
        ),
        CheckConstraint(
            f"stock_quantity BETWEEN 0 AND {MAX_QUANTITY} "
            "AND stock_quantity = CAST(stock_quantity AS INTEGER)",
            name="stock_range",
        ),
        CheckConstraint(
            f"reserved_quantity BETWEEN 0 AND {MAX_QUANTITY} "
            "AND reserved_quantity = CAST(reserved_quantity AS INTEGER)",
            name="reserved_range",
        ),
        CheckConstraint(
            f"min_stock_quantity BETWEEN 0 AND {MAX_QUANTITY} "
            "AND min_stock_quantity = CAST(min_stock_quantity AS INTEGER)",
            name="min_stock_range",
        ),
        CheckConstraint("reserved_quantity <= stock_quantity", name="reserved_within_stock"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[UUID] = mapped_column(Uuid(), default=uuid4, unique=True)
    name: Mapped[str] = mapped_column(String(200))
    name_normalized: Mapped[str] = mapped_column(String(600), index=True)
    barcode: Mapped[str] = mapped_column(String(13), unique=True, index=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    unit: Mapped[ProductUnit] = mapped_column(
        Enum(
            ProductUnit,
            values_callable=lambda members: [member.value for member in members],
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="product_unit",
        )
    )
    price_minor: Mapped[int] = mapped_column(BigInteger())
    stock_quantity: Mapped[int] = mapped_column(default=0, server_default="0")
    reserved_quantity: Mapped[int] = mapped_column(default=0, server_default="0")
    min_stock_quantity: Mapped[int] = mapped_column(default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="active_bool"), default=True, server_default=true()
    )
    description: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)

    @validates("barcode")
    def validate_barcode(self, _key: str, value: str) -> str:
        return validate_ean(value)

    @validates("price_minor", "stock_quantity", "reserved_quantity", "min_stock_quantity")
    def validate_integer(self, key: str, value: int) -> int:
        maximum = MAX_PRICE_MINOR if key == "price_minor" else MAX_QUANTITY
        if type(value) is not int or not 0 <= value <= maximum:
            raise ValueError(f"{key} must be an integer between 0 and {maximum}")
        return value


@event.listens_for(Product, "before_insert")
@event.listens_for(Product, "before_update")
def normalize_product_name(
    _mapper: Mapper[Product], _connection: Connection, target: Product
) -> None:
    """Keep normalization in sync for ORM writes, including renames."""
    if not isinstance(target.name, str) or not 1 <= len(target.name.strip()) <= 200:
        raise ValueError("Product name must contain between 1 and 200 characters")
    target.name = target.name.strip()
    target.name_normalized = target.name.casefold()
````

app/models/commerce.py

````python
"""Shop users, order snapshots, payments, immutable events, and stock ledger."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import OrderStatus, PaymentStatus, ProductUnit, StockReason, UserRole
from app.db.base import Base
from app.db.types import UTCDateTime
from app.models.catalog import utc_now


def string_enum(kind: type[StrEnum], name: str) -> Enum:
    return Enum(
        kind,
        values_callable=lambda members: [member.value for member in members],
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        name=name,
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("length(username) BETWEEN 3 AND 64", name="username_length"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[UUID] = mapped_column(Uuid(), default=uuid4, unique=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[UserRole] = mapped_column(string_enum(UserRole, "user_role"))
    is_active: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="active_bool"), default=True, server_default=true()
    )


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "total_minor BETWEEN 0 AND 9223372036854775807 "
            "AND total_minor = CAST(total_minor AS BIGINT)",
            name="total_range",
        ),
        CheckConstraint("currency = 'KZT'", name="currency"),
        CheckConstraint("length(terminal_code) BETWEEN 1 AND 64", name="terminal_length"),
        Index("ix_orders_status_terminal_code", "status", "terminal_code"),
        Index(
            "uq_orders_active_terminal",
            "terminal_code",
            unique=True,
            sqlite_where=text("status IN ('OPEN', 'PENDING_PAYMENT')"),
            postgresql_where=text("status IN ('OPEN', 'PENDING_PAYMENT')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[UUID] = mapped_column(Uuid(), default=uuid4, unique=True)
    number: Mapped[str] = mapped_column(String(64), unique=True)
    terminal_code: Mapped[str] = mapped_column(String(64), default="main", server_default="main")
    status: Mapped[OrderStatus] = mapped_column(
        string_enum(OrderStatus, "order_status"), default=OrderStatus.OPEN, server_default="OPEN"
    )
    total_minor: Mapped[int] = mapped_column(BigInteger(), default=0, server_default="0")
    currency: Mapped[str] = mapped_column(String(3), default="KZT", server_default="KZT")
    cashier_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)
    paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint("order_id", "product_id"),
        CheckConstraint(
            "quantity BETWEEN 1 AND 2147483647 AND quantity = CAST(quantity AS INTEGER)",
            name="quantity_range",
        ),
        CheckConstraint(
            "unit_price_minor BETWEEN 0 AND 9223372036854775807 "
            "AND unit_price_minor = CAST(unit_price_minor AS BIGINT)",
            name="price_range",
        ),
        CheckConstraint(
            "line_total_minor BETWEEN 0 AND 9223372036854775807 "
            "AND line_total_minor = CAST(line_total_minor AS BIGINT)",
            name="total_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[UUID] = mapped_column(Uuid(), default=uuid4, unique=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    product_name: Mapped[str] = mapped_column(String(200))
    barcode: Mapped[str] = mapped_column(String(13))
    unit: Mapped[ProductUnit] = mapped_column(string_enum(ProductUnit, "product_unit"))
    unit_price_minor: Mapped[int] = mapped_column(BigInteger())
    quantity: Mapped[int] = mapped_column()
    line_total_minor: Mapped[int] = mapped_column(BigInteger())


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("creation_attempts >= 0", name="creation_attempts_nonnegative"),
        CheckConstraint(
            "amount_minor BETWEEN 1 AND 9223372036854775807 "
            "AND amount_minor = CAST(amount_minor AS BIGINT)",
            name="amount_range",
        ),
        CheckConstraint("currency = 'KZT'", name="currency"),
        Index("ix_payments_status_expires_at", "status", "expires_at"),
        Index(
            "uq_payments_pending_order",
            "order_id",
            unique=True,
            sqlite_where=text("status = 'PENDING'"),
            postgresql_where=text("status = 'PENDING'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[UUID] = mapped_column(Uuid(), default=uuid4, unique=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), index=True)
    provider: Mapped[str] = mapped_column(
        String(32), default="mock_bank", server_default="mock_bank"
    )
    provider_invoice_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    creation_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    creation_attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    amount_minor: Mapped[int] = mapped_column(BigInteger())
    currency: Mapped[str] = mapped_column(String(3), default="KZT", server_default="KZT")
    status: Mapped[PaymentStatus] = mapped_column(
        string_enum(PaymentStatus, "payment_status"),
        default=PaymentStatus.PENDING,
        server_default="PENDING",
    )
    pay_url: Mapped[str | None] = mapped_column(String(2048))
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    failure_reason: Mapped[str | None] = mapped_column(String(100))
    needs_review: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="review_bool"), default=False, server_default=false()
    )
    review_reason: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    __table_args__ = (UniqueConstraint("provider", "provider_event_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32))
    provider_event_id: Mapped[str] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(50))
    raw_body: Mapped[str] = mapped_column(Text())
    signature_valid: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="signature_bool")
    )
    outcome: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint(
            "delta BETWEEN -2147483647 AND 2147483647 "
            "AND delta <> 0 AND delta = CAST(delta AS INTEGER)",
            name="delta_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    delta: Mapped[int] = mapped_column()
    reason: Mapped[StockReason] = mapped_column(string_enum(StockReason, "stock_reason"))
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
````

app/providers/__init__.py

````python
"""Adapters for merchant payment APIs."""

from app.providers.base import BankStatus, InvoiceSnapshot, PaymentProvider, ProviderUnavailable
from app.providers.mock_bank import MockBankProvider

__all__ = [
    "BankStatus",
    "InvoiceSnapshot",
    "MockBankProvider",
    "PaymentProvider",
    "ProviderUnavailable",
]
````

app/providers/base.py

````python
"""Provider contracts independent of a particular bank implementation."""

from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import (
    AnyHttpUrl,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    model_validator,
)


class BankStatus(StrEnum):
    CREATED = "CREATED"
    PAID = "PAID"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class InvoiceSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    invoice_id: UUID
    merchant_reference: UUID
    amount_minor: StrictInt = Field(gt=0, le=2**63 - 1)
    currency: str = Field(min_length=3, max_length=3)
    status: BankStatus
    pay_url: AnyHttpUrl = Field(max_length=2048)
    expires_at: AwareDatetime
    paid_at: AwareDatetime | None = None
    failure_reason: str | None = Field(default=None, max_length=100)
    event_id: UUID | None = None

    @model_validator(mode="after")
    def validate_final_event(self) -> "InvoiceSnapshot":
        if self.status is not BankStatus.CREATED and self.event_id is None:
            raise ValueError("A final invoice must include its durable event ID")
        if self.pay_url.username is not None or self.pay_url.password is not None:
            raise ValueError("Payment URLs must not contain credentials")
        return self


class ProviderUnavailable(Exception):
    """A safe failure; only proven non-creation allows reservation compensation."""

    def __init__(self, *, definitely_not_created: bool = False) -> None:
        super().__init__("Payment provider unavailable")
        self.definitely_not_created = definitely_not_created


class PaymentProvider(Protocol):
    def create_invoice(
        self,
        *,
        amount_minor: int,
        currency: str,
        merchant_reference: UUID,
        description: str,
        ttl_seconds: int,
    ) -> InvoiceSnapshot: ...

    def get_invoice_status(self, invoice_id: UUID) -> InvoiceSnapshot: ...

    def cancel_invoice(self, invoice_id: UUID) -> InvoiceSnapshot: ...
````

app/providers/fake.py

````python
"""Deterministic in-memory provider for tests, never selected by environment settings."""

from datetime import UTC, datetime, timedelta
from threading import RLock
from uuid import UUID, uuid4

from app.providers.base import BankStatus, InvoiceSnapshot, ProviderUnavailable


class FakeProvider:
    def __init__(self) -> None:
        self.invoices: dict[UUID, InvoiceSnapshot] = {}
        self.references: dict[UUID, UUID] = {}
        self.create_calls = 0
        self.status_calls = 0
        self.create_error: ProviderUnavailable | None = None
        self.lock = RLock()

    def create_invoice(
        self,
        *,
        amount_minor: int,
        currency: str,
        merchant_reference: UUID,
        description: str,
        ttl_seconds: int,
    ) -> InvoiceSnapshot:
        with self.lock:
            self.create_calls += 1
            if self.create_error is not None:
                raise self.create_error
            if merchant_reference in self.references:
                invoice = self.invoices[self.references[merchant_reference]]
                if invoice.amount_minor != amount_minor or invoice.currency != currency:
                    raise ProviderUnavailable()
                return invoice
            invoice_id = uuid4()
            invoice = InvoiceSnapshot(
                invoice_id=invoice_id,
                merchant_reference=merchant_reference,
                amount_minor=amount_minor,
                currency=currency,
                status=BankStatus.CREATED,
                pay_url=f"http://bank.test/pay/{uuid4().hex}",
                expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
            )
            self.invoices[invoice_id] = invoice
            self.references[merchant_reference] = invoice_id
            return invoice

    def get_invoice_status(self, invoice_id: UUID) -> InvoiceSnapshot:
        with self.lock:
            self.status_calls += 1
            invoice = self.invoices[invoice_id]
            if invoice.status is BankStatus.CREATED and invoice.expires_at <= datetime.now(UTC):
                return self.finish(invoice_id, BankStatus.EXPIRED)
            return invoice

    def cancel_invoice(self, invoice_id: UUID) -> InvoiceSnapshot:
        with self.lock:
            invoice = self.get_invoice_status(invoice_id)
            if invoice.status is BankStatus.CREATED:
                return self.finish(invoice_id, BankStatus.CANCELLED)
            return invoice

    def finish(
        self, invoice_id: UUID, status: BankStatus, failure_reason: str | None = None
    ) -> InvoiceSnapshot:
        with self.lock:
            invoice = self.invoices[invoice_id]
            if invoice.status is not BankStatus.CREATED:
                return invoice
            if status is BankStatus.CREATED:
                raise ValueError("A final status is required")
            invoice = invoice.model_copy(
                update={
                    "status": status,
                    "event_id": uuid4(),
                    "failure_reason": failure_reason,
                    "paid_at": datetime.now(UTC) if status is BankStatus.PAID else None,
                }
            )
            self.invoices[invoice_id] = invoice
            return invoice
````

app/providers/mock_bank.py

````python
"""HTTP adapter; it deliberately imports no code from the bank application."""

from uuid import UUID

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.providers.base import InvoiceSnapshot, ProviderUnavailable


class MockBankProvider:
    def __init__(self, client: httpx.Client, settings: Settings) -> None:
        self.client = client
        self.base_url = str(settings.bank_base_url).rstrip("/")
        self.api_key = settings.bank_merchant_api_key.get_secret_value()

    def _request(self, method: str, path: str, *, payload: dict | None = None) -> InvoiceSnapshot:
        try:
            response = self.client.request(
                method,
                self.base_url + path,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
        except httpx.ConnectError:
            raise ProviderUnavailable(definitely_not_created=True) from None
        except httpx.HTTPError:
            raise ProviderUnavailable() from None
        if response.status_code >= 400:
            raise ProviderUnavailable(
                definitely_not_created=response.status_code in (400, 401, 403, 422)
            )
        try:
            return InvoiceSnapshot.model_validate(response.json())
        except (ValueError, ValidationError):
            raise ProviderUnavailable() from None

    def create_invoice(
        self,
        *,
        amount_minor: int,
        currency: str,
        merchant_reference: UUID,
        description: str,
        ttl_seconds: int,
    ) -> InvoiceSnapshot:
        return self._request(
            "POST",
            "/api/merchant/invoices",
            payload={
                "amount_minor": amount_minor,
                "currency": currency,
                "merchant_reference": str(merchant_reference),
                "description": description,
                "ttl_seconds": ttl_seconds,
            },
        )

    def get_invoice_status(self, invoice_id: UUID) -> InvoiceSnapshot:
        return self._request("GET", f"/api/merchant/invoices/{invoice_id}")

    def cancel_invoice(self, invoice_id: UUID) -> InvoiceSnapshot:
        try:
            return self._request("POST", f"/api/merchant/invoices/{invoice_id}/cancel")
        except ProviderUnavailable:
            # A concurrent payment can make cancellation return 409; a lost cancel
            # response can also hide a final result. Always reconcile before release.
            return self.get_invoice_status(invoice_id)
````

app/routers/__init__.py

````python
"""Thin HTTP routers for the shop application."""
````

app/routers/auth.py

````python
"""Session cookies for the browser and bearer tokens for API clients."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.models import User
from app.schemas.auth import LoginInput, LoginResponse, UserResponse
from app.services.auth import authenticate, require_same_origin, require_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(data: LoginInput, request: Request, response: Response) -> LoginResponse:
    require_same_origin(request)
    settings = request.app.state.settings
    result = authenticate(request.app.state.session_factory, data, settings)
    options = {"secure": settings.app_env == "production", "samesite": "lax", "path": "/"}
    maximum_age = settings.access_token_expire_minutes * 60
    response.set_cookie(
        "access_token", result.access_token, httponly=True, max_age=maximum_age, **options
    )
    response.set_cookie(
        "csrf_token", result.csrf_token, httponly=False, max_age=maximum_age, **options
    )
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/me", response_model=UserResponse)
def me(user: Annotated[User, Depends(require_user)], response: Response) -> UserResponse:
    response.headers["Cache-Control"] = "no-store"
    return UserResponse.model_validate(user)


@router.post("/logout")
def logout(
    _user: Annotated[User, Depends(require_user)], request: Request, response: Response
) -> dict[str, bool]:
    options = {
        "secure": request.app.state.settings.app_env == "production",
        "samesite": "lax",
        "path": "/",
    }
    response.delete_cookie("access_token", httponly=True, **options)
    response.delete_cookie("csrf_token", httponly=False, **options)
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True}
````

app/routers/catalog.py

````python
"""Thin catalog endpoints; access checks run before service transactions."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.schemas.catalog import (
    Barcode,
    CategoryCreate,
    CategoryPage,
    CategoryPatch,
    CategoryRead,
    ProductCreate,
    ProductPage,
    ProductPatch,
    ProductRead,
    PublicProductPage,
    StockAdjustment,
)
from app.services.auth import require_admin, require_cashier
from app.services.catalog import CatalogService

router = APIRouter(prefix="/api/v1", tags=["catalog"])
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=1_000_000)]
Search = Annotated[str | None, Query(max_length=200)]
BarcodeQuery = Annotated[Barcode | None, Query()]


def service(request: Request) -> CatalogService:
    return CatalogService(request.app.state.session_factory)


@router.get("/categories", response_model=CategoryPage, dependencies=[Depends(require_cashier)])
def categories(request: Request, limit: Limit = 50, offset: Offset = 0) -> dict:
    return service(request).list_categories(limit=limit, offset=offset)


@router.get("/public/categories", response_model=CategoryPage)
def public_categories(request: Request, limit: Limit = 50, offset: Offset = 0) -> dict:
    return service(request).list_categories(public=True, limit=limit, offset=offset)


@router.post(
    "/categories",
    response_model=CategoryRead,
    status_code=201,
    dependencies=[Depends(require_admin)],
)
def create_category(request: Request, command: CategoryCreate) -> dict:
    return service(request).create_category(command)


@router.patch(
    "/categories/{category_id}", response_model=CategoryRead, dependencies=[Depends(require_admin)]
)
def update_category(request: Request, category_id: UUID, command: CategoryPatch) -> dict:
    return service(request).update_category(category_id, command)


@router.delete(
    "/categories/{category_id}", response_model=CategoryRead, dependencies=[Depends(require_admin)]
)
def delete_category(request: Request, category_id: UUID) -> dict:
    return service(request).delete_category(category_id)


@router.get("/products", response_model=ProductPage, dependencies=[Depends(require_cashier)])
def products(
    request: Request,
    q: Search = None,
    category_id: UUID | None = None,
    include_subcategories: bool = False,
    is_active: bool | None = None,
    barcode: BarcodeQuery = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> dict:
    return service(request).list_products(
        q=q,
        category_id=category_id,
        include_subcategories=include_subcategories,
        is_active=is_active,
        barcode=barcode,
        limit=limit,
        offset=offset,
    )


@router.get("/public/products", response_model=PublicProductPage)
def public_products(
    request: Request,
    q: Search = None,
    category_id: UUID | None = None,
    include_subcategories: bool = False,
    barcode: BarcodeQuery = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> dict:
    return service(request).list_products(
        q=q,
        category_id=category_id,
        include_subcategories=include_subcategories,
        barcode=barcode,
        limit=limit,
        offset=offset,
        public=True,
    )


@router.post(
    "/products", response_model=ProductRead, status_code=201, dependencies=[Depends(require_admin)]
)
def create_product(request: Request, command: ProductCreate) -> dict:
    return service(request).create_product(command)


@router.get(
    "/products/by-barcode/{barcode}",
    response_model=ProductRead,
    dependencies=[Depends(require_cashier)],
)
def product_by_barcode(request: Request, barcode: Barcode) -> dict:
    return service(request).get_by_barcode(barcode)


@router.get(
    "/products/{product_id}", response_model=ProductRead, dependencies=[Depends(require_cashier)]
)
def product(request: Request, product_id: UUID) -> dict:
    return service(request).get_product(product_id)


@router.patch(
    "/products/{product_id}", response_model=ProductRead, dependencies=[Depends(require_admin)]
)
def update_product(request: Request, product_id: UUID, command: ProductPatch) -> dict:
    return service(request).update_product(product_id, command)


@router.delete(
    "/products/{product_id}", response_model=ProductRead, dependencies=[Depends(require_admin)]
)
def delete_product(request: Request, product_id: UUID) -> dict:
    return service(request).delete_product(product_id)


@router.post(
    "/products/{product_id}/stock-adjustments",
    response_model=ProductRead,
    dependencies=[Depends(require_admin)],
)
def adjust_stock(request: Request, product_id: UUID, command: StockAdjustment) -> dict:
    return service(request).adjust_stock(product_id, command)
````

app/routers/health.py

````python
"""Public readiness endpoint."""

from fastapi import APIRouter, Depends, Response

from app.dependencies import require_database
from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, dependencies=[Depends(require_database)])
def health(response: Response) -> HealthResponse:
    response.headers["Cache-Control"] = "no-store"
    return HealthResponse()
````

app/routers/orders.py

````python
"""Order routes delegate all business decisions to the service layer."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from app.core.enums import OrderStatus
from app.models import User
from app.routers.catalog import Limit, Offset
from app.schemas.orders import (
    DisplayRead,
    ItemAdd,
    ItemPatch,
    OrderCreate,
    OrderPage,
    OrderRead,
    ReceiptRead,
    TerminalCode,
)
from app.services.auth import require_cashier
from app.services.orders import OrderService

router = APIRouter(prefix="/api/v1", tags=["orders"])


def service(request: Request) -> OrderService:
    return OrderService(request.app.state.session_factory, request.app.state.settings.currency)


@router.post("/orders", response_model=OrderRead, status_code=201)
def create_order(
    request: Request, command: OrderCreate, user: Annotated[User, Depends(require_cashier)]
) -> dict:
    return service(request).create_order(command, user.id)


@router.get("/orders", response_model=OrderPage, dependencies=[Depends(require_cashier)])
def orders(
    request: Request,
    terminal_code: TerminalCode | None = None,
    status: OrderStatus | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> dict:
    return service(request).list_orders(
        terminal_code=terminal_code, status=status, limit=limit, offset=offset
    )


@router.get("/orders/{order_id}", response_model=OrderRead, dependencies=[Depends(require_cashier)])
def order(request: Request, order_id: UUID) -> dict:
    return service(request).get_order(order_id)


@router.post(
    "/orders/{order_id}/items", response_model=OrderRead, dependencies=[Depends(require_cashier)]
)
def add_item(request: Request, order_id: UUID, command: ItemAdd) -> dict:
    return service(request).add_item(order_id, command)


@router.patch(
    "/orders/{order_id}/items/{item_id}",
    response_model=OrderRead,
    dependencies=[Depends(require_cashier)],
)
def update_item(request: Request, order_id: UUID, item_id: UUID, command: ItemPatch) -> dict:
    return service(request).update_item(order_id, item_id, command)


@router.delete(
    "/orders/{order_id}/items/{item_id}",
    response_model=OrderRead,
    dependencies=[Depends(require_cashier)],
)
def remove_item(request: Request, order_id: UUID, item_id: UUID) -> dict:
    return service(request).remove_item(order_id, item_id)


@router.get(
    "/orders/{order_id}/receipt",
    response_model=ReceiptRead,
    dependencies=[Depends(require_cashier)],
)
def receipt(request: Request, order_id: UUID) -> dict:
    return service(request).receipt(order_id)


@router.get("/public/terminals/{terminal_code}/display", response_model=DisplayRead)
def display(request: Request, response: Response, terminal_code: TerminalCode) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return service(request).display(terminal_code)
````

app/routers/pages.py

````python
"""Server-rendered entry pages with role checks and local static assets."""

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.errors import AppError
from app.services.auth import require_admin, require_cashier

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


def page(request: Request, name: str, *, role: str | None = None, **context: object):
    """Authenticate protected HTML pages before rendering any operational content."""
    user = None
    if role:
        try:
            user = require_admin(request) if role == "admin" else require_cashier(request)
        except AppError as exc:
            if exc.status_code == 401:
                return RedirectResponse("/login", status_code=303)
            raise
    response = templates.TemplateResponse(
        request=request,
        name=f"{name}.html",
        context={
            "page": name,
            "user": user,
            "development": request.app.state.settings.app_env == "development",
            "timezone": request.app.state.settings.timezone,
            **context,
        },
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; "
        "frame-ancestors 'none'; form-action 'self'"
    )
    return response


@router.get("/", response_class=HTMLResponse)
def home() -> RedirectResponse:
    return RedirectResponse("/cashier", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login(request: Request):
    return page(request, "login")


@router.get("/cashier", response_class=HTMLResponse)
def cashier(request: Request):
    return page(request, "cashier", role="cashier")


@router.get("/display/{terminal_code}", response_class=HTMLResponse)
def display(request: Request, terminal_code: str):
    if not 1 <= len(terminal_code) <= 64 or not all(
        character.isascii() and (character.isalnum() or character in "_-")
        for character in terminal_code
    ):
        raise AppError(404, "NOT_FOUND", "Терминал не найден.")
    return page(request, "display", terminal_code=terminal_code)


@router.get("/price-check", response_class=HTMLResponse)
def price_check(request: Request):
    return page(request, "price-check")


@router.get("/receipt/{order_uuid}", response_class=HTMLResponse)
def receipt(request: Request, order_uuid: UUID):
    return page(request, "receipt", role="cashier", order_uuid=str(order_uuid))


@router.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    return page(request, "admin", role="admin")
````

app/routers/payments.py

````python
"""Thin payment endpoints; the signature covers the original notification bytes."""

import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from app.core.enums import PaymentStatus
from app.core.errors import AppError
from app.schemas.payments import PaymentRead
from app.services.auth import require_cashier
from app.services.payments import PaymentService
from app.services.qr_service import make_qr_png

router = APIRouter(prefix="/api/v1", tags=["payments"])


def get_payment_service(request: Request) -> PaymentService:
    return PaymentService(
        request.app.state.session_factory, request.app.state.provider, request.app.state.settings
    )


Service = Annotated[PaymentService, Depends(get_payment_service)]


@router.post(
    "/orders/{order_id}/checkout",
    response_model=PaymentRead,
    dependencies=[Depends(require_cashier)],
)
def checkout(order_id: UUID, service: Service) -> dict:
    return service.checkout(order_id)


@router.post("/orders/{order_id}/cancel", dependencies=[Depends(require_cashier)])
def cancel_order(order_id: UUID, service: Service) -> dict:
    return service.cancel_order(order_id)


@router.get("/payments/{payment_id}", response_model=PaymentRead)
def get_payment(payment_id: UUID, response: Response, service: Service) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return service.get_payment(payment_id)


@router.post(
    "/payments/{payment_id}/refresh",
    response_model=PaymentRead,
    dependencies=[Depends(require_cashier)],
)
def refresh(payment_id: UUID, service: Service) -> dict:
    return service.refresh(payment_id)


@router.post(
    "/payments/{payment_id}/cancel",
    response_model=PaymentRead,
    dependencies=[Depends(require_cashier)],
)
def cancel(payment_id: UUID, service: Service) -> dict:
    return service.cancel(payment_id)


@router.get("/payments/{payment_id}/qr.png")
def qr(payment_id: UUID, service: Service) -> Response:
    payment = service.get_payment(payment_id)
    if payment["status"] != PaymentStatus.PENDING:
        status = 410 if payment["status"] == PaymentStatus.EXPIRED else 409
        raise AppError(status, "PAYMENT_NOT_PENDING", "Этот QR-код больше нельзя использовать.")
    if payment["seconds_left"] <= 0:
        raise AppError(410, "QR_EXPIRED", "Срок QR-кода истёк. Проверьте статус оплаты.")
    if not payment["pay_url"]:
        raise AppError(409, "INVOICE_NOT_READY", "Счёт банка ещё не получен.")
    return Response(
        make_qr_png(payment["pay_url"]),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/webhooks/mock-bank")
async def webhook(request: Request, service: Service) -> dict:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 16384:
            raise AppError(413, "WEBHOOK_TOO_LARGE", "Уведомление превышает допустимый размер.")
    return await asyncio.to_thread(
        service.process_webhook,
        bytes(body),
        request.headers.get("X-Timestamp", ""),
        request.headers.get("X-Signature", ""),
    )
````

app/routers/reports.py

````python
"""Administrative reporting routes; authorization is mandatory in all environments."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.services.auth import require_admin
from app.services.reports import low_stock_report, payments_review_report, sales_report

router = APIRouter(
    prefix="/api/v1/reports", tags=["reports"], dependencies=[Depends(require_admin)]
)


@router.get("/sales")
def sales(
    request: Request,
    response: Response,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return sales_report(
        request.app.state.session_factory, request.app.state.settings, date_from, date_to
    )


@router.get("/low-stock")
def low_stock(
    request: Request,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return low_stock_report(request.app.state.session_factory, limit, offset)


@router.get("/payments-needing-review")
def payments_needing_review(
    request: Request,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return payments_review_report(request.app.state.session_factory, limit, offset)
````

app/schemas/auth.py

````python
"""Validated credentials and deliberately small public user contracts."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.core.enums import UserRole


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: SecretStr = Field(min_length=1, max_length=128, repr=False)


class CreateUserInput(LoginInput):
    password: SecretStr = Field(min_length=12, max_length=128, repr=False)
    role: UserRole


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    public_id: UUID
    username: str
    role: UserRole


class LoginResponse(BaseModel):
    user: UserResponse
    access_token: str = Field(repr=False)
    csrf_token: str = Field(repr=False)
````

app/schemas/catalog.py

````python
"""Validated catalog commands and public response contracts."""

from typing import Annotated
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

from app.core.barcodes import validate_ean
from app.core.enums import ProductUnit, StockReason
from app.core.money import MAX_SAFE_MINOR
from app.models.catalog import MAX_QUANTITY

Price = Annotated[int, Field(strict=True, ge=0, le=MAX_SAFE_MINOR)]
Quantity = Annotated[int, Field(strict=True, ge=0, le=MAX_QUANTITY)]
Name = Annotated[str, Field(min_length=1, max_length=200)]
CategoryName = Annotated[str, Field(min_length=1, max_length=100)]
Slug = Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
Barcode = Annotated[
    str,
    Field(min_length=8, max_length=13, pattern=r"^(?:[0-9]{8}|[0-9]{13})$"),
    AfterValidator(validate_ean),
]


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    @field_validator("name", check_fields=False)
    @classmethod
    def trim_name(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("Name must not be blank")
        return value


class CategoryCreate(Command):
    name: CategoryName
    slug: Slug
    parent_id: UUID | None = None
    sort_order: Annotated[int, Field(strict=True, ge=-(2**31), le=MAX_QUANTITY)] = 0
    is_active: StrictBool = True


class CategoryPatch(Command):
    name: CategoryName | None = None
    slug: Slug | None = None
    parent_id: UUID | None = None
    sort_order: Annotated[int, Field(strict=True, ge=-(2**31), le=MAX_QUANTITY)] | None = None
    is_active: StrictBool | None = None

    @model_validator(mode="after")
    def reject_null_values(self) -> "CategoryPatch":
        if any(getattr(self, name) is None for name in self.model_fields_set - {"parent_id"}):
            raise ValueError("Only parent_id can be null")
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class ProductCreate(Command):
    name: Name
    barcode: Barcode
    category_id: UUID
    unit: ProductUnit
    price_minor: Price
    stock_quantity: Quantity = 0
    min_stock_quantity: Quantity = 0
    is_active: StrictBool = True
    description: Annotated[str, Field(max_length=2000)] | None = None


class ProductPatch(Command):
    name: Name | None = None
    barcode: Barcode | None = None
    category_id: UUID | None = None
    unit: ProductUnit | None = None
    price_minor: Price | None = None
    min_stock_quantity: Quantity | None = None
    is_active: StrictBool | None = None
    description: Annotated[str, Field(max_length=2000)] | None = None

    @model_validator(mode="after")
    def reject_null_values(self) -> "ProductPatch":
        if any(getattr(self, name) is None for name in self.model_fields_set - {"description"}):
            raise ValueError("Only description can be null")
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class StockAdjustment(Command):
    delta: Annotated[int, Field(strict=True, ge=-MAX_QUANTITY, le=MAX_QUANTITY)]
    reason: StockReason = StockReason.ADJUSTMENT

    @model_validator(mode="after")
    def validate_adjustment(self) -> "StockAdjustment":
        if self.delta == 0:
            raise ValueError("Stock delta must not be zero")
        if self.reason not in {StockReason.RESTOCK, StockReason.ADJUSTMENT}:
            raise ValueError("Sale movements are generated by the payment service")
        if self.reason is StockReason.RESTOCK and self.delta < 0:
            raise ValueError("Restock must increase stock")
        return self


class CategoryRead(BaseModel):
    public_id: UUID
    name: str
    slug: str
    parent_id: UUID | None
    sort_order: int
    is_active: bool


class PublicProductRead(BaseModel):
    public_id: UUID
    name: str
    barcode: str
    category_id: UUID
    unit: ProductUnit
    price_minor: int
    description: str | None
    in_stock: bool


class ProductRead(PublicProductRead):
    stock_quantity: int
    available_quantity: int
    min_stock_quantity: int
    is_active: bool


class CategoryPage(BaseModel):
    items: list[CategoryRead]
    total: int
    limit: int
    offset: int


class ProductPage(BaseModel):
    items: list[ProductRead]
    total: int
    limit: int
    offset: int


class PublicProductPage(BaseModel):
    items: list[PublicProductRead]
    total: int
    limit: int
    offset: int
````

app/schemas/common.py

````python
"""Public response contracts shared by the HTTP API."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, JsonValue] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorBody


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = "ok"
    database: Literal["ok"] = "ok"
````

app/schemas/orders.py

````python
"""Validated order commands and response contracts with public UUIDs only."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.core.enums import OrderStatus, PaymentStatus, ProductUnit
from app.models.catalog import MAX_QUANTITY
from app.schemas.catalog import Barcode, Command

TerminalCode = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")]
PositiveQuantity = Annotated[int, Field(strict=True, ge=1, le=MAX_QUANTITY)]


class OrderCreate(Command):
    terminal_code: TerminalCode = "main"


class ItemAdd(Command):
    barcode: Barcode | None = None
    product_id: UUID | None = None
    quantity: PositiveQuantity = 1

    @model_validator(mode="after")
    def exactly_one_identifier(self) -> "ItemAdd":
        if (self.barcode is None) == (self.product_id is None):
            raise ValueError("Provide exactly one of barcode or product_id")
        return self


class ItemPatch(Command):
    quantity: PositiveQuantity


class PaymentSummary(BaseModel):
    public_id: UUID
    order_id: UUID
    status: PaymentStatus
    amount_minor: int
    currency: str
    pay_url: str | None
    expires_at: datetime | None
    seconds_left: int
    failure_reason: str | None
    needs_review: bool


class OrderItemRead(BaseModel):
    public_id: UUID
    product_id: UUID
    product_name: str
    barcode: str
    unit: ProductUnit
    unit_price_minor: int
    quantity: int
    line_total_minor: int


class OrderRead(BaseModel):
    public_id: UUID
    number: str
    terminal_code: str
    status: OrderStatus
    total_minor: int
    currency: str
    created_at: datetime
    paid_at: datetime | None
    cancelled_at: datetime | None
    items: list[OrderItemRead]
    payment: PaymentSummary | None


class OrderPage(BaseModel):
    items: list[OrderRead]
    total: int
    limit: int
    offset: int


class ReceiptRead(OrderRead):
    payment_method: Literal["QR"] = "QR"
    disclaimer: str = "Учебный проект, не фискальный чек"


class DisplayRead(BaseModel):
    state: Literal["idle", "cart", "awaiting_payment", "paid", "payment_failed"]
    order: OrderRead | None
    payment: PaymentSummary | None
    seconds_left: int
    failure_reason: str | None = None
````

app/schemas/payments.py

````python
"""Public payment contracts and bounded signed notification input."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt

from app.core.enums import PaymentStatus


class PaymentRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_id: UUID
    order_id: UUID
    status: PaymentStatus
    amount_minor: int
    currency: str
    pay_url: str | None
    expires_at: AwareDatetime | None
    seconds_left: int
    failure_reason: str | None
    needs_review: bool


class EventData(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    invoice_id: UUID
    merchant_reference: UUID
    amount_minor: StrictInt = Field(gt=0, le=2**63 - 1)
    currency: str = Field(min_length=3, max_length=3)
    failure_reason: str | None = Field(default=None, max_length=100)


class BankEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    event_id: UUID
    type: Literal["invoice.paid", "invoice.failed", "invoice.expired", "invoice.cancelled"]
    created_at: AwareDatetime
    data: EventData
````

app/seed.py

````python
"""Create deterministic demo catalog entries without resetting existing stock."""

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.barcodes import generate_internal_ean13
from app.core.config import get_settings
from app.core.enums import ProductUnit, StockReason
from app.db.session import create_db_engine, create_session_factory
from app.db.transactions import run_write
from app.models import Category, Product, StockMovement

# Parent slugs occur before children, so a single pass can resolve the tree.
CATEGORIES = (
    ("food", "Еда", None),
    ("sweets", "Сладости", "food"),
    ("chocolate", "Шоколад", "sweets"),
    ("candy", "Конфеты", "sweets"),
    ("cookies", "Печенье", "sweets"),
    ("dairy", "Молочные продукты", "food"),
    ("milk-kefir", "Молоко и кефир", "dairy"),
    ("cheese-butter", "Сыр и масло", "dairy"),
    ("yogurt-curd", "Йогурты и творог", "dairy"),
    ("produce", "Овощи и фрукты", "food"),
    ("vegetables", "Овощи", "produce"),
    ("fruit", "Фрукты", "produce"),
    ("ready-food", "Готовая еда", "food"),
    ("salads", "Салаты", "ready-food"),
    ("hot-meals", "Горячие блюда", "ready-food"),
    ("baked-goods", "Выпечка", "ready-food"),
    ("bread-dough", "Тесто и хлеб", "food"),
    ("bread", "Хлеб и лаваш", "bread-dough"),
    ("dough", "Тесто и полуфабрикаты", "bread-dough"),
    ("drinks", "Напитки", "food"),
    ("water", "Вода", "drinks"),
    ("juice-soda", "Соки и газировка", "drinks"),
    ("tea-coffee", "Чай и кофе", "drinks"),
    ("household", "Мелочи и товары для дома", None),
    ("stationery", "Канцелярия", "household"),
    ("small-household", "Хозяйственные мелочи", "household"),
    ("hygiene", "Гигиена", "household"),
)

# Prices are whole tenge here and are converted to integer minor units below.
# Quantity and low-stock thresholds are pieces or grams according to the unit.
PRODUCTS = (
    ("Шоколад молочный 90 г", "chocolate", 650, "PIECE", 20, 3),
    ("Шоколад тёмный 85 г", "chocolate", 780, "PIECE", 10, 3),
    ("Конфеты карамель 200 г", "candy", 420, "PIECE", 18, 4),
    ("Конфеты сливочные 150 г", "candy", 550, "PIECE", 2, 4),
    ("Печенье овсяное 300 г", "cookies", 460, "PIECE", 16, 4),
    ("Печенье сахарное 200 г", "cookies", 340, "PIECE", 18, 4),
    ("Молоко 2,5% 1 л", "milk-kefir", 520, "PIECE", 30, 5),
    ("Кефир 2,5% 1 л", "milk-kefir", 570, "PIECE", 12, 3),
    ("Сыр полутвёрдый 200 г", "cheese-butter", 1100, "PIECE", 8, 2),
    ("Масло сливочное 180 г", "cheese-butter", 1200, "PIECE", 10, 2),
    ("Йогурт натуральный 200 г", "yogurt-curd", 380, "PIECE", 20, 4),
    ("Творог 5% 200 г", "yogurt-curd", 650, "PIECE", 12, 3),
    ("Картофель", "vegetables", 220, "KG", 25000, 3000),
    ("Морковь", "vegetables", 240, "KG", 18000, 2500),
    ("Лук репчатый", "vegetables", 190, "KG", 15000, 2000),
    ("Помидоры", "vegetables", 950, "KG", 4000, 1000),
    ("Огурцы", "vegetables", 780, "KG", 500, 1000),
    ("Яблоки", "fruit", 750, "KG", 12000, 2000),
    ("Бананы", "fruit", 980, "KG", 8000, 1500),
    ("Груши", "fruit", 1150, "KG", 6000, 1000),
    ("Апельсины", "fruit", 1050, "KG", 7000, 1000),
    ("Салат овощной 250 г", "salads", 850, "PIECE", 7, 2),
    ("Салат картофельный 250 г", "salads", 790, "PIECE", 1, 2),
    ("Плов с курицей 350 г", "hot-meals", 1450, "PIECE", 8, 2),
    ("Гречка с овощами 300 г", "hot-meals", 990, "PIECE", 6, 2),
    ("Самса с картофелем", "baked-goods", 330, "PIECE", 15, 3),
    ("Булочка с корицей", "baked-goods", 280, "PIECE", 15, 3),
    ("Хлеб пшеничный 500 г", "bread", 250, "PIECE", 24, 5),
    ("Лаваш тонкий 200 г", "bread", 320, "PIECE", 12, 3),
    ("Тесто слоёное 500 г", "dough", 750, "PIECE", 10, 2),
    ("Пельмени с курицей 500 г", "dough", 1300, "PIECE", 8, 2),
    ("Вода питьевая 1,5 л", "water", 230, "PIECE", 40, 8),
    ("Вода газированная 1 л", "water", 270, "PIECE", 24, 5),
    ("Сок яблочный 1 л", "juice-soda", 790, "PIECE", 12, 3),
    ("Лимонад 1 л", "juice-soda", 450, "PIECE", 20, 4),
    ("Чай чёрный 100 г", "tea-coffee", 900, "PIECE", 14, 3),
    ("Кофе растворимый 50 г", "tea-coffee", 1450, "PIECE", 8, 2),
    ("Карандаш простой", "stationery", 100, "PIECE", 25, 5),
    ("Ручка синяя", "stationery", 150, "PIECE", 30, 5),
    ("Тетрадь в клетку 48 листов", "stationery", 270, "PIECE", 20, 4),
    ("Зубочистки деревянные 100 шт", "small-household", 180, "PIECE", 12, 3),
    ("Спички 10 коробков", "small-household", 190, "PIECE", 10, 2),
    ("Пакеты для мусора 30 л", "small-household", 420, "PIECE", 14, 3),
    ("Салфетки бумажные 100 шт", "small-household", 250, "PIECE", 20, 4),
    ("Мыло туалетное 90 г", "hygiene", 290, "PIECE", 18, 3),
    ("Зубная паста 75 мл", "hygiene", 650, "PIECE", 12, 3),
    ("Печенье сезонное 150 г", "cookies", 390, "PIECE", 0, 2),
)


def seed_catalog(factory: sessionmaker[Session]) -> dict[str, int]:
    def operation(session: Session) -> dict[str, int]:
        categories = {item.slug: item for item in session.scalars(select(Category))}
        existing_barcodes = set(session.scalars(select(Product.barcode)))
        created_categories = 0
        created_products = 0
        for sort_order, (slug, name, parent_slug) in enumerate(CATEGORIES):
            if slug in categories:
                continue
            category = Category(
                slug=slug,
                name=name,
                sort_order=sort_order,
                parent_id=categories[parent_slug].id if parent_slug else None,
            )
            session.add(category)
            session.flush()
            categories[slug] = category
            created_categories += 1
        for sequence, (name, slug, price, unit, stock, minimum) in enumerate(PRODUCTS, start=1):
            barcode = generate_internal_ean13(sequence)
            if barcode in existing_barcodes:
                continue
            product = Product(
                name=name,
                barcode=barcode,
                category_id=categories[slug].id,
                unit=ProductUnit(unit),
                price_minor=price * 100,
                stock_quantity=stock,
                min_stock_quantity=minimum,
                is_active=sequence != len(PRODUCTS),
            )
            session.add(product)
            session.flush()
            if stock:
                session.add(
                    StockMovement(product_id=product.id, delta=stock, reason=StockReason.RESTOCK)
                )
            created_products += 1
        return {"categories_created": created_categories, "products_created": created_products}

    return run_write(factory, operation)


def main() -> None:
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    try:
        result = seed_catalog(create_session_factory(engine))
        print(
            f"Создано категорий: {result['categories_created']}; "
            f"товаров: {result['products_created']}."
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
````

app/services/auth.py

````python
"""Argon2 credentials, short-lived JWTs, and live role checks for every request."""

import hmac
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from urllib.parse import urlsplit
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.enums import UserRole
from app.core.errors import AppError
from app.db.transactions import run_write
from app.models import User
from app.schemas.auth import CreateUserInput, LoginInput, LoginResponse, UserResponse

TOKEN_ISSUER = "qr-mini-market"
TOKEN_AUDIENCE = "qr-mini-market:shop"
PASSWORD_HASHER = PasswordHasher()
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """Make nonexistent-user verification perform the same expensive operation."""
    return PASSWORD_HASHER.hash(secrets.token_urlsafe(32))


def create_user(factory: sessionmaker[Session], data: CreateUserInput) -> User:
    """Hash outside the write transaction; do not overwrite an existing account."""
    password_hash = PASSWORD_HASHER.hash(data.password.get_secret_value())

    def operation(session: Session) -> User:
        user = User(username=data.username, password_hash=password_hash, role=data.role)
        session.add(user)
        session.flush()
        return user

    try:
        return run_write(factory, operation)
    except IntegrityError:
        raise AppError(
            409, "USERNAME_EXISTS", "Пользователь с таким именем уже существует."
        ) from None


def authenticate(
    factory: sessionmaker[Session], data: LoginInput, settings: Settings
) -> LoginResponse:
    """Verify credentials without holding a database transaction during Argon2."""
    with factory() as session:
        user = session.scalar(select(User).where(User.username == data.username))
        stored_hash = user.password_hash if user is not None else None
    stored_hash = stored_hash if stored_hash is not None else _dummy_hash()
    try:
        valid = PASSWORD_HASHER.verify(stored_hash, data.password.get_secret_value())
    except (VerificationError, InvalidHashError):
        valid = False
    if not valid or user is None or not user.is_active:
        raise AppError(401, "INVALID_CREDENTIALS", "Неверное имя пользователя или пароль.")

    new_hash = (
        PASSWORD_HASHER.hash(data.password.get_secret_value())
        if PASSWORD_HASHER.check_needs_rehash(stored_hash)
        else None
    )

    def confirm(session: Session) -> User:
        current = session.scalar(select(User).where(User.id == user.id).with_for_update())
        if current is None or not current.is_active or current.password_hash != stored_hash:
            raise AppError(401, "INVALID_CREDENTIALS", "Неверное имя пользователя или пароль.")
        if new_hash is not None:
            current.password_hash = new_hash
            session.flush()
        return current

    current = run_write(factory, confirm)
    csrf_token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(current.public_id),
            "iss": TOKEN_ISSUER,
            "aud": TOKEN_AUDIENCE,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
            "jti": secrets.token_urlsafe(24),
            "csrf": csrf_token,
        },
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )
    return LoginResponse(
        user=UserResponse.model_validate(current), access_token=token, csrf_token=csrf_token
    )


def require_same_origin(request: Request) -> None:
    """Reject cross-site browser login attempts, while permitting originless API clients."""
    origin = request.headers.get("origin")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise AppError(403, "CSRF_FAILED", "Недопустимый источник запроса.")
    if origin is None:
        return
    try:
        supplied = urlsplit(origin)
        expected = urlsplit(str(request.base_url))
        supplied_origin = (
            supplied.scheme,
            supplied.hostname,
            supplied.port or _port(supplied.scheme),
        )
        expected_origin = (
            expected.scheme,
            expected.hostname,
            expected.port or _port(expected.scheme),
        )
    except ValueError:
        raise AppError(403, "CSRF_FAILED", "Недопустимый источник запроса.") from None
    if (
        supplied_origin != expected_origin
        or supplied.username is not None
        or supplied.password is not None
        or supplied.path not in ("", "/")
        or supplied.query
        or supplied.fragment
    ):
        raise AppError(403, "CSRF_FAILED", "Недопустимый источник запроса.")


def _port(scheme: str) -> int:
    return 443 if scheme == "https" else 80


def require_user(request: Request) -> User:
    """Return a detached active user; cookie-authenticated writes also require CSRF."""
    authorization = request.headers.get("authorization")
    cookie_auth = authorization is None
    if cookie_auth:
        token = request.cookies.get("access_token", "")
    else:
        parts = authorization.split()
        if len(parts) != 2 or parts[0].casefold() != "bearer":
            raise AppError(401, "UNAUTHORIZED", "Требуется авторизация.")
        token = parts[1]
    settings: Settings = request.app.state.settings
    try:
        claims = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=["HS256"],
            issuer=TOKEN_ISSUER,
            audience=TOKEN_AUDIENCE,
            options={"require": ["exp", "iat", "nbf", "sub", "iss", "aud", "jti", "csrf"]},
        )
        user_uuid = UUID(claims["sub"])
        if not isinstance(claims["csrf"], str) or len(claims["csrf"]) < 32:
            raise ValueError("Invalid CSRF claim")
    except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError):
        raise AppError(401, "UNAUTHORIZED", "Сессия недействительна. Войдите снова.") from None
    if cookie_auth and request.method not in SAFE_METHODS:
        require_same_origin(request)
        header = request.headers.get("x-csrf-token", "")
        cookie = request.cookies.get("csrf_token", "")
        # Encode attacker-controlled Unicode before constant-time comparison.
        if not hmac.compare_digest(
            header.encode(), claims["csrf"].encode()
        ) or not hmac.compare_digest(cookie.encode(), claims["csrf"].encode()):
            raise AppError(403, "CSRF_FAILED", "Обновите страницу и повторите действие.")
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        user = session.scalar(
            select(User).where(User.public_id == user_uuid, User.is_active.is_(True))
        )
        if user is None:
            raise AppError(401, "UNAUTHORIZED", "Сессия недействительна. Войдите снова.")
        session.expunge(user)
        return user


def require_cashier(request: Request) -> User:
    user = require_user(request)
    if user.role not in (UserRole.ADMIN, UserRole.CASHIER):
        raise AppError(403, "FORBIDDEN", "Недостаточно прав.")
    return user


def require_admin(request: Request) -> User:
    user = require_user(request)
    if user.role is not UserRole.ADMIN:
        raise AppError(403, "FORBIDDEN", "Требуются права администратора.")
    return user
````

app/services/catalog.py

````python
"""Catalog operations with transaction ownership and atomic stock adjustments."""

from collections.abc import Callable
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import BigInteger, cast, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.enums import StockReason
from app.core.errors import AppError
from app.core.money import MAX_SAFE_MINOR
from app.db.transactions import run_write
from app.models import Category, Product, StockMovement
from app.models.catalog import MAX_QUANTITY
from app.schemas.catalog import (
    CategoryCreate,
    CategoryPatch,
    ProductCreate,
    ProductPatch,
    StockAdjustment,
)

T = TypeVar("T")


def active_category_ids(session: Session) -> set[int]:
    """A category is available only while every ancestor is active and acyclic."""
    categories = {row.id: row for row in session.scalars(select(Category))}
    available: set[int] = set()
    for category_id in categories:
        current: int | None = category_id
        seen: set[int] = set()
        while current is not None:
            category = categories.get(current)
            if category is None or not category.is_active or current in seen:
                break
            seen.add(current)
            current = category.parent_id
        else:
            available.add(category_id)
    return available


def product_available(session: Session, product: Product) -> bool:
    return product.is_active and product.category_id in active_category_ids(session)


def category_dict(category: Category, public_ids: dict[int, UUID]) -> dict[str, Any]:
    return {
        "public_id": category.public_id,
        "name": category.name,
        "slug": category.slug,
        "parent_id": public_ids.get(category.parent_id),
        "sort_order": category.sort_order,
        "is_active": category.is_active,
    }


def product_dict(product: Product, category_uuid: UUID, public: bool = False) -> dict[str, Any]:
    if product.price_minor > MAX_SAFE_MINOR:
        raise AppError(422, "AMOUNT_TOO_LARGE", "Цена превышает допустимый предел API.")
    available = product.stock_quantity - product.reserved_quantity
    result = {
        "public_id": product.public_id,
        "name": product.name,
        "barcode": product.barcode,
        "category_id": category_uuid,
        "unit": product.unit,
        "price_minor": product.price_minor,
        "description": product.description,
        "in_stock": product.is_active and available > 0,
    }
    if not public:
        result.update(
            stock_quantity=product.stock_quantity,
            available_quantity=available,
            min_stock_quantity=product.min_stock_quantity,
            is_active=product.is_active,
        )
    return result


class CatalogService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    def _write(self, operation: Callable[[Session], T]) -> T:
        try:
            return run_write(self.factory, operation)
        except IntegrityError:
            raise AppError(
                409, "CATALOG_CONFLICT", "Штрихкод или код категории уже используется."
            ) from None

    @staticmethod
    def _category(session: Session, category_uuid: UUID) -> Category:
        category = session.scalar(select(Category).where(Category.public_id == category_uuid))
        if category is None:
            raise AppError(404, "CATEGORY_NOT_FOUND", "Категория не найдена.")
        return category

    @staticmethod
    def _product(session: Session, product_uuid: UUID, lock: bool = False) -> Product:
        if lock:
            session.execute(
                update(Product)
                .where(Product.public_id == product_uuid)
                .values(stock_quantity=Product.stock_quantity)
                .execution_options(synchronize_session=False)
            )
        product = session.scalar(select(Product).where(Product.public_id == product_uuid))
        if product is None:
            raise AppError(404, "PRODUCT_NOT_FOUND", "Товар не найден.")
        return product

    @staticmethod
    def _lock_tree(session: Session) -> None:
        """Serialize tree changes on a common row before checking ancestors."""
        first_id = select(func.min(Category.id)).scalar_subquery()
        session.execute(
            update(Category).where(Category.id == first_id).values(sort_order=Category.sort_order)
        )

    @staticmethod
    def _check_parent(session: Session, category_id: int, parent_id: int | None) -> None:
        parents = dict(session.execute(select(Category.id, Category.parent_id)).all())
        seen = {category_id}
        while parent_id is not None:
            if parent_id in seen:
                raise AppError(
                    409, "CATEGORY_CYCLE", "Категория не может находиться внутри своего потомка."
                )
            seen.add(parent_id)
            parent_id = parents.get(parent_id)

    @staticmethod
    def _category_result(session: Session, category: Category) -> dict[str, Any]:
        public_ids = dict(session.execute(select(Category.id, Category.public_id)).all())
        return category_dict(category, public_ids)

    @staticmethod
    def _product_result(session: Session, product: Product, public: bool = False) -> dict[str, Any]:
        category_uuid = session.scalar(
            select(Category.public_id).where(Category.id == product.category_id)
        )
        return product_dict(product, category_uuid, public)

    def list_categories(
        self, *, public: bool = False, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        with self.factory() as session:
            query = select(Category)
            if public:
                query = query.where(Category.id.in_(active_category_ids(session)))
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            categories = session.scalars(
                query.order_by(Category.sort_order, Category.id).limit(limit).offset(offset)
            )
            public_ids = dict(session.execute(select(Category.id, Category.public_id)).all())
            return {
                "items": [category_dict(row, public_ids) for row in categories],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    def create_category(self, command: CategoryCreate) -> dict[str, Any]:
        def operation(session: Session) -> dict[str, Any]:
            self._lock_tree(session)
            data = command.model_dump(exclude={"parent_id"})
            parent = self._category(session, command.parent_id) if command.parent_id else None
            category = Category(**data, parent_id=parent.id if parent else None)
            session.add(category)
            session.flush()
            return self._category_result(session, category)

        return self._write(operation)

    def update_category(self, category_uuid: UUID, command: CategoryPatch) -> dict[str, Any]:
        def operation(session: Session) -> dict[str, Any]:
            self._lock_tree(session)
            category = self._category(session, category_uuid)
            data = command.model_dump(exclude_unset=True)
            if "parent_id" in data:
                parent = self._category(session, data["parent_id"]) if data["parent_id"] else None
                data["parent_id"] = parent.id if parent else None
                self._check_parent(session, category.id, data["parent_id"])
            for key, value in data.items():
                setattr(category, key, value)
            session.flush()
            return self._category_result(session, category)

        return self._write(operation)

    def delete_category(self, category_uuid: UUID) -> dict[str, Any]:
        return self.update_category(category_uuid, CategoryPatch(is_active=False))

    def list_products(
        self,
        *,
        q: str | None = None,
        category_id: UUID | None = None,
        include_subcategories: bool = False,
        is_active: bool | None = True,
        barcode: str | None = None,
        limit: int = 50,
        offset: int = 0,
        public: bool = False,
    ) -> dict[str, Any]:
        with self.factory() as session:
            query = select(Product, Category.public_id).join(
                Category, Product.category_id == Category.id
            )
            if q is not None and q.strip():
                query = query.where(
                    Product.name_normalized.contains(q.strip().casefold(), autoescape=True)
                )
            if barcode is not None:
                query = query.where(Product.barcode == barcode)
            if is_active is not None or public:
                query = query.where(Product.is_active.is_(True if public else is_active))
            if public or is_active is True:
                query = query.where(Product.category_id.in_(active_category_ids(session)))
            if category_id is not None:
                category = self._category(session, category_id)
                selected = {category.id}
                if include_subcategories:
                    parents = session.execute(select(Category.id, Category.parent_id)).all()
                    while True:
                        descendants = {row.id for row in parents if row.parent_id in selected}
                        updated = selected | descendants
                        if updated == selected:
                            break
                        selected = updated
                query = query.where(Product.category_id.in_(selected))
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            rows = session.execute(
                query.order_by(Product.name_normalized, Product.id).limit(limit).offset(offset)
            )
            return {
                "items": [product_dict(product, uuid, public) for product, uuid in rows],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    def get_product(self, product_uuid: UUID) -> dict[str, Any]:
        with self.factory() as session:
            return self._product_result(session, self._product(session, product_uuid))

    def get_by_barcode(self, barcode: str) -> dict[str, Any]:
        with self.factory() as session:
            product = session.scalar(select(Product).where(Product.barcode == barcode))
            if product is None or not product_available(session, product):
                raise AppError(404, "PRODUCT_NOT_FOUND", "Активный товар не найден.")
            return self._product_result(session, product)

    def create_product(self, command: ProductCreate) -> dict[str, Any]:
        def operation(session: Session) -> dict[str, Any]:
            category = self._category(session, command.category_id)
            product = Product(
                **command.model_dump(exclude={"category_id"}), category_id=category.id
            )
            session.add(product)
            session.flush()
            if product.stock_quantity:
                session.add(
                    StockMovement(
                        product_id=product.id,
                        delta=product.stock_quantity,
                        reason=StockReason.RESTOCK,
                    )
                )
                session.flush()
            return self._product_result(session, product)

        return self._write(operation)

    def update_product(self, product_uuid: UUID, command: ProductPatch) -> dict[str, Any]:
        def operation(session: Session) -> dict[str, Any]:
            product = self._product(session, product_uuid, lock=True)
            data = command.model_dump(exclude_unset=True)
            if "unit" in data and data["unit"] != product.unit:
                raise AppError(
                    409, "UNIT_IMMUTABLE", "Для другой единицы измерения создайте отдельный товар."
                )
            if "category_id" in data:
                data["category_id"] = self._category(session, data["category_id"]).id
            for key, value in data.items():
                setattr(product, key, value)
            session.flush()
            return self._product_result(session, product)

        return self._write(operation)

    def delete_product(self, product_uuid: UUID) -> dict[str, Any]:
        return self.update_product(product_uuid, ProductPatch(is_active=False))

    def adjust_stock(self, product_uuid: UUID, command: StockAdjustment) -> dict[str, Any]:
        def operation(session: Session) -> dict[str, Any]:
            product = self._product(session, product_uuid, lock=True)
            # Widen before arithmetic so PostgreSQL can evaluate the range guard.
            new_stock = cast(Product.stock_quantity, BigInteger) + command.delta
            result = session.execute(
                update(Product)
                .where(
                    Product.id == product.id,
                    new_stock >= Product.reserved_quantity,
                    new_stock <= MAX_QUANTITY,
                )
                .values(stock_quantity=new_stock)
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                raise AppError(
                    409,
                    "STOCK_CONFLICT",
                    "Остаток не может быть меньше резерва или превышать предел.",
                )
            session.add(
                StockMovement(product_id=product.id, delta=command.delta, reason=command.reason)
            )
            session.flush()
            session.refresh(product)
            return self._product_result(session, product)

        return self._write(operation)
````

app/services/orders.py

````python
"""Orders use price snapshots, serialized mutations, and server-calculated totals."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.enums import OrderStatus, PaymentStatus
from app.core.errors import AppError
from app.core.money import MAX_SAFE_MINOR, calculate_line_total
from app.db.transactions import run_write
from app.models import Order, OrderItem, Payment, Product
from app.models.catalog import MAX_QUANTITY
from app.schemas.orders import ItemAdd, ItemPatch, OrderCreate
from app.services.catalog import product_available


def payment_summary(payment: Payment | None, order_uuid: UUID) -> dict[str, Any] | None:
    if payment is None:
        return None
    seconds_left = 0
    if payment.status is PaymentStatus.PENDING and payment.expires_at is not None:
        seconds_left = max(0, int((payment.expires_at - datetime.now(UTC)).total_seconds()))
    return {
        "public_id": payment.public_id,
        "order_id": order_uuid,
        "status": payment.status,
        "amount_minor": payment.amount_minor,
        "currency": payment.currency,
        "pay_url": payment.pay_url,
        "expires_at": payment.expires_at,
        "seconds_left": seconds_left,
        "failure_reason": payment.failure_reason,
        "needs_review": payment.needs_review,
    }


def order_dict(session: Session, order: Order) -> dict[str, Any]:
    rows = session.execute(
        select(OrderItem, Product.public_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(OrderItem.order_id == order.id)
        .order_by(OrderItem.id)
    )
    payment = session.scalar(
        select(Payment).where(Payment.order_id == order.id).order_by(Payment.id.desc()).limit(1)
    )
    return {
        "public_id": order.public_id,
        "number": order.number,
        "terminal_code": order.terminal_code,
        "status": order.status,
        "total_minor": order.total_minor,
        "currency": order.currency,
        "created_at": order.created_at,
        "paid_at": order.paid_at,
        "cancelled_at": order.cancelled_at,
        "items": [
            {
                "public_id": item.public_id,
                "product_id": product_uuid,
                "product_name": item.product_name,
                "barcode": item.barcode,
                "unit": item.unit,
                "unit_price_minor": item.unit_price_minor,
                "quantity": item.quantity,
                "line_total_minor": item.line_total_minor,
            }
            for item, product_uuid in rows
        ],
        "payment": payment_summary(payment, order.public_id),
    }


class OrderService:
    def __init__(self, factory: sessionmaker[Session], currency: str = "KZT") -> None:
        self.factory = factory
        self.currency = currency

    @staticmethod
    def _order(session: Session, order_uuid: UUID, *, editable: bool = False) -> Order:
        if editable:
            result = session.execute(
                update(Order)
                .where(Order.public_id == order_uuid, Order.status == OrderStatus.OPEN)
                .values(updated_at=datetime.now(UTC))
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                existing = session.scalar(select(Order.id).where(Order.public_id == order_uuid))
                if existing is not None:
                    raise AppError(
                        409, "ORDER_NOT_OPEN", "Чек нельзя изменить в текущем состоянии."
                    )
        order = session.scalar(select(Order).where(Order.public_id == order_uuid))
        if order is None:
            raise AppError(404, "ORDER_NOT_FOUND", "Чек не найден.")
        return order

    @staticmethod
    def _item(session: Session, order: Order, item_uuid: UUID) -> OrderItem:
        item = session.scalar(
            select(OrderItem).where(
                OrderItem.order_id == order.id, OrderItem.public_id == item_uuid
            )
        )
        if item is None:
            raise AppError(404, "ITEM_NOT_FOUND", "Позиция чека не найдена.")
        return item

    @staticmethod
    def _check_quantity(session: Session, product: Product, quantity: int) -> None:
        if not product_available(session, product):
            raise AppError(409, "PRODUCT_INACTIVE", "Товар или его категория недоступны.")
        if quantity > MAX_QUANTITY:
            raise AppError(422, "QUANTITY_TOO_LARGE", "Количество превышает допустимый предел.")
        if quantity > product.stock_quantity - product.reserved_quantity:
            raise AppError(
                409,
                "INSUFFICIENT_STOCK",
                "Недостаточно доступного остатка.",
                {"product_id": str(product.public_id)},
            )

    @staticmethod
    def _line_total(item: OrderItem) -> int:
        total = calculate_line_total(item.unit, item.unit_price_minor, item.quantity)
        if total > MAX_SAFE_MINOR or item.unit_price_minor > MAX_SAFE_MINOR:
            raise AppError(422, "AMOUNT_TOO_LARGE", "Сумма позиции превышает допустимый предел.")
        return total

    @staticmethod
    def _recalculate(session: Session, order: Order) -> None:
        session.flush()
        amounts = session.scalars(
            select(OrderItem.line_total_minor).where(OrderItem.order_id == order.id)
        )
        # Python integers detect overflow before a database aggregate can overflow.
        total = sum(amounts)
        if total > MAX_SAFE_MINOR:
            raise AppError(422, "AMOUNT_TOO_LARGE", "Сумма чека превышает допустимый предел.")
        order.total_minor = total
        session.flush()

    def create_order(self, command: OrderCreate, cashier_id: int | None = None) -> dict[str, Any]:
        def operation(session: Session) -> dict[str, Any]:
            active = session.scalar(
                select(Order).where(
                    Order.terminal_code == command.terminal_code,
                    Order.status.in_([OrderStatus.OPEN, OrderStatus.PENDING_PAYMENT]),
                )
            )
            if active is not None:
                raise AppError(
                    409,
                    "ACTIVE_ORDER_EXISTS",
                    "На терминале уже есть открытый чек.",
                    {"order_id": str(active.public_id)},
                )
            order_uuid = uuid4()
            order = Order(
                public_id=order_uuid,
                number=f"{datetime.now(UTC):%Y%m%d}-{order_uuid.hex}",
                terminal_code=command.terminal_code,
                currency=self.currency,
                status=OrderStatus.OPEN,
                total_minor=0,
                cashier_id=cashier_id,
            )
            session.add(order)
            session.flush()
            return order_dict(session, order)

        try:
            return run_write(self.factory, operation)
        except IntegrityError:
            raise AppError(
                409, "ACTIVE_ORDER_EXISTS", "На терминале уже есть открытый чек."
            ) from None

    def get_order(self, order_uuid: UUID) -> dict[str, Any]:
        with self.factory() as session:
            return order_dict(session, self._order(session, order_uuid))

    def list_orders(
        self,
        *,
        terminal_code: str | None = None,
        status: OrderStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        with self.factory() as session:
            query = select(Order)
            if terminal_code is not None:
                query = query.where(Order.terminal_code == terminal_code)
            if status is not None:
                query = query.where(Order.status == status)
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            orders = session.scalars(query.order_by(Order.id.desc()).limit(limit).offset(offset))
            return {
                "items": [order_dict(session, order) for order in orders],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    def add_item(self, order_uuid: UUID, command: ItemAdd) -> dict[str, Any]:
        def operation(session: Session) -> dict[str, Any]:
            order = self._order(session, order_uuid, editable=True)
            query = (
                select(Product).where(Product.barcode == command.barcode)
                if command.barcode
                else select(Product).where(Product.public_id == command.product_id)
            )
            product = session.scalar(query)
            if product is None:
                raise AppError(404, "PRODUCT_NOT_FOUND", "Товар не найден.")
            item = session.scalar(
                select(OrderItem).where(
                    OrderItem.order_id == order.id, OrderItem.product_id == product.id
                )
            )
            quantity = command.quantity + (item.quantity if item else 0)
            self._check_quantity(session, product, quantity)
            if item is None:
                item = OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    product_name=product.name,
                    barcode=product.barcode,
                    unit=product.unit,
                    unit_price_minor=product.price_minor,
                    quantity=quantity,
                )
                session.add(item)
            else:
                item.quantity = quantity
            item.line_total_minor = self._line_total(item)
            self._recalculate(session, order)
            return order_dict(session, order)

        return run_write(self.factory, operation)

    def update_item(self, order_uuid: UUID, item_uuid: UUID, command: ItemPatch) -> dict[str, Any]:
        def operation(session: Session) -> dict[str, Any]:
            order = self._order(session, order_uuid, editable=True)
            item = self._item(session, order, item_uuid)
            product = session.get(Product, item.product_id)
            self._check_quantity(session, product, command.quantity)
            item.quantity = command.quantity
            item.line_total_minor = self._line_total(item)
            self._recalculate(session, order)
            return order_dict(session, order)

        return run_write(self.factory, operation)

    def remove_item(self, order_uuid: UUID, item_uuid: UUID) -> dict[str, Any]:
        def operation(session: Session) -> dict[str, Any]:
            order = self._order(session, order_uuid, editable=True)
            session.delete(self._item(session, order, item_uuid))
            self._recalculate(session, order)
            return order_dict(session, order)

        return run_write(self.factory, operation)

    def receipt(self, order_uuid: UUID) -> dict[str, Any]:
        result = self.get_order(order_uuid)
        if result["status"] is not OrderStatus.PAID:
            raise AppError(409, "RECEIPT_NOT_READY", "Чек доступен после успешной оплаты.")
        return {**result, "payment_method": "QR", "disclaimer": "Учебный проект, не фискальный чек"}

    def display(self, terminal_code: str) -> dict[str, Any]:
        with self.factory() as session:
            order = session.scalar(
                select(Order)
                .where(
                    Order.terminal_code == terminal_code,
                    Order.status.in_([OrderStatus.OPEN, OrderStatus.PENDING_PAYMENT]),
                )
                .order_by(Order.id.desc())
                .limit(1)
            )
            if order is None:
                order = session.scalar(
                    select(Order)
                    .where(
                        Order.terminal_code == terminal_code,
                        Order.status == OrderStatus.PAID,
                        Order.paid_at >= datetime.now(UTC) - timedelta(seconds=15),
                    )
                    .order_by(Order.paid_at.desc(), Order.id.desc())
                    .limit(1)
                )
            if order is None:
                return {
                    "state": "idle",
                    "order": None,
                    "payment": None,
                    "seconds_left": 0,
                    "failure_reason": None,
                }
            result = order_dict(session, order)
            payment = result["payment"]
            state = "cart"
            failure_reason = None
            if order.status is OrderStatus.PAID:
                state = "paid"
            elif order.status is OrderStatus.PENDING_PAYMENT:
                state = "awaiting_payment"
            elif payment and payment["status"] in {
                PaymentStatus.FAILED,
                PaymentStatus.EXPIRED,
                PaymentStatus.CANCELLED,
            }:
                state = "payment_failed"
                failure_reason = {
                    PaymentStatus.EXPIRED: "expired",
                    PaymentStatus.CANCELLED: "cancelled",
                }.get(payment["status"], "declined")
            return {
                "state": state,
                "order": result,
                "payment": payment,
                "seconds_left": payment["seconds_left"] if payment else 0,
                "failure_reason": failure_reason,
            }
````

app/services/payments.py

````python
"""Reservation, external invoice creation, and atomic final payment transitions."""

import hashlib
import hmac
import logging
import time
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.enums import OrderStatus, PaymentStatus, StockReason
from app.core.errors import AppError
from app.core.money import MAX_SAFE_MINOR, calculate_line_total
from app.db.transactions import run_write
from app.models import Category, Order, OrderItem, Payment, PaymentEvent, Product, StockMovement
from app.providers.base import BankStatus, InvoiceSnapshot, PaymentProvider, ProviderUnavailable
from app.schemas.payments import BankEvent, EventData, PaymentRead

logger = logging.getLogger(__name__)
EVENT_STATUSES = {
    "invoice.paid": PaymentStatus.SUCCEEDED,
    "invoice.failed": PaymentStatus.FAILED,
    "invoice.expired": PaymentStatus.EXPIRED,
    "invoice.cancelled": PaymentStatus.CANCELLED,
}


class PaymentService:
    def __init__(
        self, factory: sessionmaker[Session], provider: PaymentProvider, settings: Settings
    ) -> None:
        self.factory, self.provider, self.settings = factory, provider, settings

    @staticmethod
    def _payment(session: Session, public_id: UUID, *, lock: bool = False) -> Payment:
        query = select(Payment).where(Payment.public_id == public_id)
        if lock:
            query = query.with_for_update()
        payment = session.scalar(query)
        if payment is None:
            raise AppError(404, "PAYMENT_NOT_FOUND", "Платёж не найден.")
        return payment

    @staticmethod
    def _dto(session: Session, payment: Payment) -> dict:
        order = session.get(Order, payment.order_id)
        remaining = 0
        if payment.status is PaymentStatus.PENDING and payment.expires_at is not None:
            remaining = max(0, int((payment.expires_at - datetime.now(UTC)).total_seconds()))
        return PaymentRead(
            public_id=payment.public_id,
            order_id=order.public_id,
            status=payment.status,
            amount_minor=payment.amount_minor,
            currency=payment.currency,
            pay_url=payment.pay_url,
            expires_at=payment.expires_at,
            seconds_left=remaining,
            failure_reason=payment.failure_reason,
            needs_review=payment.needs_review,
        ).model_dump(mode="json")

    def get_payment(self, public_id: UUID) -> dict:
        with self.factory() as session:
            return self._dto(session, self._payment(session, public_id))

    @staticmethod
    def _active_category(session: Session, category_id: int) -> bool:
        visited: set[int] = set()
        while category_id is not None:
            if category_id in visited:
                return False
            visited.add(category_id)
            category = session.scalar(
                select(Category).where(Category.id == category_id).with_for_update()
            )
            if category is None or not category.is_active:
                return False
            category_id = category.parent_id
        return True

    def checkout(self, order_uuid: UUID) -> dict:
        def prepare(session: Session) -> UUID:
            order = session.scalar(
                select(Order).where(Order.public_id == order_uuid).with_for_update()
            )
            if order is None:
                raise AppError(404, "ORDER_NOT_FOUND", "Чек не найден.")
            pending = session.scalar(
                select(Payment).where(
                    Payment.order_id == order.id, Payment.status == PaymentStatus.PENDING
                )
            )
            if pending is not None:
                return pending.public_id
            changed = session.execute(
                update(Order)
                .where(Order.id == order.id, Order.status == OrderStatus.OPEN)
                .values(status=OrderStatus.PENDING_PAYMENT, updated_at=datetime.now(UTC))
            )
            if changed.rowcount != 1:
                raise AppError(409, "ORDER_NOT_OPEN", "Чек нельзя отправить на оплату.")
            items = list(
                session.scalars(
                    select(OrderItem)
                    .where(OrderItem.order_id == order.id)
                    .order_by(OrderItem.product_id)
                )
            )
            if not items:
                raise AppError(409, "EMPTY_ORDER", "Добавьте товары в чек.")
            total = 0
            missing = []
            for item in items:
                item.line_total_minor = calculate_line_total(
                    item.unit, item.unit_price_minor, item.quantity
                )
                total += item.line_total_minor
                product = session.get(Product, item.product_id)
                if product is None or not self._active_category(session, product.category_id):
                    missing.append({"product_id": str(product.public_id) if product else None})
                    continue
                reserved = session.execute(
                    update(Product)
                    .where(
                        Product.id == item.product_id,
                        Product.category_id == product.category_id,
                        Product.is_active.is_(True),
                        Product.unit == item.unit,
                        Product.stock_quantity - Product.reserved_quantity >= item.quantity,
                    )
                    .values(reserved_quantity=Product.reserved_quantity + item.quantity)
                )
                if reserved.rowcount != 1:
                    missing.append({"product_id": str(product.public_id)})
            if missing:
                raise AppError(
                    409,
                    "INSUFFICIENT_STOCK",
                    "Товара недостаточно или он недоступен.",
                    {
                        "items": missing,
                    },
                )
            if not 0 < total <= MAX_SAFE_MINOR:
                raise AppError(
                    422, "INVALID_PAYMENT_AMOUNT", "Сумма оплаты вне допустимого диапазона."
                )
            order.total_minor = total
            payment = Payment(
                order_id=order.id,
                provider="mock_bank",
                amount_minor=total,
                currency=order.currency,
                status=PaymentStatus.PENDING,
                expires_at=datetime.now(UTC) + timedelta(seconds=self.settings.payment_ttl_seconds),
            )
            session.add(payment)
            session.flush()
            return payment.public_id

        public_id = run_write(self.factory, prepare)
        self._ensure_invoice(public_id)
        return self.get_payment(public_id)

    @staticmethod
    def _mark_review(payment: Payment, reason: str) -> None:
        payment.needs_review = True
        payment.review_reason = reason
        logger.warning("Payment requires review: %s (%s)", payment.public_id, reason)

    def _provider_error(
        self,
        public_id: UUID,
        failure: ProviderUnavailable,
        *,
        creating: bool,
        attempt: int | None = None,
    ) -> None:
        logger.warning("Payment provider request failed: %s", public_id)
        if creating and attempt == 1 and failure.definitely_not_created:

            def compensate(session: Session) -> None:
                payment = self._payment(session, public_id, lock=True)
                if (
                    payment.status is not PaymentStatus.PENDING
                    or payment.provider_invoice_id
                    or payment.creation_attempts != attempt
                ):
                    return
                event_id = str(uuid5(NAMESPACE_URL, f"provider-unavailable:{public_id}"))
                existing = session.scalar(
                    select(PaymentEvent.id).where(
                        PaymentEvent.provider == "mock_bank",
                        PaymentEvent.provider_event_id == event_id,
                    )
                )
                if existing is None:
                    session.add(
                        PaymentEvent(
                            payment_id=payment.id,
                            provider="mock_bank",
                            provider_event_id=event_id,
                            event_type="provider.unavailable",
                            raw_body="{}",
                            signature_valid=False,
                            outcome="applied",
                        )
                    )
                    self._finalize(session, payment, PaymentStatus.FAILED, "provider_unavailable")

            run_write(self.factory, compensate)
        raise AppError(
            503,
            "PROVIDER_UNAVAILABLE",
            "Банк недоступен. Проверьте оплату повторно.",
            {
                "payment_id": str(public_id),
            },
        ) from None

    def _ensure_invoice(self, public_id: UUID) -> None:
        def claim(session: Session):
            payment = self._payment(session, public_id, lock=True)
            if (
                payment.provider_invoice_id is not None
                or payment.status is not PaymentStatus.PENDING
            ):
                return
            now = datetime.now(UTC)
            if (
                payment.creation_started_at is not None
                and payment.creation_started_at > now - timedelta(seconds=30)
            ):
                return
            payment.creation_started_at = now
            payment.creation_attempts += 1
            order = session.get(Order, payment.order_id)
            parameters = {
                "amount_minor": payment.amount_minor,
                "currency": payment.currency,
                "merchant_reference": payment.public_id,
                "description": f"Чек {order.number}",
                "ttl_seconds": self.settings.payment_ttl_seconds,
            }
            return parameters, payment.creation_attempts

        claimed = run_write(self.factory, claim)
        if claimed is None:
            return
        parameters, attempt = claimed
        try:
            try:
                invoice = self.provider.create_invoice(**parameters)
            except ProviderUnavailable as exc:
                self._provider_error(public_id, exc, creating=True, attempt=attempt)
                return
            self._accept_snapshot(public_id, invoice)
        finally:

            def release(session: Session) -> None:
                session.execute(
                    update(Payment)
                    .where(
                        Payment.public_id == public_id,
                        Payment.creation_attempts == attempt,
                    )
                    .values(creation_started_at=None)
                )

            run_write(self.factory, release)

    def _accept_snapshot(self, public_id: UUID, invoice: InvoiceSnapshot) -> None:
        def accept(session: Session) -> str:
            payment = self._payment(session, public_id, lock=True)
            if (
                invoice.merchant_reference != payment.public_id
                or invoice.amount_minor != payment.amount_minor
                or invoice.currency != payment.currency
                or payment.provider_invoice_id not in (None, str(invoice.invoice_id))
            ):
                self._mark_review(payment, "provider_snapshot_mismatch")
                return "mismatch"
            other_owner = session.scalar(
                select(Payment.id).where(
                    Payment.provider_invoice_id == str(invoice.invoice_id),
                    Payment.id != payment.id,
                )
            )
            if other_owner is not None:
                self._mark_review(payment, "provider_invoice_collision")
                return "mismatch"
            payment.provider_invoice_id = str(invoice.invoice_id)
            payment.pay_url = str(invoice.pay_url)
            payment.expires_at = invoice.expires_at
            session.flush()
            waiting = list(
                session.scalars(
                    select(PaymentEvent)
                    .where(
                        PaymentEvent.payment_id == payment.id,
                        PaymentEvent.outcome == "awaiting_invoice",
                    )
                    .order_by(PaymentEvent.id)
                )
            )
            for stored in waiting:
                self._apply_event(
                    session, BankEvent.model_validate_json(stored.raw_body), stored.raw_body
                )
            if invoice.status is not BankStatus.CREATED:
                event = BankEvent(
                    event_id=invoice.event_id,
                    type=f"invoice.{invoice.status.value.lower()}",
                    created_at=invoice.paid_at or datetime.now(UTC),
                    data=EventData(
                        invoice_id=invoice.invoice_id,
                        merchant_reference=invoice.merchant_reference,
                        amount_minor=invoice.amount_minor,
                        currency=invoice.currency,
                        failure_reason=invoice.failure_reason,
                    ),
                )
                return self._apply_event(session, event, event.model_dump_json())
            return "accepted"

        outcome = self._write_event(accept)
        if outcome == "mismatch":
            raise AppError(422, "PAYMENT_MISMATCH", "Данные банка не совпадают. Нужна проверка.")

    def _finalize(
        self,
        session: Session,
        payment: Payment,
        status: PaymentStatus,
        failure_reason: str | None,
        paid_at: datetime | None = None,
    ) -> None:
        """The only method that changes a pending payment and its reserved inventory."""
        order = session.scalar(select(Order).where(Order.id == payment.order_id).with_for_update())
        if order.status is not OrderStatus.PENDING_PAYMENT:
            raise AppError(409, "PAYMENT_STATE_CONFLICT", "Состояние оплаты требует проверки.")
        now = datetime.now(UTC)
        succeeded = status is PaymentStatus.SUCCEEDED
        changed = session.execute(
            update(Payment)
            .where(Payment.id == payment.id, Payment.status == PaymentStatus.PENDING)
            .values(
                status=status,
                paid_at=(paid_at or now) if succeeded else None,
                failure_reason=failure_reason,
                updated_at=now,
            )
        )
        if changed.rowcount != 1:
            raise AppError(409, "PAYMENT_STATE_CONFLICT", "Состояние оплаты изменилось.")
        changed = session.execute(
            update(Order)
            .where(Order.id == order.id, Order.status == OrderStatus.PENDING_PAYMENT)
            .values(
                status=OrderStatus.PAID if succeeded else OrderStatus.OPEN,
                paid_at=(paid_at or now) if succeeded else None,
                updated_at=now,
            )
        )
        if changed.rowcount != 1:
            raise AppError(409, "PAYMENT_STATE_CONFLICT", "Состояние чека изменилось.")
        for item in session.scalars(select(OrderItem).where(OrderItem.order_id == order.id)):
            values = {"reserved_quantity": Product.reserved_quantity - item.quantity}
            if succeeded:
                values["stock_quantity"] = Product.stock_quantity - item.quantity
            changed = session.execute(
                update(Product)
                .where(
                    Product.id == item.product_id,
                    Product.reserved_quantity >= item.quantity,
                    Product.stock_quantity >= item.quantity,
                )
                .values(**values)
            )
            if changed.rowcount != 1:
                raise AppError(409, "RESERVATION_CONFLICT", "Резерв товара требует проверки.")
            if succeeded:
                session.add(
                    StockMovement(
                        product_id=item.product_id,
                        delta=-item.quantity,
                        reason=StockReason.SALE,
                        order_id=order.id,
                    )
                )
        logger.info("Payment transition: %s -> %s", payment.public_id, status.value)

    def _apply_event(self, session: Session, event: BankEvent, raw: str) -> str:
        stored = session.scalar(
            select(PaymentEvent)
            .where(
                PaymentEvent.provider == "mock_bank",
                PaymentEvent.provider_event_id == str(event.event_id),
            )
            .with_for_update()
        )
        if stored is not None and stored.outcome != "awaiting_invoice":
            return "duplicate"
        by_invoice = session.scalar(
            select(Payment)
            .where(Payment.provider_invoice_id == str(event.data.invoice_id))
            .with_for_update()
        )
        payment = by_invoice or session.scalar(
            select(Payment)
            .where(Payment.public_id == event.data.merchant_reference)
            .with_for_update()
        )
        if stored is None:
            stored = PaymentEvent(
                provider="mock_bank",
                provider_event_id=str(event.event_id),
                event_type=event.type,
                raw_body=raw,
                signature_valid=True,
                outcome="received",
                payment_id=payment.id if payment is not None else None,
            )
            session.add(stored)
            session.flush()
        if payment is None:
            stored.outcome = "unknown_payment"
            return stored.outcome
        if (
            event.data.merchant_reference != payment.public_id
            or event.data.amount_minor != payment.amount_minor
            or event.data.currency != payment.currency
            or payment.provider_invoice_id not in (None, str(event.data.invoice_id))
        ):
            self._mark_review(payment, "event_data_mismatch")
            stored.outcome = "mismatch"
            return stored.outcome
        if payment.provider_invoice_id is None:
            stored.outcome = "awaiting_invoice"
            return stored.outcome
        status = EVENT_STATUSES[event.type]
        if payment.status is not PaymentStatus.PENDING:
            if status is PaymentStatus.SUCCEEDED and payment.status is not PaymentStatus.SUCCEEDED:
                self._mark_review(payment, "late_success")
                stored.outcome = "late_success"
            else:
                stored.outcome = "already_final"
            return stored.outcome
        try:
            with session.begin_nested():
                self._finalize(
                    session,
                    payment,
                    status,
                    event.data.failure_reason,
                    event.created_at if status is PaymentStatus.SUCCEEDED else None,
                )
        except AppError:
            self._mark_review(payment, "reservation_or_order_conflict")
            stored.outcome = "state_conflict"
        else:
            stored.outcome = "applied"
        return stored.outcome

    def _write_event(self, operation):
        try:
            return run_write(self.factory, operation)
        except IntegrityError:
            # PostgreSQL may race on event uniqueness; retry in a new transaction
            # so the durable winner is seen and no stock mutation can run twice.
            return run_write(self.factory, operation)

    def process_webhook(self, raw_body: bytes, timestamp: str, signature: str) -> dict:
        if (
            len(raw_body) > 16384
            or len(timestamp) > 16
            or len(signature) != 64
            or not signature.isascii()
        ):
            raise AppError(401, "INVALID_SIGNATURE", "Неверная подпись уведомления.")
        try:
            issued_at = int(timestamp)
        except ValueError:
            raise AppError(401, "INVALID_SIGNATURE", "Неверная подпись уведомления.") from None
        expected = hmac.new(
            self.settings.webhook_secret.get_secret_value().encode(),
            timestamp.encode() + b"." + raw_body,
            hashlib.sha256,
        ).hexdigest()
        if abs(time.time() - issued_at) > 300 or not hmac.compare_digest(expected, signature):
            logger.warning("Rejected invalid or expired bank notification signature")
            raise AppError(401, "INVALID_SIGNATURE", "Неверная подпись уведомления.")
        try:
            event = BankEvent.model_validate_json(raw_body)
            raw = raw_body.decode("utf-8")
        except (ValueError, ValidationError):
            raise AppError(422, "INVALID_WEBHOOK", "Некорректное уведомление банка.") from None
        outcome = self._write_event(lambda session: self._apply_event(session, event, raw))
        if outcome == "mismatch":
            raise AppError(422, "PAYMENT_MISMATCH", "Данные оплаты не совпадают. Нужна проверка.")
        return {"accepted": True, "outcome": outcome}

    def refresh(self, public_id: UUID) -> dict:
        self._ensure_invoice(public_id)
        with self.factory() as session:
            payment = self._payment(session, public_id)
            invoice_id = payment.provider_invoice_id
            if payment.status is not PaymentStatus.PENDING or invoice_id is None:
                return self._dto(session, payment)
        try:
            invoice = self.provider.get_invoice_status(UUID(invoice_id))
        except ProviderUnavailable as exc:
            self._provider_error(public_id, exc, creating=False)
            raise AssertionError("Unreachable") from None
        self._accept_snapshot(public_id, invoice)
        return self.get_payment(public_id)

    def cancel(self, public_id: UUID) -> dict:
        self._ensure_invoice(public_id)
        with self.factory() as session:
            payment = self._payment(session, public_id)
            if payment.status is PaymentStatus.SUCCEEDED:
                raise AppError(409, "ALREADY_PAID", "Чек уже оплачен.")
            if payment.status is not PaymentStatus.PENDING:
                return self._dto(session, payment)
            invoice_id = payment.provider_invoice_id
        if invoice_id is None:
            raise AppError(409, "INVOICE_NOT_READY", "Создание счёта ещё не завершено.")
        try:
            invoice = self.provider.cancel_invoice(UUID(invoice_id))
        except ProviderUnavailable as exc:
            self._provider_error(public_id, exc, creating=False)
            raise AssertionError("Unreachable") from None
        self._accept_snapshot(public_id, invoice)
        result = self.get_payment(public_id)
        if result["status"] == PaymentStatus.SUCCEEDED:
            raise AppError(409, "ALREADY_PAID", "Чек уже оплачен.")
        if result["status"] == PaymentStatus.PENDING:
            raise AppError(503, "CANCELLATION_UNCONFIRMED", "Банк ещё не подтвердил отмену.")
        return result

    def cancel_order(self, order_uuid: UUID) -> dict:
        with self.factory() as session:
            order = session.scalar(select(Order).where(Order.public_id == order_uuid))
            if order is None:
                raise AppError(404, "ORDER_NOT_FOUND", "Чек не найден.")
            pending = session.scalar(
                select(Payment).where(
                    Payment.order_id == order.id, Payment.status == PaymentStatus.PENDING
                )
            )
            payment_uuid = pending.public_id if pending else None
        if payment_uuid is not None:
            self.cancel(payment_uuid)

        def cancel_open(session: Session) -> None:
            order = session.scalar(
                select(Order).where(Order.public_id == order_uuid).with_for_update()
            )
            if order.status is OrderStatus.CANCELLED:
                return
            changed = session.execute(
                update(Order)
                .where(
                    Order.id == order.id,
                    Order.status == OrderStatus.OPEN,
                )
                .values(
                    status=OrderStatus.CANCELLED,
                    cancelled_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
            if changed.rowcount != 1:
                code = (
                    "ALREADY_PAID" if order.status is OrderStatus.PAID else "ORDER_STATE_CONFLICT"
                )
                raise AppError(409, code, "Чек нельзя отменить в текущем состоянии.")

        run_write(self.factory, cancel_open)
        from app.services.orders import OrderService

        return OrderService(self.factory).get_order(order_uuid)

    def sweep(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(seconds=self.settings.payment_expiry_grace_seconds)
        with self.factory() as session:
            public_ids = list(
                session.scalars(
                    select(Payment.public_id)
                    .where(
                        Payment.status == PaymentStatus.PENDING,
                        (Payment.expires_at < cutoff) | Payment.provider_invoice_id.is_(None),
                    )
                    .order_by(Payment.id)
                    .limit(100)
                )
            )
        for public_id in public_ids:
            try:
                self.refresh(public_id)
            except AppError:
                logger.warning("Payment reconciliation deferred: %s", public_id)
        return len(public_ids)
````

app/services/qr_service.py

````python
"""Generate a high contrast QR image without storing payment links on disk."""

from io import BytesIO

import qrcode
from qrcode.constants import ERROR_CORRECT_M


def make_qr_png(data: str) -> bytes:
    if not isinstance(data, str) or not data or len(data) > 2048:
        raise ValueError("QR payload must contain between 1 and 2048 characters")
    qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    qr.box_size = max(10, (300 + qr.modules_count + 7) // (qr.modules_count + 8))
    image = qr.make_image(fill_color="black", back_color="white")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
````

app/services/reports.py

````python
"""Read-only reports over paid snapshots and administrative stock/payment views."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.enums import OrderStatus
from app.core.errors import AppError
from app.models import Category, Order, OrderItem, Payment, Product


def _pagination(limit: int, offset: int) -> None:
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
        raise AppError(
            422, "INVALID_PAGINATION", "Укажите limit от 1 до 100 и offset не меньше нуля."
        )


def sales_report(
    factory: sessionmaker[Session],
    settings: Settings,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    """Use local calendar days, UTC filtering, and exact Python integer accumulation.

    Product names/prices/units are order snapshots. Categories are the current
    catalog assignment because the order schema has no category snapshot.
    """
    timezone = ZoneInfo(settings.timezone)
    last = date_to or datetime.now(timezone).date()
    first = date_from or last.replace(day=1)
    if first > last or (last - first).days >= 366 or last == date.max:
        raise AppError(422, "INVALID_DATE_RANGE", "Укажите период от 1 до 366 дней.")
    try:
        start_utc = datetime.combine(first, time.min, timezone).astimezone(UTC)
        end_utc = datetime.combine(last + timedelta(days=1), time.min, timezone).astimezone(UTC)
    except (OverflowError, ValueError):
        raise AppError(422, "INVALID_DATE_RANGE", "Даты выходят за допустимый диапазон.") from None
    conditions = (
        Order.status == OrderStatus.PAID,
        Order.paid_at >= start_utc,
        Order.paid_at < end_utc,
    )
    days: dict[str, dict] = {}
    categories: dict[str, dict] = {}
    products: dict[tuple[str, str, str], dict] = {}
    count = 0
    revenue = 0
    with factory() as session:
        # One SQL statement shares a single MVCC snapshot under READ COMMITTED.
        # Separate header/item queries could observe a newly paid order differently.
        rows = session.execute(
            select(
                Order.id.label("order_id"),
                Order.paid_at,
                OrderItem.product_name,
                OrderItem.unit,
                OrderItem.quantity,
                OrderItem.line_total_minor,
                Product.public_id,
                Category.public_id.label("category_public_id"),
                Category.name.label("category_name"),
            )
            .select_from(Order)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .join(Product, Product.id == OrderItem.product_id)
            .join(Category, Category.id == Product.category_id)
            .where(*conditions)
            .order_by(Order.id, OrderItem.id)
        ).yield_per(200)
        previous_order = None
        for row in rows:
            day_key = row.paid_at.astimezone(timezone).date().isoformat()
            day = days.setdefault(day_key, {"date": day_key, "orders_count": 0, "revenue_minor": 0})
            if previous_order != row.order_id:
                day["orders_count"] += 1
                count += 1
                previous_order = row.order_id
            day["revenue_minor"] += row.line_total_minor
            revenue += row.line_total_minor
            category_key = str(row.category_public_id)
            category = categories.setdefault(
                category_key,
                {"public_id": category_key, "name": row.category_name, "revenue_minor": 0},
            )
            category["revenue_minor"] += row.line_total_minor
            # Keep historical renamed products or changed units distinguishable.
            product_key = (str(row.public_id), row.product_name, row.unit.value)
            product = products.setdefault(
                product_key,
                {
                    "public_id": str(row.public_id),
                    "name": row.product_name,
                    "unit": row.unit.value,
                    "quantity": 0,
                    "revenue_minor": 0,
                },
            )
            product["quantity"] += row.quantity
            product["revenue_minor"] += row.line_total_minor
    for item in [*days.values(), *categories.values(), *products.values()]:
        item["revenue_minor_text"] = str(item["revenue_minor"])
    return {
        "date_from": first.isoformat(),
        "date_to": last.isoformat(),
        "timezone": settings.timezone,
        "currency": settings.currency,
        "orders_count": count,
        "revenue_minor": revenue,
        "revenue_minor_text": str(revenue),
        "days": sorted(days.values(), key=lambda item: item["date"]),
        "categories": sorted(
            categories.values(), key=lambda item: (-item["revenue_minor"], item["public_id"])
        ),
        "products": sorted(
            products.values(),
            key=lambda item: (-item["revenue_minor"], item["name"], item["public_id"]),
        ),
    }


def low_stock_report(factory: sessionmaker[Session], limit: int = 50, offset: int = 0) -> dict:
    """Include active products whose unreserved stock has reached its threshold."""
    _pagination(limit, offset)
    available = Product.stock_quantity - Product.reserved_quantity
    conditions = (Product.is_active.is_(True), available <= Product.min_stock_quantity)
    with factory() as session:
        total = session.scalar(select(func.count()).select_from(Product).where(*conditions))
        rows = session.execute(
            select(Product, Category.public_id)
            .join(Category, Category.id == Product.category_id)
            .where(*conditions)
            .order_by(available, Product.id)
            .limit(limit)
            .offset(offset)
        )
        items = [
            {
                "public_id": str(product.public_id),
                "name": product.name,
                "barcode": product.barcode,
                "unit": product.unit.value,
                "category_id": str(category_uuid),
                "stock_quantity": product.stock_quantity,
                "available_quantity": product.stock_quantity - product.reserved_quantity,
                "min_stock_quantity": product.min_stock_quantity,
            }
            for product, category_uuid in rows
        ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def payments_review_report(
    factory: sessionmaker[Session], limit: int = 50, offset: int = 0
) -> dict:
    """Expose review reasons to admins without provider identifiers or raw event bodies."""
    _pagination(limit, offset)
    with factory() as session:
        total = session.scalar(
            select(func.count()).select_from(Payment).where(Payment.needs_review.is_(True))
        )
        rows = session.execute(
            select(Payment, Order.public_id)
            .join(Order, Order.id == Payment.order_id)
            .where(Payment.needs_review.is_(True))
            .order_by(Payment.created_at.desc(), Payment.id.desc())
            .limit(limit)
            .offset(offset)
        )
        items = [
            {
                "public_id": str(payment.public_id),
                "order_id": str(order_uuid),
                "status": payment.status.value,
                "amount_minor": payment.amount_minor,
                "currency": payment.currency,
                "needs_review": payment.needs_review,
                "review_reason": payment.review_reason,
                "created_at": payment.created_at,
                "updated_at": payment.updated_at,
            }
            for payment, order_uuid in rows
        ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}
````

app/setup_env.py

````python
"""Create a local configuration once with independent, generated secrets."""

import os
import secrets
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECRET_NAMES = ("BANK_MERCHANT_API_KEY", "WEBHOOK_SECRET", "SECRET_KEY")


def create_env(destination: Path, template: Path) -> bool:
    """Never replace an existing configuration or print its generated values."""
    content = template.read_text(encoding="utf-8")
    for name in SECRET_NAMES:
        content = content.replace(f"{name}=\n", f"{name}={secrets.token_urlsafe(48)}\n")
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        target.write(content)
    return True


def main() -> None:
    created = create_env(PROJECT_ROOT / ".env", PROJECT_ROOT / ".env.example")
    print("Настройки .env созданы." if created else "Файл .env уже существует и сохранён.")


if __name__ == "__main__":
    main()
````

app/static/mark.svg

````xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="18" fill="#64d7bd"/><path d="M13 43V24h7v3c4-5 10-5 13 0 5-6 17-6 17 4v12h-7V32c0-5-8-5-8 0v11h-7V32c0-5-8-5-8 0v11Z" fill="#102830"/><circle cx="51" cy="16" r="5" fill="#f0c977"/></svg>
````

app/static/shop.css

````css
@charset "UTF-8";
:root{--bg:#101a24;--panel:#182530;--panel-raised:#1e2d39;--line:#30404b;--ink:#f1f5f4;--muted:#a0b1bd;--mint:#75ddc4;--gold:#edc67d;--red:#ffa9a3;--radius:18px;--shadow:0 18px 50px #0002;font-family:Inter,"Segoe UI",Arial,sans-serif;color:var(--ink);background:var(--bg);font-synthesis:none;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;min-width:320px}button,input,select,textarea{font:inherit}button,a,input,select,textarea{-webkit-tap-highlight-color:transparent}button{cursor:pointer}a{color:inherit;text-decoration:none}button:disabled{cursor:not-allowed;opacity:.48}button,input,select,textarea{transition:border-color .15s,background .15s,opacity .15s}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:3px solid var(--gold);outline-offset:3px}input,select,textarea{width:100%;border:1px solid var(--line);border-radius:10px;background:#12212c;color:var(--ink);padding:13px 14px;min-height:46px}input::placeholder,textarea::placeholder{color:#8fa3b1}input[type=checkbox]{min-height:18px;width:18px;accent-color:var(--mint)}input[type=date]{min-width:150px}label{display:block;font-size:13px;font-weight:600;color:#cad6dd}label input,label select,label textarea{margin-top:8px}form>label{margin-top:18px}h1,h2,h3,p{margin:0}h1{font-size:35px;letter-spacing:-1.5px;font-weight:650}h2{font-size:20px;letter-spacing:-.4px;font-weight:650}h3{font-size:16px}p{line-height:1.65}small{font-size:12px}[hidden]{display:none!important}.mint{color:var(--mint)}.muted{color:var(--muted);font-size:13px}.eyebrow{display:block;color:var(--mint);font-size:10px;letter-spacing:2px;font-weight:750;margin-bottom:10px}.wide{width:100%}.span-two{grid-column:1/-1}.visually-hidden{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}.skip-link{position:absolute;top:-50px;left:12px;z-index:50;padding:10px;background:var(--mint);color:var(--bg)}.skip-link:focus{top:12px}
.topbar{height:95px;padding:0 4vw;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:40px;background:#121e29}.brand{display:flex;align-items:center;gap:12px;font-size:24px;letter-spacing:-1px;font-weight:750;flex-shrink:0}.brand-mark{display:flex;align-items:center;justify-content:center;width:45px;height:45px;background:var(--mint);border-radius:12px;color:#132b32;font-weight:850;font-size:31px;position:relative;padding-bottom:3px}.brand-mark>span{color:#203d39;position:absolute;right:5px;top:-9px;font-size:27px}.brand-light{font-weight:350;color:#c6d2d9}.brand small{display:block;font-size:7px;letter-spacing:1.9px;color:var(--muted);margin-top:5px}.topbar nav{display:flex;gap:28px;margin:auto;align-items:center}.topbar nav a{padding:15px 0;color:var(--muted);font-size:13px;position:relative}.topbar nav a[aria-current=page],.topbar nav a:hover{color:var(--mint)}.topbar nav a[aria-current=page]::after{content:"";position:absolute;bottom:5px;left:0;right:0;height:2px;background:var(--mint);border-radius:2px}.header-end{display:flex;align-items:center;gap:15px}.user-label{font-size:12px;color:var(--muted)}.demo-badge{font-size:9px;letter-spacing:1.4px;border:1px solid #627260;padding:9px 12px;border-radius:6px;color:var(--gold);white-space:nowrap}.page-shell{max-width:1600px;margin:0 auto;padding:34px 4vw 50px;min-height:calc(100vh - 170px)}.page-heading{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:30px}.heading-actions{display:flex;align-items:center;gap:20px}.heading-dot{display:inline-block;background:var(--mint);width:9px;height:9px;vertical-align:middle;margin-left:10px;border-radius:50%;box-shadow:0 0 0 5px #75ddc410}.terminal-label{font-size:12px;color:var(--muted)}.button{display:inline-flex;align-items:center;justify-content:center;gap:12px;border:1px solid transparent;border-radius:10px;padding:13px 18px;font-size:13px;font-weight:650;min-height:45px;line-height:1.2;white-space:nowrap}.primary{background:var(--mint);color:#102c2f;box-shadow:0 3px 15px #75ddc40b}.primary:hover:not(:disabled){background:#94e9d4}.secondary{background:var(--panel-raised);border-color:var(--line);color:#d6e0e5}.secondary:hover:not(:disabled){border-color:var(--mint)}.ghost{color:var(--muted);background:transparent;border-color:var(--line)}.danger{color:var(--red);border-color:#684044;background:#36272e}.small{padding:8px 11px;min-height:34px;font-size:11px}.icon-button{border:0;background:transparent;color:var(--muted);font-size:24px;padding:4px 10px;border-radius:8px;line-height:1}.panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}.site-footer{max-width:1600px;margin:auto;padding:21px 4vw;display:flex;justify-content:space-between;gap:20px;color:#8296a5;border-top:1px solid #26343e;font-size:10px;letter-spacing:.3px}.notice{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);padding:15px 22px;max-width:min(620px,92vw);border:1px solid var(--mint);background:#1e353a;border-radius:12px;box-shadow:0 10px 45px #0008;z-index:100;font-size:13px;line-height:1.5}.notice.error{background:#3b2830;border-color:var(--red);color:#ffe5e3}.form-error{color:var(--red);background:#382a31;padding:12px;margin:15px 0;border-radius:8px;font-size:13px;line-height:1.5}.field-help{font-size:11px;color:var(--muted);margin:9px 0 20px}.status{display:inline-flex;align-items:center;border-radius:6px;padding:6px 9px;font-size:10px;letter-spacing:.2px;background:#24413f;color:var(--mint);white-space:nowrap}.status.warning{background:#443e2a;color:var(--gold)}.status.failure{background:#462d32;color:var(--red)}.muted-status{background:#2c3943;color:#bcc9d1}.count{font-size:12px;color:var(--muted);font-weight:400;margin-left:5px}.empty-note{color:var(--muted);padding:35px 20px;text-align:center;grid-column:1/-1;font-size:13px}.section-head{display:flex;align-items:center;justify-content:space-between;gap:15px;margin-bottom:22px}.section-head p{margin-top:5px}.pagination{display:flex;align-items:center;justify-content:center;gap:20px;font-size:12px;color:var(--muted);margin-top:24px;min-height:35px}
.cashier-layout{display:grid;grid-template-columns:minmax(0,1fr) 400px;gap:25px;align-items:start}.scan-panel{padding:10px 12px}.scan-form{display:flex;gap:8px;align-items:center}.scan-icon{font-size:30px;color:var(--mint);padding:0 8px}.scan-form input{background:transparent;border:0;min-width:0;padding:10px 4px;font-size:13px}.scan-form .button{font-size:11px;padding:12px 15px}.catalog-toolbar{display:flex;align-items:center;justify-content:space-between;gap:20px;margin:28px 0 18px}.catalog-toolbar input{max-width:260px;font-size:12px;min-height:40px;background:var(--panel)}.category-chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:21px}.category-chips button{border:1px solid var(--line);background:var(--panel);color:var(--muted);border-radius:8px;font-size:11px;padding:9px 12px;min-height:36px}.category-chips button.active{color:var(--mint);border-color:#589786;background:#203936}.category-chips button:hover{border-color:var(--mint)}.category-chips .child-chip{font-size:10px;border-style:dashed}.product-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px}.product-card{position:relative;text-align:left;border:1px solid var(--line);background:var(--panel);border-radius:15px;color:var(--ink);padding:18px;min-height:169px;display:flex;flex-direction:column;align-items:stretch;gap:10px;overflow:hidden}.product-card:hover:not(:disabled){border-color:#6ab6a4;background:#1c2d37;transform:translateY(-2px)}.product-card:disabled{opacity:.6}.product-card .product-art{display:flex;align-items:center;justify-content:center;width:40px;height:40px;background:#293f42;color:var(--mint);border-radius:12px;font-size:20px;font-weight:700}.product-card:nth-child(3n+2) .product-art{background:#3d3b35;color:var(--gold)}.product-card:nth-child(3n+3) .product-art{background:#343a50;color:#b8bde6}.product-card .product-name{font-size:13px;font-weight:600;line-height:1.45;min-height:36px;overflow-wrap:anywhere}.product-price{display:flex;align-items:baseline;justify-content:space-between;gap:4px;margin-top:auto}.product-price strong{font-size:19px;letter-spacing:-.6px;white-space:nowrap}.product-price small{font-size:10px;color:var(--muted)}.product-stock{font-size:10px;color:#aabeb4}.add-circle{position:absolute;top:19px;right:17px;width:25px;height:25px;border:1px solid var(--line);color:var(--mint);border-radius:50%;display:grid;place-items:center;font-size:17px}.order-panel{position:sticky;top:20px;overflow:hidden}.order-header{padding:24px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;gap:10px}.order-header h2{font-size:17px}.order-header .eyebrow{font-size:8px;margin-bottom:8px}.order-empty{min-height:310px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:30px 20px}.empty-symbol{font-size:41px;color:#71978f;margin-bottom:15px}.order-empty h3{margin-bottom:10px}.order-empty p{color:var(--muted);font-size:12px;margin-bottom:22px}.order-items{max-height:450px;overflow:auto}.order-item{padding:19px 22px;border-bottom:1px solid #2c3b45;display:grid;grid-template-columns:1fr auto;gap:9px 12px}.item-name{font-size:13px;font-weight:550;line-height:1.5;overflow-wrap:anywhere}.item-detail{font-size:11px;color:var(--muted);margin-top:5px}.item-sum{font-size:14px;white-space:nowrap;text-align:right}.quantity-controls{display:flex;gap:6px;align-items:center}.quantity-controls input{width:82px;text-align:center;min-height:31px;padding:5px 7px;font-size:12px;border-radius:6px}.quantity-controls button{background:#243844;border:1px solid var(--line);color:var(--ink);border-radius:5px;width:28px;height:28px}.quantity-controls .remove-item{margin-left:auto;color:var(--red);font-size:17px;background:transparent;border:0}.quantity-controls span{font-size:10px;color:var(--muted)}.order-bottom{padding:24px}.total-row{display:flex;align-items:center;justify-content:space-between;gap:15px;font-size:14px;color:#c0cdd5}.total-row strong{font-size:31px;letter-spacing:-1px;color:var(--ink);white-space:nowrap}.order-actions{display:flex;flex-direction:column;gap:10px;margin-top:24px}.order-footnote{text-align:center;font-size:9px;color:#8599a7;margin-top:16px}.payment-box{padding:22px;background:#142b30;text-align:center;border-bottom:1px solid var(--line)}.payment-box .qr-image{margin:18px auto;width:300px;max-width:100%;height:auto}.payment-box h3{color:var(--mint)}.payment-box p{font-size:12px;color:var(--muted);margin-top:8px}.payment-box .timer{font-size:22px;margin-top:12px}.payment-link{display:block;color:var(--mint);font-size:11px;text-decoration:underline;overflow-wrap:anywhere;margin-top:15px;line-height:1.6}.qr-image{display:block;width:320px;height:320px;max-width:100%;object-fit:contain;background:#fff;border:8px solid #fff;border-radius:12px}.timer{font-variant-numeric:tabular-nums;color:var(--gold);font-size:30px;letter-spacing:1px}.success-icon{display:grid;place-items:center;width:76px;height:76px;background:#25443f;color:var(--mint);border-radius:50%;font-size:42px;margin:0 auto 20px}.payment-box .success-icon{width:50px;height:50px;font-size:25px;margin-bottom:12px}
dialog{border:1px solid #45606a;border-radius:20px;background:var(--panel);color:var(--ink);padding:28px;width:min(520px,calc(100vw - 30px));max-height:90vh;box-shadow:0 30px 100px #0007}dialog::backdrop{background:#06101dcc;backdrop-filter:blur(5px)}.dialog-head{display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:18px}.dialog-head h2{font-size:23px}.dialog-head+ .muted{margin-bottom:18px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.checkbox-label{display:flex;gap:10px;align-items:center;margin:20px 0}.checkbox-label input{margin:0}.dialog-head~.button{margin-top:20px}
.login-layout{display:grid;grid-template-columns:1.3fr 1fr;gap:9vw;max-width:1140px;align-items:center;margin:40px auto 10px}.login-story{padding:8px 0}.login-story h1{font-size:49px;line-height:1.18;letter-spacing:-2.5px}.login-story h1>span{color:var(--mint)}.login-story>p{margin-top:22px;color:var(--muted);font-size:14px}.login-card{padding:38px;max-width:420px;width:100%;justify-self:end}.login-card h2{font-size:29px;letter-spacing:-1px;margin-bottom:10px}.login-card form{margin-top:30px}.login-card form .button{margin-top:25px;justify-content:space-between}.login-note{font-size:11px;text-align:center;margin-top:26px;color:var(--muted);border-top:1px solid var(--line);padding-top:23px}.story-art{height:220px;position:relative;margin-top:10px}.art-orbit{position:absolute;width:340px;height:170px;border:1px solid #31514f;border-radius:50%;transform:rotate(-16deg);top:45px;left:10px}.art-orbit::after{content:"";position:absolute;inset:20px;border:1px dashed #31514f;border-radius:50%}.art-receipt{background:#20313c;border:1px solid #49616a;padding:20px;border-radius:12px;position:absolute;left:67px;top:20px;width:250px;transform:rotate(-7deg);box-shadow:0 20px 40px #0004}.art-receipt>span{font-weight:700;font-size:18px}.art-lines{height:5px;width:80%;margin:15px 0 0;background:#56717d;border-radius:4px}.art-lines.short{width:55%;margin-top:10px}.art-total{font-size:11px;margin-top:20px;border-top:1px dashed #607881;padding-top:14px;display:flex;justify-content:space-between}.art-total b{color:var(--mint)}.art-barcode{background:repeating-linear-gradient(90deg,#94b3b8 0 2px,transparent 2px 5px,#94b3b8 5px 6px,transparent 6px 9px);height:22px;margin-top:15px;width:90px}.art-chip{position:absolute;bottom:22px;left:240px;background:#dbc087;color:#2c352f;padding:12px 18px;border-radius:8px;transform:rotate(5deg);font-size:11px;font-weight:700;white-space:nowrap}.story-footer{display:flex;gap:22px;color:#94afa9;font-size:9px;letter-spacing:.2px;margin-top:14px}
.live-indicator{font-size:11px;color:var(--muted)}.live-indicator::before{content:"";display:inline-block;width:6px;height:6px;background:var(--mint);border-radius:50%;margin-right:8px}.welcome-display{min-height:570px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:45px 20px;background:radial-gradient(ellipse at 50% 30%,#223f43 0,transparent 65%),var(--panel)}.welcome-icon{display:block;width:90px;height:90px;background:var(--mint);color:#132e32;border-radius:24px;font-size:65px;font-weight:800;line-height:85px;letter-spacing:-8px;padding-right:7px;transform:rotate(-7deg);margin-bottom:30px}.welcome-icon span{color:#315445;font-size:50px}.welcome-display h2{font-size:42px;line-height:1.2;letter-spacing:-1.5px;margin:8px 0 20px}.welcome-display p{font-size:14px;color:var(--muted)}.welcome-steps{display:flex;gap:40px;margin-top:45px;color:#c0d2cb;font-size:11px}.display-layout{display:grid;grid-template-columns:1fr 440px;gap:26px;align-items:start}.display-cart{padding:28px}.display-cart .order-item{padding:20px 0}.display-cart .item-name{font-size:16px}.display-cart .item-detail{font-size:13px}.display-cart .item-sum{font-size:18px}.display-total{margin-top:30px;padding-top:10px}.display-total strong{font-size:40px}.display-pay{text-align:center;padding:32px 28px;display:flex;flex-direction:column;align-items:center;min-height:425px;justify-content:center}.display-pay h2{font-size:26px;margin-bottom:12px}.display-pay p{font-size:13px;color:var(--muted);margin-top:10px}.display-pay .qr-image{margin:18px 0 22px}.display-pay .timer{margin-top:12px}.display-pay .payment-link{max-width:330px}.display-pay .waiting-symbol{font-size:55px;color:var(--gold);margin-bottom:20px}
.price-hero{text-align:center;padding:32px 0 30px}.price-hero h1{font-size:48px;letter-spacing:-2px;line-height:1.16}.price-hero p{font-size:13px;color:var(--muted);margin-top:20px}.price-search{display:flex;gap:10px;max-width:640px;margin:30px auto 0;padding:8px;border:1px solid #42645f;background:var(--panel);border-radius:14px;box-shadow:0 10px 50px #07131330}.price-search input{border:0;background:transparent;min-width:0}.centered{justify-content:center;margin:12px 0 37px}.price-grid{grid-template-columns:repeat(4,minmax(0,1fr))}.price-grid .product-card{min-height:200px;cursor:default}.price-grid .product-name{font-size:16px}.price-grid .product-price strong{font-size:24px}.price-grid .product-price small{font-size:12px}.price-grid .product-stock{margin-top:10px}.price-description{font-size:11px;color:var(--muted)}
.admin-tabs{display:flex;gap:6px;padding:6px;border:1px solid var(--line);background:#15232d;border-radius:12px;margin-bottom:26px;overflow:auto}.admin-tabs button{background:transparent;border:0;color:var(--muted);padding:13px 23px;white-space:nowrap;border-radius:8px;font-size:12px}.admin-tabs button[aria-selected=true]{background:#294239;color:var(--mint)}.admin-panel{padding:28px}.table-toolbar{display:flex;gap:12px;margin-bottom:20px}.table-toolbar input{max-width:370px}.table-toolbar select{max-width:180px}table{width:100%;border-collapse:collapse;text-align:left;font-size:13px}.table-scroll{overflow-x:auto}th{font-size:10px;letter-spacing:.5px;color:var(--muted);font-weight:500;padding:14px 14px;border-bottom:1px solid var(--line);white-space:nowrap}td{padding:18px 14px;border-bottom:1px solid #2a3943;vertical-align:middle}tbody tr:last-child td{border-bottom:0}td small{display:block;margin-top:6px;font-size:10px;color:var(--muted)}td .actions{display:flex;gap:6px;flex-wrap:wrap}td.money-cell{white-space:nowrap;font-variant-numeric:tabular-nums}.table-empty{text-align:center;color:var(--muted);padding:45px 20px}.category-indent{color:#6c958c;margin-right:9px}.report-filter{display:flex;gap:18px;padding:20px;align-items:end;margin-bottom:20px}.report-filter label{flex:0 1 200px}.report-filter>span{align-self:center;margin-left:auto;font-size:11px}.stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px}.stat-card{padding:25px;border:1px solid #35584e;background:#1e3434;border-radius:16px}.stat-card span{display:block;color:var(--muted);font-size:12px;margin-bottom:13px}.stat-card strong{font-size:35px;color:var(--mint);letter-spacing:-1px}.report-grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}.report-grid>.panel{padding:25px}.report-products{grid-column:1/-1}.report-grid h2{margin-bottom:18px}.review-reason{max-width:300px;overflow-wrap:anywhere;color:var(--gold);line-height:1.6;font-size:12px}
.receipt-actions{max-width:620px;margin:0 auto 25px;display:flex;justify-content:space-between;gap:15px}.receipt-paper{max-width:620px;margin:auto;background:#f5f2e9;color:#223236;padding:42px;border-radius:3px;box-shadow:0 25px 60px #0005;font-family:"Courier New",monospace}.receipt-brand{text-align:center;font-family:Arial,sans-serif;font-size:30px;letter-spacing:-1.5px}.receipt-subtitle{text-align:center;font-size:12px;margin:14px 0 25px}.receipt-meta{border-block:1px dashed #a5adab;padding:18px 0;line-height:1.8;font-size:12px}.receipt-line{padding:16px 0;border-bottom:1px dashed #b2b7b3}.receipt-line strong{font-size:13px}.receipt-line>div{display:flex;justify-content:space-between;margin-top:8px;font-size:12px;gap:20px}.receipt-total{display:flex;justify-content:space-between;font-size:22px;font-weight:700;padding:24px 0}.receipt-disclaimer{text-align:center;font-size:10px;margin-top:25px;color:#5e6b69;border-top:1px dashed #a5adab;padding-top:20px}.receipt-paper .form-error{color:#8b2833;background:#f3e0df}
@media(min-width:1500px){.product-grid{grid-template-columns:repeat(4,minmax(0,1fr))}.price-grid{grid-template-columns:repeat(5,minmax(0,1fr))}}
@media(max-width:1150px){.cashier-layout{grid-template-columns:minmax(0,1fr) 350px;gap:18px}.product-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.price-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.display-layout{grid-template-columns:minmax(0,1fr) 390px}.catalog-toolbar{flex-wrap:wrap;gap:12px}.catalog-toolbar input{max-width:none}.login-story h1{font-size:41px}.login-layout{gap:5vw}.topbar{gap:20px}.topbar nav{gap:20px}.order-header,.order-bottom{padding:22px 18px}.order-item{padding:18px}.total-row strong{font-size:28px}}
@media(max-width:850px){.topbar{height:auto;min-height:90px;flex-wrap:wrap;padding:20px 5vw;gap:20px}.topbar nav{order:3;width:100%;justify-content:center;border-top:1px solid var(--line);padding-top:8px;margin:0}.header-end{margin-left:auto}.page-shell{padding:28px 5vw 40px}.cashier-layout,.display-layout{grid-template-columns:1fr}.order-panel{position:static}.product-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.price-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.order-items{max-height:none}.display-pay{grid-row:1}.page-heading{align-items:flex-start}.heading-actions{flex-direction:column;align-items:flex-end;gap:8px}.login-layout{grid-template-columns:1fr;max-width:500px;margin:15px auto;gap:35px}.login-story{text-align:center}.login-story h1{font-size:42px}.login-story>p{display:none}.story-art,.story-footer{display:none}.login-card{max-width:none;justify-self:stretch}.site-footer span:last-child{display:none}.report-grid{grid-template-columns:1fr}.admin-panel{padding:20px}.admin-tabs button{padding:12px 17px}.report-filter{flex-wrap:wrap}.report-filter>span{margin-left:0}.welcome-display{min-height:480px}.welcome-steps{gap:20px}.display-total strong{font-size:35px}}
@media(max-width:540px){h1{font-size:29px}.brand{font-size:20px}.brand-mark{width:38px;height:38px;font-size:28px}.brand small{font-size:6px}.header-end{gap:8px}.user-label{max-width:80px;overflow:hidden;text-overflow:ellipsis}.topbar nav{gap:24px}.topbar nav a{font-size:12px}.page-heading{margin-bottom:22px;gap:12px}.heading-actions .button{font-size:10px;padding:10px;min-height:35px}.terminal-label{font-size:10px}.product-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.product-card{padding:15px;min-height:163px}.product-price strong{font-size:17px}.product-price small{font-size:9px}.scan-icon{display:none}.scan-form .button{font-size:10px;padding:12px 10px}.scan-form input{font-size:11px}.scan-panel{padding:8px}.catalog-toolbar h2{font-size:19px}.order-panel{border-radius:14px}.page-shell{padding:24px 4vw 35px}.price-hero{padding-top:15px}.price-hero h1{font-size:36px}.price-hero p{font-size:12px}.price-search{padding:6px;gap:4px}.price-search input{padding:10px 8px;font-size:12px}.price-search .button{padding:12px;font-size:11px}.price-grid .product-name{font-size:14px}.price-grid .product-price strong{font-size:19px}.price-grid .product-price small{font-size:10px}.price-grid .product-card{min-height:185px}.welcome-display h2{font-size:32px}.welcome-steps{flex-direction:column;gap:15px;margin-top:28px}.welcome-display p{font-size:12px}.live-indicator{font-size:9px;max-width:105px;line-height:1.5}.display-cart{padding:20px}.display-pay{padding:26px 12px}.display-pay .qr-image{width:300px;height:300px;max-width:none}.display-total strong{font-size:30px}.display-cart .item-name{font-size:14px}.display-cart .item-sum{font-size:16px}.site-footer{font-size:9px;gap:15px;padding:18px 4vw}.login-card{padding:28px 22px}.login-story h1{font-size:35px}.login-story .eyebrow{font-size:9px}.section-head{flex-wrap:wrap}.section-head h2{font-size:19px}.table-toolbar{flex-direction:column}.table-toolbar input,.table-toolbar select{max-width:none}.admin-panel{padding:18px 12px}.admin-tabs{margin-bottom:18px}.form-grid{grid-template-columns:1fr}.form-grid .span-two{grid-column:1}.stat-card{padding:19px}.stat-card strong{font-size:27px}.stat-grid{gap:12px}.report-filter{padding:15px;gap:15px}.report-filter label{flex:1}.report-filter .button{width:100%}.report-filter>span{width:100%;text-align:center}.report-grid>.panel{padding:18px 12px}.receipt-paper{padding:28px 22px}.receipt-actions .button{font-size:11px;padding:12px}.receipt-total{font-size:19px}dialog{padding:22px 18px}.demo-badge{font-size:8px;padding:8px}.payment-box .qr-image{max-width:none}.cashier-layout{gap:25px}}
@media(prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}.product-card:hover{transform:none}}
form>label+input{margin-top:8px}
.display-layout>*{min-width:0}.section-head h2{min-width:0;overflow-wrap:anywhere}.order-header>div{min-width:0}.order-header h2{overflow-wrap:anywhere;line-height:1.4}.order-header .status{flex-shrink:0}
@media(max-width:380px){body[data-page=display] .page-shell{padding-inline:0}body[data-page=display] .page-heading{margin-inline:12px}.display-pay{padding-inline:8px}.order-panel{margin-inline:-4vw;border-radius:0}.payment-box{padding-inline:8px}.form-grid{grid-template-columns:1fr}}
@media print{:root,body{background:white;color:black;color-scheme:light}.topbar,.site-footer,.notice,.receipt-actions,.skip-link{display:none!important}.page-shell{padding:0;min-height:0}.receipt-paper{width:80mm;max-width:100%;padding:6mm;margin:0 auto;background:white;color:black;box-shadow:none;border-radius:0;font-size:10px}.receipt-total{font-size:16px}.receipt-disclaimer{font-size:9px}@page{margin:8mm}}
````

app/static/shop.js

````javascript
"use strict";

(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const API = "/api/v1";
  const isDev = document.body.dataset.development === "true";
  const timezone = document.body.dataset.timezone || "Asia/Almaty";
  const labels = {OPEN: "Открыт", PENDING_PAYMENT: "Ожидает оплату", PAID: "Оплачен", CANCELLED: "Отменён", PENDING: "Ожидание", SUCCEEDED: "Оплачен", FAILED: "Отклонён", EXPIRED: "Истёк"};
  const failureLabels = {INSUFFICIENT_FUNDS: "На выбранном счёте недостаточно средств.", insufficient_funds: "На выбранном счёте недостаточно средств.", bank_declined: "Банк отклонил платёж.", USER_CANCELLED: "Покупатель отменил оплату.", MERCHANT_CANCELLED: "Оплата отменена кассиром.", expired: "Срок оплаты истёк.", EXPIRED: "Срок оплаты истёк.", DECLINED: "Банк отклонил платёж.", BANK_UNAVAILABLE: "Банк временно недоступен."};
  let noticeTimer;

  function element(tag, className, content) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content !== undefined) node.textContent = String(content);
    return node;
  }
  function button(text, className, action) {
    const node = element("button", `button ${className}`, text);
    node.type = "button";
    node.addEventListener("click", () => safely(action));
    return node;
  }
  function notice(message, error = false) {
    const dialog = $("dialog[open]");
    if (dialog && error) {
      let inline = $(".dialog-notice", dialog);
      if (!inline) { inline = element("div", "form-error dialog-notice"); inline.setAttribute("role", "alert"); $("form", dialog).prepend(inline); }
      inline.textContent = message; inline.scrollIntoView({block: "nearest"});
      return;
    }
    const box = $("#notice");
    box.textContent = message;
    box.classList.toggle("error", error);
    box.hidden = false;
    clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => { box.hidden = true; }, error ? 8500 : 4000);
  }
  async function safely(action) {
    try { return await action(); } catch (error) { notice(error.message || "Не удалось выполнить действие.", true); }
  }
  function csrf() {
    return document.cookie.split("; ").find(item => item.startsWith("csrf_token="))?.split("=").slice(1).join("=") || "";
  }
  function parseJSON(text) {
    // Preserve large integer tokens without touching strings or using floating point.
    const preserved = text.replace(/"(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g, token => {
      if (token.startsWith('"') || !/^-?\d+$/.test(token)) return token;
      const integer = BigInt(token);
      return integer > 9007199254740991n || integer < -9007199254740991n ? `"${token}"` : token;
    });
    return JSON.parse(preserved);
  }
  async function api(path, options = {}) {
    const method = options.method || "GET";
    const headers = {Accept: "application/json", ...(options.headers || {})};
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    if (!["GET", "HEAD"].includes(method)) headers["X-CSRF-Token"] = decodeURIComponent(csrf());
    let response;
    try { response = await fetch(API + path, {...options, method, headers, credentials: "same-origin", cache: "no-store", body: options.body === undefined ? undefined : JSON.stringify(options.body)}); }
    catch { throw new Error("Нет связи с магазином. Проверьте подключение и повторите действие."); }
    const text = await response.text();
    let data;
    try { data = text ? parseJSON(text) : null; } catch { throw new Error("Сервер вернул неожиданный ответ. Повторите попытку."); }
    if (!response.ok) {
      if (response.status === 401 && document.body.dataset.page !== "login") {
        window.location.assign("/login");
      }
      const error = new Error(data?.error?.message || "Не удалось выполнить запрос.");
      error.code = data?.error?.code;
      error.status = response.status;
      if (response.status === 422 && data?.error?.details?.fields?.length) error.message += " Проверьте заполненные поля.";
      throw error;
    }
    return data;
  }
  function money(value) {
    const minor = BigInt(String(value ?? 0));
    const negative = minor < 0n;
    const absolute = negative ? -minor : minor;
    return `${negative ? "−" : ""}${(absolute / 100n).toLocaleString("ru-RU")},${String(absolute % 100n).padStart(2, "0")} ₸`;
  }
  function moneyInput(value) {
    const minor = BigInt(String(value ?? 0));
    return `${minor / 100n}.${String(minor % 100n).padStart(2, "0")}`;
  }
  function parsePrice(value) {
    const normalized = value.trim().replace(",", ".");
    if (!/^\d+(\.\d{1,2})?$/.test(normalized)) throw new Error("Укажите цену в тенге: например, 1250,50. Не больше двух знаков после запятой.");
    const [whole, fraction = ""] = normalized.split(".");
    const minor = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
    if (minor > 9007199254740991n) throw new Error("Цена слишком велика для ввода через веб-интерфейс.");
    return Number(minor);
  }
  function integer(value, minimum = 0) {
    if (!/^-?\d+$/.test(String(value))) throw new Error("Количество должно быть целым числом.");
    const result = Number(value);
    if (!Number.isSafeInteger(result) || result < minimum || result > 2147483647) throw new Error("Количество вне допустимого диапазона.");
    return result;
  }
  const unit = value => value === "KG" ? "кг" : "шт.";
  const amountUnit = value => value === "KG" ? "г" : "шт.";
  const quantity = item => `${item.quantity} ${amountUnit(item.unit)}`;
  function status(value) {
    return element("span", `status ${["PENDING", "PENDING_PAYMENT"].includes(value) ? "warning" : ["FAILED", "EXPIRED", "CANCELLED"].includes(value) ? "failure" : ""}`, labels[value] || value);
  }
  const dateTime = value => new Intl.DateTimeFormat("ru-RU", {timeZone: timezone, dateStyle: "medium", timeStyle: "short"}).format(new Date(value));
  function debounce(callback, delay = 220) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => safely(() => callback(...args)), delay); };
  }
  async function submitting(form, action) {
    const submit = $("button[type=submit]", form);
    if (submit.disabled) return;
    submit.disabled = true;
    try { await action(); } finally { submit.disabled = false; }
  }
  function bindForm(id, action) {
    const form = $(id);
    form.addEventListener("submit", event => { event.preventDefault(); safely(() => submitting(form, () => action(form))); });
  }
  function pagination(container, page, onChange) {
    container.replaceChildren();
    if (!page.total) return;
    if (page.offset) container.append(button("← Назад", "secondary small", () => onChange(Math.max(0, page.offset - page.limit))));
    container.append(element("span", "", `${page.offset + 1}–${Math.min(page.offset + page.items.length, page.total)} из ${page.total}`));
    if (page.offset + page.limit < page.total) container.append(button("Далее →", "secondary small", () => onChange(page.offset + page.limit)));
  }
  async function allCategories(publicOnly = false) {
    const result = [];
    for (let offset = 0; ; offset += 100) {
      const page = await api(`${publicOnly ? "/public" : ""}/categories?limit=100&offset=${offset}`);
      result.push(...page.items);
      if (result.length >= page.total || page.items.length === 0) return result;
    }
  }
  function categoryTree(categories) {
    const result = [], visited = new Set();
    function add(parent, depth) {
      categories.filter(item => item.parent_id === parent).sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name, "ru")).forEach(item => {
        if (visited.has(item.public_id)) return;
        visited.add(item.public_id); result.push({...item, depth}); add(item.public_id, depth + 1);
      });
    }
    add(null, 0);
    categories.filter(item => !visited.has(item.public_id)).forEach(item => result.push({...item, depth: 0}));
    return result;
  }
  function categoryChips(container, categories, selected, select) {
    container.replaceChildren();
    const all = button("Все товары", "", () => select(""));
    all.className = selected ? "" : "active";
    all.setAttribute("aria-pressed", String(!selected)); container.append(all);
    categoryTree(categories).filter(item => item.is_active).forEach(item => {
      const node = button(`${item.depth ? "↳ " : ""}${item.name}`, "", () => select(item.public_id));
      node.className = `${selected === item.public_id ? "active " : ""}${item.depth ? "child-chip" : ""}`;
      node.setAttribute("aria-pressed", String(selected === item.public_id)); container.append(node);
    });
  }
  function productCard(product, action) {
    const card = element(action ? "button" : "article", "product-card");
    if (action) { card.type = "button"; card.addEventListener("click", () => safely(() => action(product))); card.disabled = !product.in_stock; }
    const art = element("span", "product-art", product.unit === "KG" ? "кг" : product.name.slice(0, 1).toUpperCase());
    art.setAttribute("aria-hidden", "true"); card.append(art, element("span", "product-name", product.name));
    const price = element("div", "product-price"); price.append(element("strong", "", money(product.price_minor)), element("small", "", `за ${unit(product.unit)}`)); card.append(price);
    card.append(element("span", "product-stock", product.in_stock ? "● В наличии" : "Нет в наличии"));
    if (action) card.append(element("span", "add-circle", "+"));
    else { if (product.description) card.append(element("p", "price-description", product.description)); card.append(element("small", "muted", product.barcode)); }
    return card;
  }
  function qr(payment) {
    const image = element("img", "qr-image");
    image.src = `${API}/payments/${encodeURIComponent(payment.public_id)}/qr.png`;
    image.alt = "QR-код для оплаты в учебном банке";
    image.width = 320; image.height = 320;
    image.addEventListener("error", () => { image.hidden = true; });
    return image;
  }
  function paymentLink(payment) {
    if (!isDev || !payment.pay_url) return null;
    let url;
    try { url = new URL(payment.pay_url); } catch { return null; }
    if (!["http:", "https:"].includes(url.protocol)) return null;
    const link = element("a", "payment-link", `Открыть учебный банк ↗ ${url.href}`);
    link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer";
    return link;
  }
  function timerText(seconds) {
    const safe = Math.max(0, Math.floor(Number(seconds) || 0));
    return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, "0")}`;
  }
  function paymentContent(container, order, payment, {display = false} = {}) {
    container.replaceChildren();
    if (order?.status === "PAID") {
      container.append(element("div", "success-icon", "✓"), element("h2", "", "Оплачено!"), element("p", "", "Спасибо за покупку. Хорошего дня!")); return;
    }
    if (payment?.needs_review) {
      container.append(element("h2", "", "Проверяем платёж"), element("p", "form-error", "Платёж требует проверки администратором. Не повторяйте оплату до уточнения."));
      return;
    }
    if (order?.status === "PENDING_PAYMENT") {
      container.append(element(display ? "h2" : "h3", "", "Оплатите по QR"));
      if (payment?.pay_url && payment.status === "PENDING" && payment.seconds_left > 0) {
        container.append(element("p", "", "Откройте камеру и наведите на QR-код"), qr(payment));
        const timer = element("div", "timer", timerText(payment.seconds_left)); timer.dataset.timer = "true"; container.append(timer);
        const link = paymentLink(payment); if (link) container.append(link);
      } else container.append(element("p", "", "Проверяем состояние платежа в банке. Пожалуйста, подождите."));
      return;
    }
    if (payment && ["FAILED", "EXPIRED", "CANCELLED"].includes(payment.status)) {
      container.append(element("div", "waiting-symbol", "↻"), element("h2", "", labels[payment.status]), element("p", "", failureLabels[payment.failure_reason] || "Кассир может повторить оплату или изменить чек.")); return;
    }
    container.append(element("div", "waiting-symbol", "▥"), element("h2", "", "Готовим вашу покупку"), element("p", "", "Когда кассир добавит все товары, здесь появится QR-код для оплаты."));
  }
  function readonlyItems(container, items) {
    container.replaceChildren(...items.map(item => {
      const row = element("div", "order-item");
      const content = element("div"); content.append(element("div", "item-name", item.product_name), element("div", "item-detail", `${quantity(item)} · ${money(item.unit_price_minor)} / ${unit(item.unit)}`));
      row.append(content, element("strong", "item-sum", money(item.line_total_minor))); return row;
    }));
  }

  async function initLogin() {
    bindForm("#login-form", async form => {
      $("#login-error").hidden = true;
      try {
        await api("/auth/login", {method: "POST", body: {username: form.elements.username.value, password: form.elements.password.value}});
        form.elements.password.value = ""; window.location.assign("/cashier");
      } catch (error) { $("#login-error").textContent = error.message; $("#login-error").hidden = false; }
    });
  }

  async function initCashier() {
    const requestedTerminal = new URLSearchParams(location.search).get("terminal") || "main";
    const terminal = /^[a-zA-Z0-9_-]{1,64}$/.test(requestedTerminal) ? requestedTerminal : "main";
    $("#terminal-label").textContent = `Терминал ${terminal}`;
    $("#display-link").href = `/display/${encodeURIComponent(terminal)}`;
    let order = null, selectedCategory = "", categories = [], search = "", offset = 0, requestId = 0, busy = false, pollBusy = false, orderSignature = "", pendingProduct = null;
    const focusScan = () => { if (!document.querySelector("dialog[open]")) $("#barcode").focus(); };
    async function mutate(action) {
      if (busy) return;
      busy = true;
      try { await action(); await loadOrder(); } finally { busy = false; renderOrder(true); }
    }
    async function loadOrder() {
      if (order) order = await api(`/orders/${order.public_id}`);
      renderOrder();
    }
    async function newOrder() {
      await mutate(async () => { order = await api("/orders", {method: "POST", body: {terminal_code: terminal}}); }); focusScan();
    }
    async function add(product, quantityValue) {
      if (!order || order.status !== "OPEN") throw new Error("Сначала откройте новый чек. Текущий чек должен быть доступен для изменения.");
      await mutate(async () => { order = await api(`/orders/${order.public_id}/items`, {method: "POST", body: {product_id: product.public_id, quantity: quantityValue}}); });
      $("#barcode").value = ""; focusScan();
    }
    async function selectProduct(product) {
      if (!order || order.status !== "OPEN") throw new Error("Откройте новый чек перед добавлением товаров.");
      if (product.unit === "KG") {
        pendingProduct = product; $("#quantity-product").textContent = `${product.name} · ${money(product.price_minor)} / кг`;
        $("#quantity-value").value = "500"; $("#quantity-dialog").showModal(); $("#quantity-value").select();
      } else await add(product, 1);
    }
    bindForm("#quantity-form", async () => { await add(pendingProduct, integer($("#quantity-value").value, 1)); $("#quantity-dialog").close(); focusScan(); });
    bindForm("#scan-form", async () => {
      const barcode = $("#barcode").value.trim(); if (!barcode) return;
      if (!/^([0-9]{8}|[0-9]{13})$/.test(barcode)) throw new Error("Штрихкод должен содержать 8 или 13 цифр.");
      await selectProduct(await api(`/products/by-barcode/${encodeURIComponent(barcode)}`));
    });
    async function products() {
      const currentRequest = ++requestId;
      const query = new URLSearchParams({limit: "18", offset: String(offset), is_active: "true", include_subcategories: "true"});
      if (selectedCategory) query.set("category_id", selectedCategory); if (search) query.set("q", search);
      const result = await api(`/products?${query}`); if (currentRequest !== requestId) return;
      $("#product-count").textContent = result.total;
      $("#product-grid").replaceChildren(...result.items.map(product => productCard(product, selectProduct)));
      if (!result.items.length) $("#product-grid").append(element("p", "empty-note", "Товары не найдены. Попробуйте другое название или категорию."));
      pagination($("#catalog-pagination"), result, async value => { offset = value; await products(); });
    }
    function chips() { categoryChips($("#category-chips"), categories, selectedCategory, async value => { selectedCategory = value; offset = 0; chips(); await products(); }); }
    $("#product-search").addEventListener("input", debounce(async event => { search = event.target.value.trim(); offset = 0; await products(); }));
    $("#create-order").addEventListener("click", () => safely(newOrder));
    function renderOrder(force = false) {
      const signature = JSON.stringify(order ? {...order, payment: order.payment ? {...order.payment, seconds_left: 0, qr_usable: order.payment.seconds_left > 0} : null} : null);
      if (!force && signature === orderSignature) {
        const timer = $("[data-timer]"); if (timer) timer.textContent = timerText(order?.payment?.seconds_left);
        return;
      }
      orderSignature = signature;
      $("#order-empty").hidden = !!order;
      $("#order-number").textContent = order ? `№ ${order.number}` : "Начните покупку";
      const badge = status(order?.status || "Нет чека"); badge.id = "order-status"; $("#order-status").replaceWith(badge);
      $("#order-total").textContent = money(order?.total_minor || 0);
      const items = $("#order-items"); items.replaceChildren();
      for (const item of order?.items || []) {
        const row = element("div", "order-item"), content = element("div");
        content.append(element("div", "item-name", item.product_name), element("div", "item-detail", `${money(item.unit_price_minor)} / ${unit(item.unit)}`));
        row.append(content, element("strong", "item-sum", money(item.line_total_minor)));
        if (order.status === "OPEN") {
          const controls = element("div", "quantity-controls"); controls.classList.add("span-two");
          const input = element("input"); input.type = "number"; input.min = "1"; input.max = "2147483647"; input.step = "1"; input.value = item.quantity; input.setAttribute("aria-label", `Количество ${item.product_name}, ${amountUnit(item.unit)}`);
          const update = async value => { await mutate(async () => { order = await api(`/orders/${order.public_id}/items/${item.public_id}`, {method: "PATCH", body: {quantity: integer(value, 1)}}); }); focusScan(); };
          const down = button("−", "", () => update(item.quantity - 1)); down.setAttribute("aria-label", "Уменьшить количество"); down.disabled = item.quantity <= 1 || busy;
          const up = button("+", "", () => update(item.quantity + 1)); up.setAttribute("aria-label", "Увеличить количество"); up.disabled = busy;
          input.disabled = busy; input.addEventListener("change", () => safely(() => update(input.value)));
          const remove = button("×", "remove-item", async () => { await mutate(async () => { order = await api(`/orders/${order.public_id}/items/${item.public_id}`, {method: "DELETE"}); }); focusScan(); }); remove.setAttribute("aria-label", `Удалить ${item.product_name}`); remove.disabled = busy;
          controls.append(down, input, up, element("span", "", amountUnit(item.unit)), remove); row.append(controls);
        } else row.append(element("span", "item-detail", quantity(item)));
        items.append(row);
      }
      if (order?.status === "OPEN" && !order.items.length) items.append(element("p", "empty-note", "Отсканируйте первый товар или выберите его в каталоге."));
      const payment = order?.payment, paymentPanel = $("#payment-panel");
      paymentPanel.hidden = !order || (!payment && order.status !== "PAID");
      if (!paymentPanel.hidden) paymentContent(paymentPanel, order, payment);
      const actions = $("#order-actions"); actions.replaceChildren();
      if (!order) return;
      if (order.status === "OPEN") {
        const checkout = button("Принять оплату по QR →", "primary wide", () => mutate(async () => { await api(`/orders/${order.public_id}/checkout`, {method: "POST"}); })); checkout.disabled = busy || !order.items.length || !!payment?.needs_review; actions.append(checkout);
      }
      if (order.status === "PENDING_PAYMENT" && payment) {
        actions.append(button("Проверить оплату ↻", "primary wide", () => mutate(async () => { await api(`/payments/${payment.public_id}/refresh`, {method: "POST"}); })));
        actions.append(button("Отменить платёж / изменить чек", "secondary wide", async () => { if (confirm("Отменить оплату и вернуться к изменению чека?")) await mutate(async () => { await api(`/payments/${payment.public_id}/cancel`, {method: "POST"}); }); }));
      }
      if (["OPEN", "PENDING_PAYMENT"].includes(order.status)) actions.append(button("Отменить чек", "ghost wide", async () => { if (confirm("Отменить текущий чек?")) await mutate(async () => { await api(`/orders/${order.public_id}/cancel`, {method: "POST"}); }); }));
      else {
        if (order.status === "PAID") { const receipt = element("a", "button secondary wide", "Открыть чек / печать ↗"); receipt.href = `/receipt/${order.public_id}`; receipt.target = "_blank"; receipt.rel = "noopener"; actions.append(receipt); }
        actions.append(button("Новый чек +", "primary wide", newOrder));
      }
      if (busy) $$("button", actions).forEach(node => { node.disabled = true; });
    }
    categories = await allCategories(); chips(); await products();
    const state = await api(`/public/terminals/${terminal}/display`);
    if (state.order) order = await api(`/orders/${state.order.public_id}`);
    renderOrder(); focusScan();
    document.addEventListener("pointerup", event => {
      if (!event.target.closest("input, textarea, select, button, a, dialog")) focusScan();
    });
    setInterval(async () => {
      if (pollBusy || busy || document.hidden) return;
      pollBusy = true;
      try {
        if (order) { const latest = await api(`/orders/${order.public_id}`); if (!$("#order-items").contains(document.activeElement)) { order = latest; renderOrder(); } }
        else { const state = await api(`/public/terminals/${terminal}/display`); if (state.order) { order = await api(`/orders/${state.order.public_id}`); renderOrder(); } }
      } catch (error) { notice(error.message, true); } finally { pollBusy = false; }
    }, 1500);
  }

  async function initDisplay() {
    const terminal = document.body.dataset.terminal;
    let busy = false, signature = "";
    async function refresh() {
      if (busy) return; busy = true;
      try {
        const state = await api(`/public/terminals/${encodeURIComponent(terminal)}/display`);
        $("#connection-status").textContent = "Обновление каждые 1,5 секунды";
        $("#display-idle").hidden = !!state.order; $("#display-order").hidden = !state.order;
        if (!state.order) return;
        const order = state.order;
        $("#display-order-number").textContent = `Чек № ${order.number}`;
        $("#display-item-count").textContent = `${order.items.length} поз.`;
        $("#display-total").textContent = money(order.total_minor);
        const newSignature = JSON.stringify({...state, seconds_left: 0, qr_usable: state.seconds_left > 0, payment: state.payment ? {...state.payment, seconds_left: 0} : null, order: {...order, payment: order.payment ? {...order.payment, seconds_left: 0} : null}});
        if (signature !== newSignature) { readonlyItems($("#display-items"), order.items); paymentContent($("#display-payment"), order, state.payment, {display: true}); signature = newSignature; }
        const timer = $("[data-timer]"); if (timer) timer.textContent = timerText(state.seconds_left);
      } catch { $("#connection-status").textContent = "Связь прервана. Восстанавливаем…"; } finally { busy = false; }
    }
    await refresh(); setInterval(refresh, 1500);
  }

  async function initPriceCheck() {
    let selected = "", search = "", offset = 0, currentRequest = 0;
    const categories = await allCategories(true);
    function chips() { categoryChips($("#price-categories"), categories, selected, async value => { selected = value; offset = 0; chips(); await load(); }); }
    async function load() {
      const id = ++currentRequest;
      const query = new URLSearchParams({limit: "20", offset: String(offset), include_subcategories: "true"});
      if (selected) query.set("category_id", selected);
      if (search) query.set(/^([0-9]{8}|[0-9]{13})$/.test(search) ? "barcode" : "q", search);
      const data = await api(`/public/products?${query}`); if (id !== currentRequest) return;
      $("#price-heading").textContent = search ? "Результаты поиска" : "Товары магазина";
      $("#price-count").textContent = `Найдено: ${data.total}`;
      $("#price-results").replaceChildren(...data.items.map(item => productCard(item)));
      if (!data.items.length) $("#price-results").append(element("p", "empty-note", "Не нашли такой товар. Проверьте штрихкод или попробуйте другое название."));
      pagination($("#price-pagination"), data, async value => { offset = value; await load(); });
    }
    bindForm("#price-search-form", async () => { search = $("#price-search").value.trim(); offset = 0; await load(); $("#price-search").select(); });
    $("#price-search").addEventListener("input", debounce(async () => { search = $("#price-search").value.trim(); offset = 0; await load(); }, 350));
    chips(); await load();
  }

  async function initReceipt() {
    const data = await api(`/orders/${document.body.dataset.order}/receipt`);
    const content = $("#receipt-content"); content.replaceChildren();
    const meta = element("div", "receipt-meta");
    meta.append(element("p", "", `Чек № ${data.number}`), element("p", "", `${dateTime(data.paid_at || data.created_at)} · ${timezone}`), element("p", "", `Терминал: ${data.terminal_code}`)); content.append(meta);
    data.items.forEach(item => {
      const row = element("div", "receipt-line"), detail = element("div"); row.append(element("strong", "", item.product_name));
      detail.append(element("span", "", `${quantity(item)} × ${money(item.unit_price_minor)}/${unit(item.unit)}`), element("span", "", money(item.line_total_minor))); row.append(detail); content.append(row);
    });
    const total = element("div", "receipt-total"); total.append(element("span", "", "ИТОГО"), element("span", "", money(data.total_minor))); content.append(total, element("p", "", `Оплата: ${data.payment_method} · ${labels[data.status] || data.status}`));
    $("#print-receipt").disabled = false; $("#print-receipt").addEventListener("click", () => window.print());
  }

  async function initAdmin() {
    let categories = await allCategories(), productOffset = 0, stockOffset = 0, reviewOffset = 0, currentProduct = null;
    const productForm = $("#product-form"), categoryForm = $("#category-form"), stockForm = $("#stock-form");
    function cell(value, className = "") { return element("td", className, value); }
    function noRows(body, columns, message = "Записей пока нет.") { if (!body.children.length) { const row = element("tr"), td = cell(message, "table-empty"); td.colSpan = columns; row.append(td); body.append(row); } }
    function fillCategories(select, selected = "", includeRoot = false, exclude = "") {
      select.replaceChildren();
      const empty = element("option", "", includeRoot ? "Без родителя" : "Выберите категорию"); empty.value = ""; select.append(empty);
      categoryTree(categories).filter(item => item.public_id !== exclude).forEach(item => { const option = element("option", "", `${"— ".repeat(Math.min(item.depth, 6))}${item.name}${item.is_active ? "" : " (неактивна)"}`); option.value = item.public_id; select.append(option); }); select.value = selected || "";
    }
    function openProduct(product = null) {
      currentProduct = product; productForm.reset(); const fields = productForm.elements;
      fields.public_id.value = product?.public_id || ""; fields.name.value = product?.name || ""; fields.barcode.value = product?.barcode || ""; fields.unit.value = product?.unit || "PIECE";
      fields.price.value = moneyInput(product?.price_minor || 0); fields.stock_quantity.value = product?.stock_quantity || 0; fields.min_stock_quantity.value = product?.min_stock_quantity || 0;
      fields.description.value = product?.description || ""; fields.is_active.checked = product?.is_active ?? true;
      fillCategories(fields.category_id, product?.category_id); $("#initial-stock-label").hidden = !!product;
      $("#product-dialog-title").textContent = product ? "Изменить товар" : "Новый товар"; $("#product-dialog").showModal(); fields.name.focus();
    }
    function openCategory(category = null) {
      categoryForm.reset(); const fields = categoryForm.elements;
      fields.public_id.value = category?.public_id || ""; fields.name.value = category?.name || ""; fields.slug.value = category?.slug || ""; fields.sort_order.value = category?.sort_order || 0; fields.is_active.checked = category?.is_active ?? true;
      fillCategories(fields.parent_id, category?.parent_id, true, category?.public_id); $("#category-dialog-title").textContent = category ? "Изменить категорию" : "Новая категория"; $("#category-dialog").showModal(); fields.name.focus();
    }
    function openStock(product) {
      stockForm.reset(); stockForm.elements.public_id.value = product.public_id;
      $("#stock-product-name").textContent = `${product.name} · изменение в ${amountUnit(product.unit)}. Доступно: ${product.available_quantity}.`;
      $("#stock-dialog").showModal(); stockForm.elements.delta.focus();
    }
    async function products() {
      const query = new URLSearchParams({limit: "20", offset: String(productOffset)}), search = $("#admin-product-search").value.trim(), active = $("#admin-product-active").value;
      if (search) query.set("q", search); if (active) query.set("is_active", active);
      const page = await api(`/products?${query}`), body = $("#admin-products"); body.replaceChildren();
      page.items.forEach(product => {
        const row = element("tr"), title = cell(product.name); title.append(element("small", "", product.barcode));
        const activeCell = cell(""); activeCell.append(element("span", `status ${product.is_active ? "" : "muted-status"}`, product.is_active ? "Активен" : "Скрыт"));
        const actions = element("div", "actions"); actions.append(button("Изменить", "secondary small", () => openProduct(product)), button("Остаток", "secondary small", () => openStock(product)));
        if (product.is_active) actions.append(button("Скрыть", "ghost small", async () => { if (confirm(`Скрыть товар «${product.name}» с кассы?`)) { await api(`/products/${product.public_id}`, {method: "DELETE"}); await products(); notice("Товар скрыт."); } }));
        const actionCell = cell(""); actionCell.append(actions);
        row.append(title, cell(`${money(product.price_minor)} / ${unit(product.unit)}`, "money-cell"), cell(`${product.stock_quantity} / ${product.available_quantity} ${amountUnit(product.unit)}`), activeCell, actionCell); body.append(row);
      }); noRows(body, 5); pagination($("#admin-pagination"), page, async value => { productOffset = value; await products(); });
    }
    function renderCategories() {
      const body = $("#admin-categories"); body.replaceChildren();
      categoryTree(categories).forEach(category => {
        const row = element("tr"), name = cell(`${"↳ ".repeat(Math.min(category.depth, 5))}${category.name}`), actions = element("div", "actions");
        actions.append(button("Изменить", "secondary small", () => openCategory(category)));
        if (category.is_active) actions.append(button("Скрыть", "ghost small", async () => { if (confirm(`Деактивировать категорию «${category.name}»?`)) { await api(`/categories/${category.public_id}`, {method: "DELETE"}); categories = await allCategories(); renderCategories(); } }));
        const actionCell = cell(""); actionCell.append(actions); row.append(name, cell(category.slug), cell(category.sort_order), cell(category.is_active ? "Активна" : "Скрыта"), actionCell); body.append(row);
      }); noRows(body, 5);
    }
    bindForm("#product-form", async form => {
      const f = form.elements, id = f.public_id.value;
      const data = {name: f.name.value, barcode: f.barcode.value.trim(), category_id: f.category_id.value, unit: f.unit.value, min_stock_quantity: integer(f.min_stock_quantity.value), description: f.description.value || null, is_active: f.is_active.checked};
      if (!id || !currentProduct || f.price.value !== moneyInput(currentProduct.price_minor)) data.price_minor = parsePrice(f.price.value);
      if (!id) data.stock_quantity = integer(f.stock_quantity.value);
      await api(id ? `/products/${id}` : "/products", {method: id ? "PATCH" : "POST", body: data}); $("#product-dialog").close(); await products(); notice("Товар сохранён.");
    });
    bindForm("#category-form", async form => {
      const f = form.elements, id = f.public_id.value;
      const data = {name: f.name.value, slug: f.slug.value, parent_id: f.parent_id.value || null, sort_order: integer(f.sort_order.value, -2147483648), is_active: f.is_active.checked};
      await api(id ? `/categories/${id}` : "/categories", {method: id ? "PATCH" : "POST", body: data}); $("#category-dialog").close(); categories = await allCategories(); renderCategories(); notice("Категория сохранена.");
    });
    bindForm("#stock-form", async form => {
      const f = form.elements, delta = integer(f.delta.value, -2147483647);
      if (!delta) throw new Error("Изменение остатка не может быть равно нулю.");
      if (f.reason.value === "RESTOCK" && delta < 0) throw new Error("Поставка должна увеличивать остаток. Для уменьшения выберите корректировку.");
      await api(`/products/${f.public_id.value}/stock-adjustments`, {method: "POST", body: {delta, reason: f.reason.value}}); $("#stock-dialog").close(); await products(); if (!$("#tab-stock").hidden) await lowStock(); notice("Остаток обновлён.");
    });
    async function sales(useDates = true) {
      const query = new URLSearchParams();
      if (useDates) { query.set("date_from", $("#date-from").value); query.set("date_to", $("#date-to").value); }
      if (useDates && $("#date-from").value > $("#date-to").value) throw new Error("Дата начала должна быть не позже даты окончания.");
      const data = await api(`/reports/sales?${query}`);
      $("#date-from").value = data.date_from; $("#date-to").value = data.date_to;
      $("#report-stats").replaceChildren(...[["Выручка за период", money(data.revenue_minor)], ["Оплаченные чеки", data.orders_count]].map(([title, value]) => { const card = element("div", "stat-card"); card.append(element("span", "", title), element("strong", "", value)); return card; }));
      const daily = $("#report-days"); daily.replaceChildren(...data.days.map(item => { const row = element("tr"); row.append(cell(item.date), cell(item.orders_count), cell(money(item.revenue_minor), "money-cell")); return row; })); noRows(daily, 3, "За этот период нет продаж.");
      const grouped = $("#report-categories"); grouped.replaceChildren(...data.categories.map(item => { const row = element("tr"); row.append(cell(item.name), cell(money(item.revenue_minor), "money-cell")); return row; })); noRows(grouped, 2);
      const sold = $("#report-products"); sold.replaceChildren(...data.products.map(item => { const row = element("tr"); row.append(cell(item.name), cell(quantity(item)), cell(money(item.revenue_minor), "money-cell")); return row; })); noRows(sold, 3);
    }
    async function lowStock() {
      const page = await api(`/reports/low-stock?limit=20&offset=${stockOffset}`), body = $("#low-stock"); body.replaceChildren();
      page.items.forEach(item => { const row = element("tr"), actions = cell(""); actions.append(button("Пополнить", "secondary small", () => openStock(item))); row.append(cell(item.name), cell(`${item.available_quantity} ${amountUnit(item.unit)}`), cell(`${item.min_stock_quantity} ${amountUnit(item.unit)}`), actions); body.append(row); });
      noRows(body, 4, "Всё в порядке — товаров с низким остатком нет."); pagination($("#stock-pagination"), page, async value => { stockOffset = value; await lowStock(); });
    }
    async function review() {
      const page = await api(`/reports/payments-needing-review?limit=20&offset=${reviewOffset}`), body = $("#payment-review"); body.replaceChildren();
      page.items.forEach(item => {
        const row = element("tr"), title = cell(item.public_id.slice(0, 8)); title.append(element("small", "", dateTime(item.created_at)));
        const state = cell(""); state.append(status(item.status)); const actions = cell(""); actions.append(button("Сверить с банком", "secondary small", async () => { await api(`/payments/${item.public_id}/refresh`, {method: "POST"}); await review(); notice("Статус запрошен у банка. Флаг разбора снимается только после проверки причин."); }));
        row.append(title, cell(money(item.amount_minor), "money-cell"), state, cell(item.review_reason || "Требуется ручная проверка.", "review-reason"), actions); body.append(row);
      }); noRows(body, 5, "Спорных платежей нет."); pagination($("#review-pagination"), page, async value => { reviewOffset = value; await review(); });
    }
    $$("[data-tab]").forEach(tab => tab.addEventListener("click", () => safely(async () => {
      const name = tab.dataset.tab;
      $$("[data-tab]").forEach(item => item.setAttribute("aria-selected", String(item === tab)));
      $$("[role=tabpanel]").forEach(panel => { panel.hidden = panel.id !== `tab-${name}`; });
      if (name === "reports") await sales(!!$("#date-from").value); if (name === "stock") await lowStock(); if (name === "review") await review();
    })));
    $("#add-product").addEventListener("click", () => openProduct()); $("#add-category").addEventListener("click", () => openCategory());
    $("#admin-product-search").addEventListener("input", debounce(async () => { productOffset = 0; await products(); }));
    $("#admin-product-active").addEventListener("change", () => safely(async () => { productOffset = 0; await products(); }));
    $("#refresh-stock").addEventListener("click", () => safely(lowStock)); $("#refresh-review").addEventListener("click", () => safely(review));
    bindForm("#report-form", () => sales()); renderCategories(); await products();
  }

  $$("[data-close-dialog]").forEach(node => node.addEventListener("click", () => node.closest("dialog").close()));
  $$("dialog").forEach(dialog => dialog.addEventListener("close", () => $(".dialog-notice", dialog)?.remove()));
  $("#logout")?.addEventListener("click", () => safely(async () => { await api("/auth/logout", {method: "POST"}); window.location.assign("/login"); }));
  const pages = {login: initLogin, cashier: initCashier, display: initDisplay, "price-check": initPriceCheck, receipt: initReceipt, admin: initAdmin};
  safely(() => pages[document.body.dataset.page]?.());
})();
````

app/templates/admin.html

````html
{% extends 'base.html' %}
{% block title %}Управление · QR Mini-Market{% endblock %}
{% block content %}
<div class="page-heading"><div><span class="eyebrow">ПУЛЬТ УПРАВЛЕНИЯ</span><h1>Всё под контролем</h1></div><span class="demo-badge">АДМИНИСТРАТОР</span></div>
<div class="admin-tabs" role="tablist" aria-label="Управление магазином"><button type="button" role="tab" aria-selected="true" aria-controls="tab-products" id="tab-button-products" data-tab="products">Товары</button><button type="button" role="tab" aria-selected="false" aria-controls="tab-categories" id="tab-button-categories" data-tab="categories">Категории</button><button type="button" role="tab" aria-selected="false" aria-controls="tab-reports" id="tab-button-reports" data-tab="reports">Продажи</button><button type="button" role="tab" aria-selected="false" aria-controls="tab-stock" id="tab-button-stock" data-tab="stock">Низкие остатки</button><button type="button" role="tab" aria-selected="false" aria-controls="tab-review" id="tab-button-review" data-tab="review">Разбор платежей</button></div>
<section id="tab-products" class="panel admin-panel" role="tabpanel" aria-labelledby="tab-button-products"><div class="section-head"><div><h2>Каталог товаров</h2><p class="muted">Цены, наличие и доступность на кассе</p></div><button id="add-product" type="button" class="button primary">Добавить товар +</button></div><div class="table-toolbar"><input type="search" id="admin-product-search" placeholder="Название или штрихкод" aria-label="Поиск товара"><select id="admin-product-active" aria-label="Активность товаров"><option value="">Все товары</option><option value="true">Активные</option><option value="false">Неактивные</option></select></div><div class="table-scroll"><table><thead><tr><th>Товар / штрихкод</th><th>Цена</th><th>Остаток / доступно</th><th>Статус</th><th>Действия</th></tr></thead><tbody id="admin-products"></tbody></table></div><div id="admin-pagination" class="pagination"></div></section>
<section id="tab-categories" class="panel admin-panel" role="tabpanel" aria-labelledby="tab-button-categories" hidden><div class="section-head"><div><h2>Категории</h2><p class="muted">Дерево каталога и порядок отображения</p></div><button type="button" id="add-category" class="button primary">Добавить категорию +</button></div><div class="table-scroll"><table><thead><tr><th>Название</th><th>Slug</th><th>Порядок</th><th>Статус</th><th>Действия</th></tr></thead><tbody id="admin-categories"></tbody></table></div></section>
<section id="tab-reports" class="admin-report-panel" role="tabpanel" aria-labelledby="tab-button-reports" hidden><form id="report-form" class="panel report-filter"><label>С даты<input id="date-from" type="date" required></label><label>По дату<input id="date-to" type="date" required></label><button class="button primary" type="submit">Показать</button><span class="muted">Время: {{ timezone }}</span></form><div id="report-stats" class="stat-grid"></div><div class="report-grid"><section class="panel"><h2>Продажи по дням</h2><div class="table-scroll"><table><thead><tr><th>Дата</th><th>Чеков</th><th>Выручка</th></tr></thead><tbody id="report-days"></tbody></table></div></section><section class="panel"><h2>Категории</h2><div class="table-scroll"><table><thead><tr><th>Название</th><th>Выручка</th></tr></thead><tbody id="report-categories"></tbody></table></div></section><section class="panel report-products"><h2>Продажи по товарам</h2><div class="table-scroll"><table><thead><tr><th>Товар</th><th>Количество</th><th>Выручка</th></tr></thead><tbody id="report-products"></tbody></table></div></section></div></section>
<section id="tab-stock" class="panel admin-panel" role="tabpanel" aria-labelledby="tab-button-stock" hidden><div class="section-head"><div><h2>Пора пополнить полки</h2><p class="muted">Доступный остаток на уровне минимального или ниже</p></div><button class="button secondary" id="refresh-stock" type="button">Обновить ↻</button></div><div class="table-scroll"><table><thead><tr><th>Товар</th><th>Доступно</th><th>Минимум</th><th>Действие</th></tr></thead><tbody id="low-stock"></tbody></table></div><div id="stock-pagination" class="pagination"></div></section>
<section id="tab-review" class="panel admin-panel" role="tabpanel" aria-labelledby="tab-button-review" hidden><div class="section-head"><div><h2>Платежи на разбор</h2><p class="muted">Проверьте спорные платежи до ручного решения</p></div><button class="button secondary" id="refresh-review" type="button">Обновить ↻</button></div><div class="table-scroll"><table><thead><tr><th>Платёж</th><th>Сумма</th><th>Статус</th><th>Причина</th><th>Проверка</th></tr></thead><tbody id="payment-review"></tbody></table></div><div id="review-pagination" class="pagination"></div></section>
<dialog id="product-dialog"><form id="product-form"><div class="dialog-head"><h2 id="product-dialog-title">Новый товар</h2><button type="button" class="icon-button" data-close-dialog aria-label="Закрыть">×</button></div><input type="hidden" name="public_id"><div class="form-grid"><label class="span-two">Название<input name="name" maxlength="200" required></label><label>Штрихкод EAN-8/13<input name="barcode" inputmode="numeric" pattern="[0-9]{8}|[0-9]{13}" required></label><label>Категория<select name="category_id" required></select></label><label>Единица<select name="unit"><option value="PIECE">Штуки</option><option value="KG">Килограммы</option></select></label><label>Цена, ₸ за шт. / кг<input name="price" inputmode="decimal" placeholder="0,00" required></label><label id="initial-stock-label">Начальный остаток, шт. / г<input name="stock_quantity" type="number" min="0" max="2147483647" step="1" value="0" required></label><label>Минимальный остаток, шт. / г<input name="min_stock_quantity" type="number" min="0" max="2147483647" step="1" value="0" required></label><label class="span-two">Описание<textarea name="description" rows="3" maxlength="2000"></textarea></label><label class="checkbox-label span-two"><input name="is_active" type="checkbox" checked>Товар доступен для продажи</label></div><p class="field-help">Для весовых товаров остаток указывается в целых граммах. Изменение остатков ведётся отдельно.</p><button class="button primary wide" type="submit">Сохранить товар</button></form></dialog>
<dialog id="category-dialog"><form id="category-form"><div class="dialog-head"><h2 id="category-dialog-title">Новая категория</h2><button type="button" class="icon-button" data-close-dialog aria-label="Закрыть">×</button></div><input name="public_id" type="hidden"><label>Название<input name="name" maxlength="100" required></label><label>Slug<input name="slug" pattern="[a-z0-9]+(-[a-z0-9]+)*" maxlength="100" placeholder="molochnye-produkty" required></label><label>Родительская категория<select name="parent_id"></select></label><label>Порядок<input name="sort_order" type="number" step="1" value="0" min="-2147483648" max="2147483647" required></label><label class="checkbox-label"><input name="is_active" type="checkbox" checked>Категория активна</label><button class="button primary wide" type="submit">Сохранить категорию</button></form></dialog>
<dialog id="stock-dialog"><form id="stock-form"><div class="dialog-head"><h2>Изменить остаток</h2><button type="button" class="icon-button" data-close-dialog aria-label="Закрыть">×</button></div><input name="public_id" type="hidden"><p id="stock-product-name" class="muted"></p><label>Операция<select name="reason"><option value="RESTOCK">Поставка</option><option value="ADJUSTMENT">Корректировка</option></select></label><label id="stock-delta-label">Изменение, шт. / г<input name="delta" type="number" min="-2147483647" max="2147483647" step="1" required placeholder="Например, 10 или -2"></label><p class="field-help">Положительное значение добавляет остаток, отрицательное уменьшает. Зарезервированный товар списать нельзя.</p><button class="button primary wide" type="submit">Применить изменение</button></form></dialog>
{% endblock %}
````

app/templates/base.html

````html
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark light">
  <title>{% block title %}QR Mini-Market{% endblock %}</title>
  <link rel="icon" href="/static/mark.svg" type="image/svg+xml">
  <link rel="stylesheet" href="/static/shop.css">
  <script src="/static/shop.js" defer></script>
</head>
<body data-page="{{ page }}" data-timezone="{{ timezone }}" data-development="{{ 'true' if development else 'false' }}" {% block data %}{% endblock %}>
  <a class="skip-link" href="#main">К содержимому</a>
  <header class="topbar">
    <a class="brand" href="{{ '/cashier' if user else '/price-check' }}" aria-label="QR Mini-Market — главная"><span class="brand-mark" aria-hidden="true">m<span>•</span></span><span>mini<span class="brand-light">market</span><small>ПРОСТО. БЫСТРО. ПО QR.</small></span></a>
    <nav aria-label="Основная навигация">
      {% if user %}<a href="/cashier" {% if page == 'cashier' %}aria-current="page"{% endif %}>Касса</a>{% endif %}
      <a href="/price-check" {% if page == 'price-check' %}aria-current="page"{% endif %}>Проверка цены</a>
      {% if user and user.role.value == 'ADMIN' %}<a href="/admin" {% if page == 'admin' %}aria-current="page"{% endif %}>Управление</a>{% endif %}
    </nav>
    <div class="header-end">{% if user %}<span class="user-label">{{ user.username }}</span><button id="logout" class="button ghost small" type="button">Выйти</button>{% else %}<span class="demo-badge">DEMO · KZT</span>{% endif %}</div>
  </header>
  <main id="main" class="page-shell">{% block content %}{% endblock %}</main>
  <div id="notice" class="notice" role="status" aria-live="polite" hidden></div>
  <footer class="site-footer"><span>QR Mini-Market</span><span>Учебный проект · без реальных платежей</span><span>Сделано для удобных покупок</span></footer>
</body>
</html>
````

app/templates/cashier.html

````html
{% extends 'base.html' %}
{% block title %}Касса · QR Mini-Market{% endblock %}
{% block content %}
<div class="page-heading"><div><span class="eyebrow">РАБОЧЕЕ МЕСТО</span><h1>Касса <span class="heading-dot"></span></h1></div><div class="heading-actions"><span class="terminal-label" id="terminal-label">Терминал main</span><a id="display-link" class="button secondary" href="/display/main" target="_blank" rel="noopener">Экран покупателя ↗</a></div></div>
<div class="cashier-layout">
  <section class="catalog-area" aria-label="Каталог товаров"><div class="panel scan-panel"><form id="scan-form" class="scan-form"><label class="scan-icon" for="barcode" aria-label="Штрихкод">▥</label><input id="barcode" autocomplete="off" inputmode="numeric" placeholder="Сканируйте штрихкод и нажмите Enter" aria-label="Штрихкод товара" autofocus><button class="button primary" type="submit">Добавить ↵</button></form></div><div class="catalog-toolbar"><h2>Каталог <span id="product-count" class="count"></span></h2><input type="search" id="product-search" placeholder="Найти товар по названию" aria-label="Поиск товара"></div><div id="category-chips" class="category-chips" aria-label="Категории"></div><div id="product-grid" class="product-grid"><p class="empty-note">Загружаем товары…</p></div><div id="catalog-pagination" class="pagination"></div></section>
  <aside class="panel order-panel" aria-label="Текущий чек"><div class="order-header"><div><span class="eyebrow">ТЕКУЩИЙ ЧЕК</span><h2 id="order-number">Начните покупку</h2></div><span id="order-status" class="status muted-status">Нет чека</span></div><div id="order-empty" class="order-empty"><div class="empty-symbol" aria-hidden="true">▤</div><h3>Здесь появятся покупки</h3><p>Откройте новый чек и добавьте<br>товары из каталога или сканером.</p><button type="button" id="create-order" class="button primary">Открыть чек +</button></div><div id="order-items" class="order-items"></div><div id="payment-panel" class="payment-box" hidden></div><div class="order-bottom"><div class="total-row"><span>К оплате</span><strong id="order-total">0,00 ₸</strong></div><div id="order-actions" class="order-actions"></div><p class="order-footnote">Оплата через учебный банк</p></div></aside>
</div>
<dialog id="quantity-dialog"><form id="quantity-form"><div class="dialog-head"><h2 id="quantity-title">Вес товара</h2><button type="button" class="icon-button" data-close-dialog aria-label="Закрыть">×</button></div><p id="quantity-product" class="muted"></p><label id="quantity-label" for="quantity-value">Количество, граммы</label><input id="quantity-value" type="number" min="1" max="2147483647" step="1" required inputmode="numeric"><p class="field-help" id="quantity-help">Например, 500 = 0,5 кг. Введите целые граммы.</p><button class="button primary wide" type="submit">Добавить в чек</button></form></dialog>
{% endblock %}
````

app/templates/display.html

````html
{% extends 'base.html' %}
{% block title %}Ваши покупки · QR Mini-Market{% endblock %}
{% block data %}data-terminal="{{ terminal_code }}"{% endblock %}
{% block content %}
<div class="page-heading"><div><span class="eyebrow">ПРИЯТНО ВАС ВИДЕТЬ</span><h1>Ваши покупки</h1></div><span class="live-indicator" id="connection-status">Обновление каждые 1,5 секунды</span></div>
<section id="display-idle" class="panel welcome-display"><span class="welcome-icon" aria-hidden="true">m<span>•</span></span><span class="eyebrow">ДОБРО ПОЖАЛОВАТЬ</span><h2>Маленький магазин.<br><span class="mint">Приятные покупки.</span></h2><p>Кассир добавит товары — они появятся здесь.<br>Когда всё будет готово, оплатите покупку по QR.</p><div class="welcome-steps"><span>01 &nbsp; Выберите товары</span><span>02 &nbsp; Отсканируйте QR</span><span>03 &nbsp; Заберите покупки</span></div></section>
<div id="display-order" class="display-layout" hidden><section class="panel display-cart"><div class="section-head"><h2 id="display-order-number">Ваш чек</h2><span id="display-item-count" class="muted"></span></div><div id="display-items"></div><div class="total-row display-total"><span>Итого</span><strong id="display-total">0,00 ₸</strong></div></section><section id="display-payment" class="panel display-pay" aria-live="polite"></section></div>
{% endblock %}
````

app/templates/login.html

````html
{% extends 'base.html' %}
{% block title %}Вход · QR Mini-Market{% endblock %}
{% block content %}
<section class="login-layout">
  <div class="login-story"><span class="eyebrow">КАССА НОВОГО РИТМА</span><h1>Меньше ожидания.<br><span>Больше удобства.</span></h1><p>Товары, чеки и оплата по QR —<br>в одном рабочем пространстве.</p><div class="story-art" aria-hidden="true"><div class="art-orbit"></div><div class="art-receipt"><span>mini<span class="mint">market</span></span><div class="art-lines"></div><div class="art-lines short"></div><div class="art-total">Всё под контролем <b>✓</b></div><div class="art-barcode"></div></div><div class="art-chip">↗ &nbsp; Оплата по QR</div></div><div class="story-footer"><span>01 &nbsp; Сканируйте</span><span>02 &nbsp; Принимайте оплату</span><span>03 &nbsp; Готово</span></div></div>
  <section class="panel login-card"><span class="eyebrow">РАБОЧЕЕ ПРОСТРАНСТВО</span><h2>С возвращением</h2><p class="muted">Войдите в аккаунт кассира или администратора.</p><form id="login-form"><label for="username">Логин</label><input id="username" name="username" autocomplete="username" required maxlength="100" autofocus placeholder="Ваш логин"><label for="password">Пароль</label><input id="password" name="password" type="password" autocomplete="current-password" required placeholder="Введите пароль"><div id="login-error" class="form-error" role="alert" hidden></div><button class="button primary wide" type="submit">Войти в магазин <span aria-hidden="true">→</span></button></form><p class="login-note">Доступ выдаёт администратор магазина.<br>Платежи в этом проекте учебные.</p></section>
</section>
{% endblock %}
````

app/templates/price-check.html

````html
{% extends 'base.html' %}
{% block title %}Проверка цены · QR Mini-Market{% endblock %}
{% block content %}
<section class="price-hero"><span class="eyebrow">ЗНАТЬ ЦЕНУ — ПРОСТО</span><h1>Сколько стоит<br><span class="mint">хорошая покупка?</span></h1><p>Сканируйте штрихкод или найдите товар по названию.<br>Это только проверка цены — покупка не оформляется.</p><form id="price-search-form" class="price-search"><label class="visually-hidden" for="price-search">Штрихкод или название товара</label><input id="price-search" type="search" autocomplete="off" placeholder="Штрихкод или название товара" autofocus><button class="button primary" type="submit">Найти →</button></form></section><div id="price-categories" class="category-chips centered" aria-label="Категории"></div><div class="section-head"><h2 id="price-heading">Товары магазина</h2><span class="muted" id="price-count"></span></div><section id="price-results" class="product-grid price-grid" aria-live="polite"><p class="empty-note">Загружаем товары…</p></section><div id="price-pagination" class="pagination"></div>
{% endblock %}
````

app/templates/receipt.html

````html
{% extends 'base.html' %}
{% block title %}Чек · QR Mini-Market{% endblock %}
{% block data %}data-order="{{ order_uuid }}"{% endblock %}
{% block content %}
<div class="receipt-actions"><a class="button secondary" href="/cashier">← Вернуться на кассу</a><button id="print-receipt" class="button primary" type="button" disabled>Распечатать чек</button></div><article id="receipt" class="receipt-paper"><div class="receipt-brand">mini<b>market</b></div><p class="receipt-subtitle">Спасибо за покупку!</p><div id="receipt-content"><p>Загружаем чек…</p></div><p class="receipt-disclaimer">Учебный проект, не фискальный чек<br>Реальные деньги не списываются.</p></article>
{% endblock %}
````

docker-compose.yml

````yaml
services:
  shop:
    build: .
    image: qr-mini-market:local
    command: ["shop"]
    init: true
    restart: unless-stopped
    env_file: .env
    environment:
      DATABASE_URL: sqlite:////data/shop.db
      BANK_BASE_URL: http://mock_bank:8001
      BANK_MERCHANT_API_KEY: "${BANK_MERCHANT_API_KEY:?Set BANK_MERCHANT_API_KEY in .env}"
      WEBHOOK_SECRET: "${WEBHOOK_SECRET:?Set WEBHOOK_SECRET in .env}"
      SECRET_KEY: "${SECRET_KEY:?Set SECRET_KEY in .env}"
    ports:
      - "8000:8000"
    volumes:
      - shop_data:/data
    depends_on:
      mock_bank:
        condition: service_healthy
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - >-
          import urllib.request;
          urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8000/health', timeout=3).read()
      interval: 10s
      timeout: 5s
      start_period: 20s
      retries: 5

  mock_bank:
    build: .
    image: qr-mini-market:local
    command: ["mock_bank"]
    init: true
    restart: unless-stopped
    env_file: .env
    environment:
      BANK_DATABASE_URL: sqlite:////data/bank.db
      SHOP_WEBHOOK_URL: http://shop:8000/api/v1/webhooks/mock-bank
      BANK_PUBLIC_URL: "${BANK_PUBLIC_URL:?Set BANK_PUBLIC_URL in .env}"
      BANK_MERCHANT_API_KEY: "${BANK_MERCHANT_API_KEY:?Set BANK_MERCHANT_API_KEY in .env}"
      WEBHOOK_SECRET: "${WEBHOOK_SECRET:?Set WEBHOOK_SECRET in .env}"
    ports:
      - "8001:8001"
    volumes:
      - bank_data:/data
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - >-
          import urllib.request;
          urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8001/health', timeout=3).read()
      interval: 10s
      timeout: 5s
      start_period: 20s
      retries: 5

volumes:
  shop_data:
  bank_data:
````

docs/VERIFICATION.md

````markdown
# Протокол проверки QR Mini-Market

Проверено 10 октября 2026 года в Linux, Python 3.12.14.

## Общий прогон

```text
414 passed, 14 warnings in 41.08s
Required test coverage of 80% reached. Total coverage: 95.46%
Ruff: All checks passed!
Ruff format: all files already formatted
pip check: No broken requirements found.
```

Команда:

```bash
.venv/bin/python -m pytest -q --cov=app.services --cov=mock_bank.service --cov=mock_bank.notifier --cov-report=term-missing --cov-fail-under=80
```

| Модуль | Покрытие строк |
| --- | ---: |
| `app/services/auth.py` | 94.96% |
| `app/services/catalog.py` | 98.95% |
| `app/services/orders.py` | 98.73% |
| `app/services/payments.py` | 89.07% |
| `app/services/qr_service.py` | 92.86% |
| `app/services/reports.py` | 100.00% |
| `mock_bank/notifier.py` | 98.39% |
| `mock_bank/service.py` | 99.13% |

14 предупреждений исходят из интеграции Starlette TestClient с httpx и передачи timeout в TestClient. Предупреждения не отключены. Требуемый ТЗ httpx сохранён.

## Два настоящих сервера

Выполнена команда `.venv/bin/python tests/e2e/smoke_tcp.py`. Сценарий создаёт временные БД и секреты, запускает два отдельных Uvicorn-процесса и общается с ними по TCP:

```text
Migration, idempotent seeds, and generated admin: OK
Real TCP: 3 piece products + weighted item + QR + signed webhook + PAID: OK
Real TCP: insufficient funds + webhook + order reopened: OK
Real TCP: background expiry + reserve released + public pages: OK
Both Uvicorn processes stopped cleanly; temporary databases removed: OK
```

Проверены фактические списания товара и баланса, снятие резерва, приём подписанного уведомления, отказ при недостатке денег, настоящее фоновое истечение счёта и штатная остановка. Этот subprocess-сценарий запускался в Linux.

## Проверка в настоящем браузере

Headless Chromium 133 + Playwright: выполнены вход с cookie, создание чека, скан штучного товара, ввод 333 г картофеля, итог 723,26 ₸, checkout и загрузка PNG QR. После подтверждения через FakeProvider касса и публичный экран показали PAID; открыты печатный чек, продажи, низкие остатки, разбор платежей и публичный поиск по EAN.

Ошибок JavaScript не было. Проверены ширины 1440 и 375 пикселей; горизонтальный выход длинного номера чека исправлен. На мобильном экране QR не меньше 300 пикселей. Браузерная проверка использовала FakeProvider; настоящий Mock Bank отдельно проверен сквозными HTTP-тестами и двумя Uvicorn-процессами выше.

Пример мобильного экрана из проверочного сценария (ссылка ведёт на тестовый провайдер):

![Экран покупателя](screenshots/display-mobile.png)

## Остальные проверки

- Alembic: upgrade head, соответствие metadata, downgrade base и повторный upgrade; откат DDL атомарен. Head: `0002_commerce`.
- SQL миграций PostgreSQL скомпилирован offline; живого PostgreSQL-сервера не было.
- `node --check` для shop.js, bank.js и money.js; Node-тест точного форматирования сумм вплоть до int64 прошёл.
- Docker: shell-синтаксис entrypoint, структура YAML, Python healthchecks, порядок миграции/seed/запуска и остановка при ошибке. Docker отсутствует, сборка и запуск образа не выполнялись.
- Защита API: роли, JWT, Secure-cookie, CSRF, Origin, подписи, повторы, отсутствие внутренних ID и точных остатков в публичном каталоге.
- Конкурентность: последняя единица товара, повторный checkout, два банковских списания, оплата против отмены, два обработчика webhook и атомарный rollback.
- Windows и macOS не запускались; для них подготовлены команды в README.

## Финальный чек-лист ревью

- [x] Два сервиса с отдельными БД и без взаимных импортов.
- [x] Деньги и вес рассчитываются сервером в целых числах; UI форматирует BigInt.
- [x] Полный каталог, касса, QR, банк, чек, админка, роли и отчёты.
- [x] Снимки цен и журнал движения товара; резерв атомарен.
- [x] Неопределённый результат банка сохраняет резерв до сверки.
- [x] Подписанные события и итог продажи сохраняются атомарно; дубликаты безопасны.
- [x] Миграции и идемпотентные seed; пароли вводятся интерактивно.
- [x] Все тесты прошли, покрытие выше 80%, Ruff чистый.
- [x] Docker-конфигурация и инструкции запуска включены.
- [x] Ограничения и невыполненные платформенные проверки указаны явно.
````

migrations/env.py

````python
"""Run synchronous migrations with the application's engine configuration."""

from logging.config import fileConfig
from pathlib import Path
from typing import Literal

from alembic import context
from alembic.autogenerate.api import AutogenContext
from sqlalchemy import make_url
from sqlalchemy.engine import Connection

import app.models  # noqa: F401
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import create_db_engine
from app.db.types import UTCDateTime

config = context.config
if config.config_file_name is not None and Path(config.config_file_name).is_file():
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def render_item(kind: str, item: object, _autogen_context: AutogenContext) -> str | Literal[False]:
    """Snapshot the physical type without importing mutable application code in revisions."""
    if kind == "type" and isinstance(item, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def run_migrations_offline() -> None:
    """Emit SQL without opening a database connection."""
    connection = config.attributes.get("connection")
    url = connection.engine.url if connection is not None else make_url(get_settings().database_url)
    is_sqlite = url.get_backend_name() == "sqlite"
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=is_sqlite,
        compare_type=True,
        render_item=render_item,
        transactional_ddl=True if is_sqlite else None,
    )
    with context.begin_transaction():
        context.run_migrations()


def migrate_connection(connection: Connection) -> None:
    """Run migrations while preserving ownership of a supplied connection."""
    is_sqlite = connection.dialect.name == "sqlite"
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=is_sqlite,
        compare_type=True,
        render_item=render_item,
        # The shared engine factory fixes SQLite's legacy DDL transaction behavior.
        transactional_ddl=True if is_sqlite else None,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Use a caller-owned connection or create and clean up an engine."""
    connection = config.attributes.get("connection")
    if connection is not None:
        migrate_connection(connection)
        return

    engine = create_db_engine(get_settings().database_url)
    try:
        with engine.connect() as connection:
            migrate_connection(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
````

migrations/script.py.mako

````text
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | Sequence[str] | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """Upgrade schema."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Downgrade schema."""
    ${downgrades if downgrades else "pass"}
````

migrations/versions/0001_catalog.py

````python
"""Create categories and products.

Revision ID: 0001_catalog
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_catalog"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(create_constraint=True, name=op.f("ck_categories_active_bool")),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(name) BETWEEN 1 AND 100", name=op.f("ck_categories_name_length")
        ),
        sa.CheckConstraint(
            "length(slug) BETWEEN 1 AND 100", name=op.f("ck_categories_slug_length")
        ),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name=op.f("ck_categories_not_own_parent")
        ),
        sa.CheckConstraint(
            "sort_order BETWEEN -2147483648 AND 2147483647 "
            "AND sort_order = CAST(sort_order AS INTEGER)",
            name=op.f("ck_categories_sort_order_range"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["categories.id"],
            name=op.f("fk_categories_parent_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint("public_id", name=op.f("uq_categories_public_id")),
        sa.UniqueConstraint("slug", name=op.f("uq_categories_slug")),
    )
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("name_normalized", sa.String(600), nullable=False),
        sa.Column("barcode", sa.String(13), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column(
            "unit",
            sa.Enum(
                "PIECE",
                "KG",
                native_enum=False,
                create_constraint=True,
                name=op.f("ck_products_product_unit"),
            ),
            nullable=False,
        ),
        sa.Column("price_minor", sa.BigInteger(), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reserved_quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("min_stock_quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(create_constraint=True, name=op.f("ck_products_active_bool")),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column("description", sa.String(2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 200", name=op.f("ck_products_name_length")),
        sa.CheckConstraint(
            "length(name_normalized) BETWEEN 1 AND 600",
            name=op.f("ck_products_name_normalized_length"),
        ),
        sa.CheckConstraint("length(barcode) IN (8, 13)", name=op.f("ck_products_barcode_length")),
        sa.CheckConstraint(
            "description IS NULL OR length(description) <= 2000",
            name=op.f("ck_products_description_length"),
        ),
        sa.CheckConstraint(
            "price_minor BETWEEN 0 AND 9223372036854775807 "
            "AND price_minor = CAST(price_minor AS BIGINT)",
            name=op.f("ck_products_price_range"),
        ),
        sa.CheckConstraint(
            "stock_quantity BETWEEN 0 AND 2147483647 "
            "AND stock_quantity = CAST(stock_quantity AS INTEGER)",
            name=op.f("ck_products_stock_range"),
        ),
        sa.CheckConstraint(
            "reserved_quantity BETWEEN 0 AND 2147483647 "
            "AND reserved_quantity = CAST(reserved_quantity AS INTEGER)",
            name=op.f("ck_products_reserved_range"),
        ),
        sa.CheckConstraint(
            "min_stock_quantity BETWEEN 0 AND 2147483647 "
            "AND min_stock_quantity = CAST(min_stock_quantity AS INTEGER)",
            name=op.f("ck_products_min_stock_range"),
        ),
        sa.CheckConstraint(
            "reserved_quantity <= stock_quantity", name=op.f("ck_products_reserved_within_stock")
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_products_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("public_id", name=op.f("uq_products_public_id")),
    )
    op.create_index("ix_products_barcode", "products", ["barcode"], unique=True)
    op.create_index("ix_products_category_id", "products", ["category_id"])
    op.create_index("ix_products_name_normalized", "products", ["name_normalized"])


def downgrade() -> None:
    op.drop_table("products")
    # SQLite RESTRICT also applies while dropping a populated self-referencing table.
    op.execute("UPDATE categories SET parent_id = NULL")
    op.drop_table("categories")
````

migrations/versions/0002_commerce.py

````python
"""Add users orders payments and stock ledger

Revision ID: 0002_commerce
Revises: 0001_catalog
Create Date: 2026-10-10 05:57:15.907599
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_commerce"
down_revision: str | Sequence[str] | None = "0001_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "ADMIN", "CASHIER", name="user_role", native_enum=False, create_constraint=False
            ),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(create_constraint=False, name="active_bool"),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('ADMIN', 'CASHIER')", name=op.f("ck_users_user_role")),
        sa.CheckConstraint("is_active IN (0, 1)", name=op.f("ck_users_active_bool")),
        sa.CheckConstraint(
            "length(username) BETWEEN 3 AND 64", name=op.f("ck_users_username_length")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("public_id", name=op.f("uq_users_public_id")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.String(length=64), nullable=False),
        sa.Column("terminal_code", sa.String(length=64), server_default="main", nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "OPEN",
                "PENDING_PAYMENT",
                "PAID",
                "CANCELLED",
                name="order_status",
                native_enum=False,
                create_constraint=False,
            ),
            server_default="OPEN",
            nullable=False,
        ),
        sa.Column("total_minor", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="KZT", nullable=False),
        sa.Column("cashier_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("currency = 'KZT'", name=op.f("ck_orders_currency")),
        sa.CheckConstraint(
            "status IN ('OPEN', 'PENDING_PAYMENT', 'PAID', 'CANCELLED')",
            name=op.f("ck_orders_order_status"),
        ),
        sa.CheckConstraint(
            "length(terminal_code) BETWEEN 1 AND 64", name=op.f("ck_orders_terminal_length")
        ),
        sa.CheckConstraint(
            "total_minor BETWEEN 0 AND 9223372036854775807 "
            "AND total_minor = CAST(total_minor AS BIGINT)",
            name=op.f("ck_orders_total_range"),
        ),
        sa.ForeignKeyConstraint(
            ["cashier_id"],
            ["users.id"],
            name=op.f("fk_orders_cashier_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.UniqueConstraint("number", name=op.f("uq_orders_number")),
        sa.UniqueConstraint("public_id", name=op.f("uq_orders_public_id")),
    )
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.create_index(
            "ix_orders_status_terminal_code", ["status", "terminal_code"], unique=False
        )
        batch_op.create_index(
            "uq_orders_active_terminal",
            ["terminal_code"],
            unique=True,
            sqlite_where=sa.text("status IN ('OPEN', 'PENDING_PAYMENT')"),
            postgresql_where=sa.text("status IN ('OPEN', 'PENDING_PAYMENT')"),
        )

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("barcode", sa.String(length=13), nullable=False),
        sa.Column(
            "unit",
            sa.Enum("PIECE", "KG", name="product_unit", native_enum=False, create_constraint=False),
            nullable=False,
        ),
        sa.Column("unit_price_minor", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("line_total_minor", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("unit IN ('PIECE', 'KG')", name=op.f("ck_order_items_product_unit")),
        sa.CheckConstraint(
            "line_total_minor BETWEEN 0 AND 9223372036854775807 "
            "AND line_total_minor = CAST(line_total_minor AS BIGINT)",
            name=op.f("ck_order_items_total_range"),
        ),
        sa.CheckConstraint(
            "quantity BETWEEN 1 AND 2147483647 AND quantity = CAST(quantity AS INTEGER)",
            name=op.f("ck_order_items_quantity_range"),
        ),
        sa.CheckConstraint(
            "unit_price_minor BETWEEN 0 AND 9223372036854775807 "
            "AND unit_price_minor = CAST(unit_price_minor AS BIGINT)",
            name=op.f("ck_order_items_price_range"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_order_items_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_order_items_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_items")),
        sa.UniqueConstraint(
            "order_id", "product_id", name=op.f("uq_order_items_order_id_product_id")
        ),
        sa.UniqueConstraint("public_id", name=op.f("uq_order_items_public_id")),
    )
    with op.batch_alter_table("order_items", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_order_items_order_id"), ["order_id"], unique=False)

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), server_default="mock_bank", nullable=False),
        sa.Column("provider_invoice_id", sa.String(length=64), nullable=True),
        sa.Column("creation_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creation_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="KZT", nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "SUCCEEDED",
                "FAILED",
                "EXPIRED",
                "CANCELLED",
                name="payment_status",
                native_enum=False,
                create_constraint=False,
            ),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("pay_url", sa.String(length=2048), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(length=100), nullable=True),
        sa.Column(
            "needs_review",
            sa.Boolean(create_constraint=False, name="review_bool"),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("review_reason", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("currency = 'KZT'", name=op.f("ck_payments_currency")),
        sa.CheckConstraint(
            "creation_attempts >= 0", name=op.f("ck_payments_creation_attempts_nonnegative")
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SUCCEEDED', 'FAILED', 'EXPIRED', 'CANCELLED')",
            name=op.f("ck_payments_payment_status"),
        ),
        sa.CheckConstraint(
            "amount_minor BETWEEN 1 AND 9223372036854775807 "
            "AND amount_minor = CAST(amount_minor AS BIGINT)",
            name=op.f("ck_payments_amount_range"),
        ),
        sa.CheckConstraint("needs_review IN (0, 1)", name=op.f("ck_payments_review_bool")),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_payments_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.UniqueConstraint("provider_invoice_id", name=op.f("uq_payments_provider_invoice_id")),
        sa.UniqueConstraint("public_id", name=op.f("uq_payments_public_id")),
    )
    with op.batch_alter_table("payments", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_payments_order_id"), ["order_id"], unique=False)
        batch_op.create_index(
            "ix_payments_status_expires_at", ["status", "expires_at"], unique=False
        )
        batch_op.create_index(
            "uq_payments_pending_order",
            ["order_id"],
            unique=True,
            sqlite_where=sa.text("status = 'PENDING'"),
            postgresql_where=sa.text("status = 'PENDING'"),
        )

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column(
            "reason",
            sa.Enum(
                "SALE",
                "RESTOCK",
                "ADJUSTMENT",
                name="stock_reason",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reason IN ('SALE', 'RESTOCK', 'ADJUSTMENT')",
            name=op.f("ck_stock_movements_stock_reason"),
        ),
        sa.CheckConstraint(
            "delta BETWEEN -2147483647 AND 2147483647 AND delta <> 0 "
            "AND delta = CAST(delta AS INTEGER)",
            name=op.f("ck_stock_movements_delta_range"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_stock_movements_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_stock_movements_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_movements")),
    )
    with op.batch_alter_table("stock_movements", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_stock_movements_order_id"), ["order_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_stock_movements_product_id"), ["product_id"], unique=False
        )

    op.create_table(
        "payment_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_event_id", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("raw_body", sa.Text(), nullable=False),
        sa.Column(
            "signature_valid",
            sa.Boolean(create_constraint=False, name="signature_bool"),
            nullable=False,
        ),
        sa.Column("outcome", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "signature_valid IN (0, 1)", name=op.f("ck_payment_events_signature_bool")
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            name=op.f("fk_payment_events_payment_id_payments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_events")),
        sa.UniqueConstraint(
            "provider",
            "provider_event_id",
            name=op.f("uq_payment_events_provider_provider_event_id"),
        ),
    )
    with op.batch_alter_table("payment_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_payment_events_payment_id"), ["payment_id"], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("payment_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_payment_events_payment_id"))

    op.drop_table("payment_events")
    with op.batch_alter_table("stock_movements", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_stock_movements_product_id"))
        batch_op.drop_index(batch_op.f("ix_stock_movements_order_id"))

    op.drop_table("stock_movements")
    with op.batch_alter_table("payments", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_payments_pending_order",
            sqlite_where=sa.text("status = 'PENDING'"),
            postgresql_where=sa.text("status = 'PENDING'"),
        )
        batch_op.drop_index("ix_payments_status_expires_at")
        batch_op.drop_index(batch_op.f("ix_payments_order_id"))

    op.drop_table("payments")
    with op.batch_alter_table("order_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_order_items_order_id"))

    op.drop_table("order_items")
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_orders_active_terminal",
            sqlite_where=sa.text("status IN ('OPEN', 'PENDING_PAYMENT')"),
            postgresql_where=sa.text("status IN ('OPEN', 'PENDING_PAYMENT')"),
        )
        batch_op.drop_index("ix_orders_status_terminal_code")

    op.drop_table("orders")
    op.drop_table("users")
````

mock_bank/__init__.py

````python
"""Independent educational bank emulator; never handles real payments."""
````

mock_bank/config.py

````python
"""Bank-only configuration without import-time environment access."""

from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        hide_input_in_errors=True,
        frozen=True,
    )
    bank_database_url: str = Field(default="sqlite:///./bank.db", min_length=1, repr=False)
    bank_public_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8001")
    shop_webhook_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8000/api/v1/webhooks/mock-bank")
    merchant_name: str = Field(default="QR Mini-Market", min_length=1, max_length=200)
    bank_merchant_api_key: SecretStr = Field(repr=False)
    webhook_secret: SecretStr = Field(repr=False)

    @field_validator("bank_merchant_api_key", "webhook_secret")
    @classmethod
    def validate_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret) < 32 or any(character.isspace() for character in secret):
            raise ValueError("Secrets must contain at least 32 characters and no whitespace")
        if secret.casefold().startswith(("change-me", "changeme", "replace-me", "your-secret")):
            raise ValueError("Replace example secrets with independently generated values")
        return value

    @field_validator("bank_public_url", "shop_webhook_url")
    @classmethod
    def validate_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.username is not None or value.password is not None or value.fragment is not None:
            raise ValueError("Service URLs must not contain credentials or fragments")
        return value

    @field_validator("bank_public_url")
    @classmethod
    def validate_origin(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.query is not None or value.path not in (None, "/"):
            raise ValueError("BANK_PUBLIC_URL must contain only an HTTP(S) origin")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
````

mock_bank/db.py

````python
"""Independent synchronous database and bounded local transaction retries."""

import sqlite3
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeVar

from sqlalchemy import DateTime, create_engine, event, make_url
from sqlalchemy.engine import Connection, Dialect, Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator

T = TypeVar("T")


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("UTCDateTime requires an aware datetime")
        value = value.astimezone(UTC)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def create_db_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    if url.drivername not in {
        "sqlite",
        "sqlite+pysqlite",
        "postgresql",
        "postgresql+psycopg",
        "postgresql+psycopg2",
    }:
        raise ValueError("BANK_DATABASE_URL requires synchronous SQLite or PostgreSQL")
    if url.get_backend_name() != "sqlite":
        return create_engine(url, pool_pre_ping=True, hide_parameters=True)
    memory = url.database in (None, "", ":memory:")
    args = {"check_same_thread": False, "timeout": 5}
    if hasattr(sqlite3, "LEGACY_TRANSACTION_CONTROL"):
        args["autocommit"] = sqlite3.LEGACY_TRANSACTION_CONTROL
    engine = create_engine(
        url,
        connect_args=args,
        hide_parameters=True,
        **({"poolclass": StaticPool} if memory else {}),
    )

    @event.listens_for(engine, "connect")
    def configure(connection: sqlite3.Connection, _record: object) -> None:
        connection.isolation_level = None
        with_cursor = connection.cursor()
        try:
            with_cursor.execute("PRAGMA foreign_keys=ON")
            with_cursor.execute("PRAGMA busy_timeout=5000")
            with_cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            with_cursor.close()

    @event.listens_for(engine, "begin")
    def begin(connection: Connection) -> None:
        immediate = connection.get_execution_options().get("bank_write", False)
        connection.exec_driver_sql("BEGIN IMMEDIATE" if immediate else "BEGIN")

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False, autoflush=False)


def run_write(factory: sessionmaker[Session], operation: Callable[[Session], T]) -> T:
    """Retry only local transactions, never a network operation."""
    for attempt in range(4):
        try:
            with factory.begin() as session:
                session.connection(execution_options={"bank_write": True})
                return operation(session)
        except OperationalError as exc:
            code = getattr(exc.orig, "sqlite_errorcode", 0)
            state = getattr(exc.orig, "sqlstate", None)
            retryable = (code and code & 0xFF in (5, 6)) or state in ("40001", "40P01")
            if not retryable or attempt == 3:
                raise
            time.sleep(0.02 * 2**attempt)
    raise RuntimeError("Transaction retries exhausted")
````

mock_bank/errors.py

````python
"""Public Russian error envelopes without exception messages or request input."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


class BankError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def response(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message, "details": details or {}}},
        status_code=status,
        headers={"Cache-Control": "no-store"},
    )


class SafeErrors:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        started = False

        async def track(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message["headers"] = list(message.get("headers", [])) + [
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (
                        b"content-security-policy",
                        b"default-src 'self'; script-src 'self'; style-src 'self'; "
                        b"frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
                    ),
                ]
            await send(message)

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            await self.app(scope, receive, track)
        except Exception as exc:
            logger.error("Bank request failed (%s)", type(exc).__name__)
            if started:
                raise RuntimeError("Bank response interrupted") from None
            await response(500, "INTERNAL_ERROR", "Внутренняя ошибка банка.")(scope, receive, track)


def install_errors(app: FastAPI) -> None:
    @app.exception_handler(BankError)
    def bank_error(_request: Request, exc: BankError) -> JSONResponse:
        return response(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    def validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [{"location": list(item["loc"]), "type": item["type"]} for item in exc.errors()]
        return response(422, "VALIDATION_ERROR", "Некорректные данные запроса.", {"fields": fields})

    @app.exception_handler(HTTPException)
    def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        result = response(
            exc.status_code,
            "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR",
            "Ресурс не найден." if exc.status_code == 404 else "Ошибка запроса.",
        )
        if exc.headers:
            result.headers.update(exc.headers)
        return result

    app.add_middleware(SafeErrors)
````

mock_bank/main.py

````python
"""Standalone bank application, independent of every shop module."""

import asyncio
import hmac
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from mock_bank.config import Settings, get_settings
from mock_bank.db import Base, create_db_engine, create_session_factory
from mock_bank.errors import BankError, install_errors
from mock_bank.notifier import WebhookNotifier
from mock_bank.schemas import InvoiceCreate, PayRequest
from mock_bank.service import BankService

ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def require_merchant(request: Request) -> None:
    supplied = request.headers.get("Authorization", "")
    expected = "Bearer " + request.app.state.settings.bank_merchant_api_key.get_secret_value()
    if not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise BankError(401, "UNAUTHORIZED", "Неверный ключ магазина.")


def create_app(
    settings: Settings | None = None,
    webhook_client: httpx.Client | None = None,
    run_worker: bool = True,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        active = settings if settings is not None else get_settings()
        engine = create_db_engine(active.bank_database_url)
        client = webhook_client if webhook_client is not None else httpx.Client(trust_env=False)
        stop = asyncio.Event()
        worker = None
        try:
            await asyncio.to_thread(Base.metadata.create_all, engine)
            factory = create_session_factory(engine)
            service = BankService(factory, active)
            notifier = WebhookNotifier(factory, active, client)
            application.state.settings = active
            application.state.engine = engine
            application.state.session_factory = factory
            application.state.service = service
            application.state.notifier = notifier

            async def work() -> None:
                while not stop.is_set():
                    try:
                        await asyncio.to_thread(service.sweep_expired)
                        await asyncio.to_thread(notifier.deliver_due)
                    except Exception as exc:
                        logger.error("Bank worker failed (%s)", type(exc).__name__)
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=1)
                    except TimeoutError:
                        pass

            if run_worker:
                worker = asyncio.create_task(work())
            yield
        finally:
            stop.set()
            if worker is not None:
                await worker
            if webhook_client is None:
                await asyncio.to_thread(client.close)
            await asyncio.to_thread(engine.dispose)

    application = FastAPI(
        title="Учебный Mock Bank", lifespan=lifespan, docs_url=None, redoc_url=None
    )
    install_errors(application)
    application.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    templates = Jinja2Templates(directory=ROOT / "templates")

    def schedule(request: Request, tasks: BackgroundTasks) -> BankService:
        tasks.add_task(request.app.state.notifier.deliver_due)
        return request.app.state.service

    @application.get("/health")
    def health(request: Request) -> dict:
        try:
            with request.app.state.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            raise BankError(503, "DATABASE_UNAVAILABLE", "База данных банка недоступна.") from None
        return {"status": "ok", "database": "ok"}

    @application.post("/api/merchant/invoices", dependencies=[Depends(require_merchant)])
    def create_invoice(payload: InvoiceCreate, request: Request, tasks: BackgroundTasks) -> dict:
        return schedule(request, tasks).create_invoice(payload)

    @application.get(
        "/api/merchant/invoices/{invoice_id}", dependencies=[Depends(require_merchant)]
    )
    def get_invoice(invoice_id: UUID, request: Request, tasks: BackgroundTasks) -> dict:
        return schedule(request, tasks).get_invoice(invoice_id)

    @application.post(
        "/api/merchant/invoices/{invoice_id}/cancel", dependencies=[Depends(require_merchant)]
    )
    def cancel_invoice(invoice_id: UUID, request: Request, tasks: BackgroundTasks) -> dict:
        return schedule(request, tasks).cancel(invoice_id)

    @application.get("/pay/{token}")
    def page(token: str, request: Request, tasks: BackgroundTasks):
        invoice = schedule(request, tasks).get_invoice(token)
        return templates.TemplateResponse(
            request=request,
            name="pay.html",
            context={"token": token, "invoice": invoice},
            background=tasks,
        )

    @application.get("/api/pay/{token}")
    def customer_invoice(token: str, request: Request, tasks: BackgroundTasks) -> dict:
        return schedule(request, tasks).get_invoice(token, accounts=True)

    @application.post("/api/pay/{token}")
    def pay(token: str, payload: PayRequest, request: Request, tasks: BackgroundTasks) -> dict:
        return schedule(request, tasks).pay(token, payload.account_id)

    @application.post("/api/pay/{token}/cancel")
    def cancel(token: str, request: Request, tasks: BackgroundTasks) -> dict:
        return schedule(request, tasks).cancel(token)

    @application.post("/api/pay/{token}/decline")
    def decline(token: str, request: Request, tasks: BackgroundTasks) -> dict:
        return schedule(request, tasks).decline(token)

    return application


app = create_app()
````

mock_bank/models.py

````python
"""Bank balances, invoices, immutable events, and durable delivery attempts."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Enum, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from mock_bank.db import Base, UTCDateTime, utc_now


class InvoiceStatus(StrEnum):
    CREATED = "CREATED"
    PAID = "PAID"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class BankAccount(Base):
    __tablename__ = "bank_accounts"
    __table_args__ = (
        CheckConstraint(
            "balance_minor >= 0 AND balance_minor <= 9223372036854775807", name="balance_range"
        ),
        CheckConstraint("balance_minor = CAST(balance_minor AS BIGINT)", name="balance_integer"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True, default=uuid4)
    seed_key: Mapped[str | None] = mapped_column(String(30), unique=True)
    holder_name: Mapped[str] = mapped_column(String(100))
    balance_minor: Mapped[int] = mapped_column(BigInteger())


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint(
            "amount_minor > 0 AND amount_minor <= 9223372036854775807", name="amount_positive"
        ),
        CheckConstraint("amount_minor = CAST(amount_minor AS BIGINT)", name="amount_integer"),
        CheckConstraint("currency = 'KZT'", name="invoice_currency"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True, default=uuid4)
    token: Mapped[str] = mapped_column(String(64), unique=True)
    merchant_reference: Mapped[UUID] = mapped_column(Uuid(), unique=True)
    merchant_name: Mapped[str] = mapped_column(String(200))
    amount_minor: Mapped[int] = mapped_column(BigInteger())
    currency: Mapped[str] = mapped_column(String(3), default="KZT")
    description: Mapped[str] = mapped_column(String(500))
    ttl_seconds: Mapped[int] = mapped_column()
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, native_enum=False, create_constraint=True, name="invoice_status"),
        default=InvoiceStatus.CREATED,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    paid_by_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("bank_accounts.id", ondelete="RESTRICT")
    )
    failure_reason: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)


class BankTransaction(Base):
    __tablename__ = "bank_transactions"
    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="RESTRICT"), unique=True
    )
    account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("bank_accounts.id", ondelete="RESTRICT")
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger())
    status: Mapped[str] = mapped_column(String(20))
    failure_reason: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class BankEvent(Base):
    __tablename__ = "bank_events"
    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    invoice_id: Mapped[UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="RESTRICT"), unique=True
    )
    event_type: Mapped[str] = mapped_column(String(40))
    raw_body: Mapped[str] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    delivered: Mapped[bool] = mapped_column(Boolean(), default=False)
    stopped: Mapped[bool] = mapped_column(Boolean(), default=False)
    lease_token: Mapped[UUID | None] = mapped_column(Uuid())
    lease_until: Mapped[datetime | None] = mapped_column(UTCDateTime())


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("bank_events.id", ondelete="RESTRICT"), index=True
    )
    attempt: Mapped[int] = mapped_column()
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    response_status: Mapped[int | None] = mapped_column()
    error_kind: Mapped[str | None] = mapped_column(String(100))
````

mock_bank/notifier.py

````python
"""Durable outbox with HTTP outside transactions and stable signed payloads."""

import hashlib
import hmac
from datetime import timedelta
from uuid import uuid4

import httpx
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from mock_bank.config import Settings
from mock_bank.db import run_write, utc_now
from mock_bank.models import BankEvent, WebhookDelivery

RETRY_DELAYS = (1, 5, 25)


class WebhookNotifier:
    def __init__(
        self, factory: sessionmaker[Session], settings: Settings, client: httpx.Client
    ) -> None:
        self.factory = factory
        self.settings = settings
        self.client = client

    def _claim(self) -> dict | None:
        def operation(session: Session) -> dict | None:
            now = utc_now()
            due = (
                BankEvent.delivered.is_(False),
                BankEvent.stopped.is_(False),
                BankEvent.next_attempt_at <= now,
                or_(BankEvent.lease_until.is_(None), BankEvent.lease_until <= now),
            )
            event = session.scalar(
                select(BankEvent)
                .where(*due)
                .order_by(BankEvent.next_attempt_at, BankEvent.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if event is None:
                return None
            lease = uuid4()
            if (
                session.execute(
                    update(BankEvent)
                    .where(BankEvent.id == event.id, *due)
                    .values(
                        lease_token=lease,
                        lease_until=now + timedelta(seconds=30),
                        attempts=BankEvent.attempts + 1,
                    )
                ).rowcount
                != 1
            ):
                return None
            delivery = WebhookDelivery(event_id=event.id, attempt=event.attempts, requested_at=now)
            session.add(delivery)
            session.flush()
            return {
                "event_id": event.id,
                "lease": lease,
                "body": event.raw_body.encode(),
                "attempt": event.attempts,
                "delivery_id": delivery.id,
            }

        return run_write(self.factory, operation)

    def _finish(self, claim: dict, status: int | None, error_kind: str | None) -> None:
        def operation(session: Session) -> None:
            now = utc_now()
            delivery = session.get(WebhookDelivery, claim["delivery_id"])
            delivery.completed_at = now
            delivery.response_status = status
            delivery.error_kind = error_kind
            success = status is not None and 200 <= status < 300
            retryable = status is None or status >= 500
            exhausted = claim["attempt"] > len(RETRY_DELAYS)
            delay = RETRY_DELAYS[min(claim["attempt"] - 1, len(RETRY_DELAYS) - 1)]
            session.execute(
                update(BankEvent)
                .where(
                    BankEvent.id == claim["event_id"],
                    BankEvent.lease_token == claim["lease"],
                )
                .values(
                    delivered=success,
                    stopped=not success and (not retryable or exhausted),
                    lease_token=None,
                    lease_until=None,
                    next_attempt_at=now + timedelta(seconds=delay),
                )
            )

        run_write(self.factory, operation)

    def deliver_due(self, limit: int = 20) -> int:
        """Send immediate attempts; persisted due times replace sleeping retry tasks."""
        delivered = 0
        for _ in range(limit):
            claim = self._claim()
            if claim is None:
                break
            timestamp = str(int(utc_now().timestamp()))
            signature = hmac.new(
                self.settings.webhook_secret.get_secret_value().encode(),
                timestamp.encode() + b"." + claim["body"],
                hashlib.sha256,
            ).hexdigest()
            status = None
            error_kind = None
            try:
                result = self.client.post(
                    str(self.settings.shop_webhook_url),
                    content=claim["body"],
                    headers={
                        "Content-Type": "application/json",
                        "X-Timestamp": timestamp,
                        "X-Signature": signature,
                    },
                    timeout=5,
                    follow_redirects=False,
                )
                status = result.status_code
            except httpx.HTTPError as exc:
                error_kind = type(exc).__name__
            self._finish(claim, status, error_kind)
            delivered += 1
        return delivered
````

mock_bank/schemas.py

````python
"""Strict merchant and customer request contracts."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class InvoiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_minor: Annotated[StrictInt, Field(gt=0, le=2**63 - 1)]
    currency: Literal["KZT"]
    merchant_reference: UUID
    description: str = Field(min_length=1, max_length=500)
    ttl_seconds: Annotated[StrictInt, Field(gt=0, le=86400)]


class PayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: UUID
````

mock_bank/seed.py

````python
"""Create three demo accounts once; never reset their balances."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from mock_bank.config import get_settings
from mock_bank.db import Base, create_db_engine, create_session_factory, run_write
from mock_bank.models import BankAccount

DEMO_ACCOUNTS = (
    ("rich", "Айдос", 50_000_000),
    ("poor", "Алия", 100_000),
    ("empty", "Дана", 0),
)


def seed_accounts(factory: sessionmaker[Session]) -> list[dict]:
    def operation(session: Session) -> list[dict]:
        for seed_key, holder, balance in DEMO_ACCOUNTS:
            if (
                session.scalar(select(BankAccount.id).where(BankAccount.seed_key == seed_key))
                is None
            ):
                session.add(
                    BankAccount(seed_key=seed_key, holder_name=holder, balance_minor=balance)
                )
        session.flush()
        return [
            {
                "public_id": str(account.id),
                "holder_name": account.holder_name,
                "balance_minor": account.balance_minor,
            }
            for account in session.scalars(select(BankAccount).order_by(BankAccount.holder_name))
        ]

    try:
        return run_write(factory, operation)
    except IntegrityError:
        return run_write(factory, operation)


def main() -> None:
    engine = create_db_engine(get_settings().bank_database_url)
    try:
        Base.metadata.create_all(engine)
        accounts = seed_accounts(create_session_factory(engine))
        print(f"Демо-счета готовы: {len(accounts)}. Существующие балансы сохранены.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
````

mock_bank/service.py

````python
"""Atomic invoice transitions and stable final events; never performs HTTP."""

import json
import secrets
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from mock_bank.config import Settings
from mock_bank.db import run_write, utc_now
from mock_bank.errors import BankError
from mock_bank.models import BankAccount, BankEvent, BankTransaction, Invoice, InvoiceStatus
from mock_bank.schemas import InvoiceCreate


class BankService:
    def __init__(self, factory: sessionmaker[Session], settings: Settings) -> None:
        self.factory = factory
        self.settings = settings

    def snapshot(self, session: Session, invoice: Invoice) -> dict:
        event_id = session.scalar(select(BankEvent.id).where(BankEvent.invoice_id == invoice.id))
        return {
            "invoice_id": str(invoice.id),
            "merchant_reference": str(invoice.merchant_reference),
            "merchant_name": invoice.merchant_name,
            "amount_minor": invoice.amount_minor,
            "amount_minor_text": str(invoice.amount_minor),
            "currency": invoice.currency,
            "description": invoice.description,
            "status": invoice.status.value,
            "pay_url": f"{str(self.settings.bank_public_url).rstrip('/')}/pay/{invoice.token}",
            "expires_at": invoice.expires_at.isoformat(),
            "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
            "failure_reason": invoice.failure_reason,
            "event_id": str(event_id) if event_id else None,
            "seconds_left": max(0, int((invoice.expires_at - utc_now()).total_seconds())),
        }

    @staticmethod
    def _find(session: Session, identifier: UUID | str) -> Invoice:
        condition = (
            Invoice.id == identifier
            if isinstance(identifier, UUID)
            else Invoice.token == identifier
        )
        invoice = session.scalar(select(Invoice).where(condition).with_for_update())
        if invoice is None:
            raise BankError(404, "INVOICE_NOT_FOUND", "Счёт не найден.")
        return invoice

    @staticmethod
    def _finalize(
        session: Session,
        invoice: Invoice,
        status: InvoiceStatus,
        reason: str | None = None,
        account_id: UUID | None = None,
    ) -> None:
        now = utc_now()
        values = {"status": status, "failure_reason": reason, "updated_at": now}
        if status is InvoiceStatus.PAID:
            values.update(paid_at=now, paid_by_account_id=account_id)
        changed = session.execute(
            update(Invoice)
            .where(Invoice.id == invoice.id, Invoice.status == InvoiceStatus.CREATED)
            .values(**values)
        ).rowcount
        if changed != 1:
            raise BankError(409, "INVOICE_FINAL", "Счёт уже завершён.")
        event_id = uuid4()
        event_type = f"invoice.{status.value.lower()}"
        body = {
            "event_id": str(event_id),
            "type": event_type,
            "created_at": now.isoformat(),
            "data": {
                "invoice_id": str(invoice.id),
                "merchant_reference": str(invoice.merchant_reference),
                "amount_minor": invoice.amount_minor,
                "currency": invoice.currency,
                "failure_reason": reason,
            },
        }
        session.add(
            BankEvent(
                id=event_id,
                invoice_id=invoice.id,
                event_type=event_type,
                raw_body=json.dumps(body, ensure_ascii=False, separators=(",", ":")),
                created_at=now,
                next_attempt_at=now,
            )
        )
        if status in (InvoiceStatus.PAID, InvoiceStatus.FAILED):
            session.add(
                BankTransaction(
                    invoice_id=invoice.id,
                    account_id=account_id,
                    amount_minor=invoice.amount_minor,
                    status=status.value,
                    failure_reason=reason,
                )
            )
        session.flush()

    def _expire(self, session: Session, invoice: Invoice) -> None:
        if invoice.status is InvoiceStatus.CREATED and invoice.expires_at <= utc_now():
            self._finalize(session, invoice, InvoiceStatus.EXPIRED, "expired")

    def create_invoice(self, payload: InvoiceCreate) -> dict:
        def operation(session: Session) -> dict:
            invoice = session.scalar(
                select(Invoice)
                .where(Invoice.merchant_reference == payload.merchant_reference)
                .with_for_update()
            )
            if invoice is not None:
                if any(
                    getattr(invoice, key) != value for key, value in payload.model_dump().items()
                ):
                    raise BankError(
                        409, "IDEMPOTENCY_CONFLICT", "Параметры повторного запроса отличаются."
                    )
                self._expire(session, invoice)
                return self.snapshot(session, invoice)
            invoice = Invoice(
                **payload.model_dump(),
                token=secrets.token_urlsafe(24),
                merchant_name=self.settings.merchant_name,
                expires_at=utc_now() + timedelta(seconds=payload.ttl_seconds),
            )
            session.add(invoice)
            session.flush()
            return self.snapshot(session, invoice)

        try:
            return run_write(self.factory, operation)
        except IntegrityError:
            # A concurrent merchant_reference insertion won; compare the committed invoice.
            return run_write(self.factory, operation)

    def get_invoice(self, identifier: UUID | str, *, accounts: bool = False) -> dict:
        def operation(session: Session) -> dict:
            invoice = self._find(session, identifier)
            self._expire(session, invoice)
            result = self.snapshot(session, invoice)
            if accounts:
                result["accounts"] = [
                    {
                        "public_id": str(account.id),
                        "holder_name": account.holder_name,
                        "balance_minor": account.balance_minor,
                        "balance_minor_text": str(account.balance_minor),
                    }
                    for account in session.scalars(
                        select(BankAccount).order_by(BankAccount.holder_name)
                    )
                ]
            return result

        return run_write(self.factory, operation)

    def pay(self, token: str, account_id: UUID) -> dict:
        def operation(session: Session) -> dict:
            invoice = self._find(session, token)
            self._expire(session, invoice)
            if invoice.status is not InvoiceStatus.CREATED:
                return self.snapshot(session, invoice)
            if session.get(BankAccount, account_id) is None:
                raise BankError(404, "ACCOUNT_NOT_FOUND", "Демо-счёт не найден.")
            debited = session.execute(
                update(BankAccount)
                .where(
                    BankAccount.id == account_id,
                    BankAccount.balance_minor >= invoice.amount_minor,
                )
                .values(balance_minor=BankAccount.balance_minor - invoice.amount_minor)
            ).rowcount
            self._finalize(
                session,
                invoice,
                InvoiceStatus.PAID if debited else InvoiceStatus.FAILED,
                None if debited else "insufficient_funds",
                account_id,
            )
            result = self.snapshot(session, invoice)
            result["_new_payment"] = True
            return result

        result = run_write(self.factory, operation)
        if result.pop("_new_payment", False):
            return result
        if result["status"] == "EXPIRED":
            raise BankError(410, "INVOICE_EXPIRED", "Срок действия счёта истёк.")
        raise BankError(409, "INVOICE_FINAL", "Счёт уже завершён.")

    def cancel(self, identifier: UUID | str) -> dict:
        def operation(session: Session) -> dict:
            invoice = self._find(session, identifier)
            self._expire(session, invoice)
            if invoice.status is InvoiceStatus.CREATED:
                self._finalize(session, invoice, InvoiceStatus.CANCELLED, "cancelled")
            return self.snapshot(session, invoice)

        result = run_write(self.factory, operation)
        if result["status"] == "PAID":
            raise BankError(409, "ALREADY_PAID", "Счёт уже оплачен.")
        return result

    def decline(self, token: str) -> dict:
        def operation(session: Session) -> dict:
            invoice = self._find(session, token)
            self._expire(session, invoice)
            if invoice.status is InvoiceStatus.CREATED:
                self._finalize(session, invoice, InvoiceStatus.FAILED, "bank_declined")
            return self.snapshot(session, invoice)

        return run_write(self.factory, operation)

    def sweep_expired(self) -> int:
        def operation(session: Session) -> int:
            invoices = session.scalars(
                select(Invoice)
                .where(
                    Invoice.status == InvoiceStatus.CREATED,
                    Invoice.expires_at <= utc_now(),
                )
                .order_by(Invoice.expires_at)
                .limit(100)
                .with_for_update()
            ).all()
            for invoice in invoices:
                self._finalize(session, invoice, InvoiceStatus.EXPIRED, "expired")
            return len(invoices)

        return run_write(self.factory, operation)
````

mock_bank/static/bank.css

````css
:root{color-scheme:light;--ink:#142c39;--muted:#526b78;--blue:#075b77;--line:#dbe6eb;--paper:#fff;--page:#edf4f7;--error:#9b2929}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--ink);font:16px/1.55 system-ui,-apple-system,sans-serif;min-height:100vh;padding:28px 16px}
.payment-card{max-width:480px;margin:auto;padding:30px;background:var(--paper);border:1px solid var(--line);border-radius:24px;box-shadow:0 16px 50px #163b4810}
.brand{display:flex;align-items:center;gap:12px;font-weight:750;font-size:18px}.brand small{display:block;font-weight:400;font-size:12px;color:var(--muted)}.brand-mark{display:grid;place-items:center;background:var(--blue);color:white;width:42px;height:42px;border-radius:13px;font-size:26px}
.notice{padding:14px;background:#fff6d9;border:1px solid #ead598;border-radius:12px;font-size:13px;margin:24px 0}.eyebrow{text-transform:uppercase;letter-spacing:.12em;font-size:11px;font-weight:700;color:var(--muted);margin-bottom:4px}h1{font-size:25px;margin:0}.amount{font-size:42px;font-weight:780;letter-spacing:-.035em;margin:18px 0 0;overflow-wrap:anywhere}.muted,#description,.footer{color:var(--muted);font-size:14px}.footer{border-top:1px solid var(--line);padding-top:20px;font-size:12px}
label{display:block;font-weight:650;margin:20px 0 7px}select,button{width:100%;font:inherit;border:1px solid var(--line);border-radius:12px;min-height:50px;padding:10px 13px}select{background:white;color:var(--ink)}button{cursor:pointer;background:var(--blue);color:white;font-weight:700;margin:6px 0}button:disabled{opacity:.5;cursor:not-allowed}.secondary{background:white;color:var(--ink)}.danger{background:#fff3f2;color:var(--error);border-color:#edd0cd}details{font-size:13px;margin:18px 0}summary{cursor:pointer;color:var(--muted)}#status{padding:10px 0;font-weight:600}#status.error{color:var(--error)}#status.success{color:#126c48}:focus-visible{outline:3px solid #dda600;outline-offset:3px}@media(max-width:380px){.payment-card{padding:20px}.amount{font-size:34px}}
````

mock_bank/static/bank.js

````javascript
"use strict";
const token = document.body.dataset.token;
const endpoint = `/api/pay/${encodeURIComponent(token)}`;
const account = document.getElementById("account");
const statusBox = document.getElementById("status");
const buttons = ["pay", "cancel", "decline"].map(id => document.getElementById(id));
const money = value => formatBankMoney(value);
let invoice = null;
let pending = false;
const labels = {CREATED:"Выберите счёт для оплаты", PAID:"Оплата прошла. Спасибо за покупку!", FAILED:"Оплата отклонена", EXPIRED:"Срок действия счёта истёк", CANCELLED:"Оплата отменена"};
const reasons = {insufficient_funds:"Недостаточно средств на демо-счёте", bank_declined:"Банк отклонил оплату"};
function render(data) {
  invoice = data;
  document.getElementById("amount").textContent = money(data.amount_minor_text);
  statusBox.textContent = reasons[data.failure_reason] || labels[data.status] || "Неизвестный статус";
  statusBox.className = data.status === "PAID" ? "success" : data.status === "CREATED" ? "" : "error";
  if (data.accounts) {
    const previous = account.value;
    account.replaceChildren(...data.accounts.map(item => {
      const option = document.createElement("option");
      option.value = item.public_id;
      option.textContent = `${item.holder_name} — ${money(item.balance_minor_text)}`;
      return option;
    }));
    if (Array.from(account.options).some(option => option.value === previous)) account.value = previous;
    if (!data.accounts.length) statusBox.textContent = "Демо-счета пока не созданы. Сообщите кассиру.";
  }
  updateButtons();
  tick();
}
function updateButtons() {
  const blocked = pending || !invoice || invoice.status !== "CREATED";
  buttons.forEach(button => { button.disabled = blocked; });
  buttons[0].disabled = blocked || !account.value;
  account.disabled = blocked;
}
function tick() {
  if (!invoice) return;
  const seconds = Math.max(0, Math.ceil((Date.parse(invoice.expires_at) - Date.now()) / 1000));
  document.getElementById("timer").textContent = invoice.status === "CREATED" ? `Осталось ${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,"0")}` : "Счёт завершён";
  if (seconds === 0 && invoice.status === "CREATED") buttons[0].disabled = true;
}
async function request(path, options={}) {
  const response = await fetch(path, {...options, headers:{"Content-Type":"application/json"}, cache:"no-store"});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message || "Не удалось выполнить запрос");
  return data;
}
async function load() {
  if (pending) return;
  try { render(await request(endpoint)); }
  catch (error) { statusBox.textContent = error.message || "Банк недоступен. Повторите позже."; statusBox.className = "error"; }
}
async function action(suffix, body) {
  if (pending) return;
  pending = true; updateButtons();
  try { render(await request(endpoint + suffix, {method:"POST", ...(body ? {body:JSON.stringify(body)} : {})})); }
  catch (error) { statusBox.textContent = error.message || "Проверьте соединение"; statusBox.className = "error"; }
  finally { pending = false; updateButtons(); }
}
document.getElementById("pay-form").addEventListener("submit", event => {event.preventDefault(); action("", {account_id:account.value});});
document.getElementById("cancel").addEventListener("click", () => action("/cancel"));
document.getElementById("decline").addEventListener("click", () => action("/decline"));
load(); setInterval(tick, 1000); setInterval(load, 2500);
````

mock_bank/static/money.js

````javascript
"use strict";

// Decimal-string API fields preserve every minor unit beyond Number.MAX_SAFE_INTEGER.
function formatBankMoney(value) {
  const minor = BigInt(value);
  const negative = minor < 0n;
  const absolute = negative ? -minor : minor;
  const whole = (absolute / 100n).toLocaleString("ru-RU");
  const fraction = String(absolute % 100n).padStart(2, "0");
  return `${negative ? "−" : ""}${whole},${fraction} ₸`;
}
````

mock_bank/templates/pay.html

````html
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Оплата · Учебный банк</title>
  <link rel="stylesheet" href="/static/bank.css">
  <script src="/static/money.js" defer></script>
  <script src="/static/bank.js" defer></script>
</head>
<body data-token="{{ token }}">
  <main class="payment-card">
    <div class="brand"><span class="brand-mark">B</span><span>Учебный банк<small>QR Mini-Market</small></span></div>
    <div class="notice">Учебный эмулятор банка. Не вводите реальные данные.</div>
    <p class="eyebrow">Оплата покупки</p>
    <h1>{{ invoice.merchant_name }}</h1>
    <p id="description">{{ invoice.description }}</p>
    <p class="amount" id="amount">Загрузка суммы…</p>
    <p id="timer" class="muted">Проверяем срок действия…</p>
    <div id="status" role="status" aria-live="polite">Загружаем счёт…</div>
    <form id="pay-form">
      <label for="account">Демо-счёт</label>
      <select id="account" required aria-describedby="account-hint" disabled><option value="">Загрузка…</option></select>
      <p class="muted" id="account-hint">Деньги учебные. Банковские реквизиты не нужны.</p>
      <button id="pay" type="submit" disabled>Оплатить</button>
    </form>
    <button id="cancel" class="secondary" type="button" disabled>Отмена</button>
    <details><summary>Демонстрация отказа</summary><p class="muted">Завершить счёт с причиной «Банк отклонил».</p><button id="decline" class="danger" type="button" disabled>Смоделировать отказ банка</button></details>
    <p class="footer">Сумма получена из базы банка. После оплаты вернитесь к экрану кассы.</p>
    <noscript><p>Для оплаты включите JavaScript в браузере.</p></noscript>
  </main>
</body>
</html>
````

pyproject.toml

````toml
[tool.ruff]
target-version = "py311"
line-length = 100
src = ["app", "mock_bank"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.ruff.lint.isort]
known-first-party = ["app", "mock_bank"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-ra --strict-config --strict-markers"
````

requirements-dev.txt

````text
-r requirements.txt
pytest==9.1.1
pytest-cov==7.1.0
ruff==0.17.0
````

requirements.txt

````text
# Versions exercised by the complete SQLite test suite. Python 3.11+.
fastapi==0.143.0
uvicorn==0.54.0
pydantic==2.14.0
pydantic-settings==2.15.0
SQLAlchemy==2.1.4
alembic==1.20.0
httpx==0.28.1
qrcode[pil]==8.2
Pillow==12.3.0
Jinja2==3.1.6
argon2-cffi==25.1.0
PyJWT==2.15.1
tzdata==2026.5
starlette==1.7.0
````

scripts/docker-entrypoint.sh

````sh
#!/bin/sh
set -eu

# Named volumes preserve data. Both seeds insert missing demo entries only.
case "${1:-shop}" in
    shop)
        python -m alembic upgrade head
        python -m app.seed
        exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
        ;;
    mock_bank)
        python -m mock_bank.seed
        exec python -m uvicorn mock_bank.main:app --host 0.0.0.0 --port 8001 --no-access-log
        ;;
    *)
        exec "$@"
        ;;
esac
````

tests/e2e/conftest.py

````python
"""Run the independent applications through their actual HTTP contracts."""

import os
import secrets
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.enums import UserRole
from app.db.session import create_db_engine
from app.main import create_app
from app.providers.mock_bank import MockBankProvider
from app.schemas.auth import CreateUserInput
from app.services.auth import create_user
from mock_bank.config import Settings as BankSettings
from mock_bank.main import create_app as create_bank_app
from mock_bank.seed import seed_accounts

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class WebhookBridge:
    """Capture signed HTTP bytes and optionally simulate a shop outage."""

    client: TestClient | None = None
    unavailable: bool = False
    requests: list[tuple[str, bytes, dict[str, str]]] = field(default_factory=list)

    def post(self, url: str, **kwargs: object) -> httpx.Response:
        content = kwargs["content"]
        headers = kwargs["headers"]
        assert isinstance(content, bytes)
        assert isinstance(headers, dict)
        self.requests.append((url, content, headers.copy()))
        if self.unavailable:
            return httpx.Response(503, request=httpx.Request("POST", url))
        assert self.client is not None
        return self.client.post(urlsplit(url).path, **kwargs)


@dataclass
class Market:
    shop: TestClient
    bank: TestClient
    bridge: WebhookBridge
    settings: Settings
    headers: dict[str, str]

    def api(self, method: str, path: str, **kwargs: object) -> dict:
        response = self.shop.request(method, "/api/v1" + path, headers=self.headers, **kwargs)
        assert 200 <= response.status_code < 300, response.text
        return response.json()


@pytest.fixture
def market(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Market]:
    """Provision separate databases, then connect only the injected HTTP clients."""
    fields = Settings.model_fields.keys() | BankSettings.model_fields.keys()
    for name in list(os.environ):
        if name.casefold() in fields:
            monkeypatch.delenv(name)
    merchant_key = secrets.token_urlsafe(32)
    webhook_secret = secrets.token_urlsafe(32)
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite:///{tmp_path / 'shop.db'}",
        bank_base_url="http://bank.test",
        bank_merchant_api_key=merchant_key,
        webhook_secret=webhook_secret,
        secret_key=secrets.token_urlsafe(32),
    )
    bank_settings = BankSettings(
        _env_file=None,
        bank_database_url=f"sqlite:///{tmp_path / 'bank.db'}",
        bank_public_url="http://bank.test",
        shop_webhook_url="http://shop.test/api/v1/webhooks/mock-bank",
        merchant_name="Тестовый мини-маркет",
        bank_merchant_api_key=merchant_key,
        webhook_secret=webhook_secret,
    )
    engine = create_db_engine(settings.database_url)
    try:
        with engine.begin() as connection:
            config = Config(str(ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        engine.dispose()
    bridge = WebhookBridge()
    bank_app = create_bank_app(bank_settings, webhook_client=bridge, run_worker=False)
    with TestClient(bank_app, base_url="http://bank.test") as bank:
        seed_accounts(bank_app.state.session_factory)
        provider = MockBankProvider(bank, settings)
        shop_app = create_app(settings, provider=provider, run_worker=False)
        with TestClient(shop_app, base_url="http://shop.test") as shop:
            bridge.client = shop
            password = secrets.token_urlsafe(24) + "Aa1!"
            create_user(
                shop_app.state.session_factory,
                CreateUserInput(username="e2e-admin", password=password, role=UserRole.ADMIN),
            )
            login = shop.post(
                "/api/v1/auth/login", json={"username": "e2e-admin", "password": password}
            )
            assert login.status_code == 200, login.text
            token = login.json()["access_token"]
            shop.cookies.clear()
            yield Market(shop, bank, bridge, settings, {"Authorization": f"Bearer {token}"})
````

tests/e2e/smoke_tcp.py

````python
"""Optional real-process smoke; run: python tests/e2e/smoke_tcp.py.

Run this file directly from the repository using the project's Python environment.
It creates temporary databases and generated credentials, then cleans up both servers.
"""

import os
import secrets
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[2]


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_for(client: httpx.Client, url: str, expected, timeout: int = 20) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = client.get(url)
            if response.status_code == 200 and expected(response.json()):
                return response.json()
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for {url}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="qr-market-smoke-") as directory:
        temporary = Path(directory)
        shop_port = free_port()
        bank_port = free_port()
        while bank_port == shop_port:
            bank_port = free_port()
        shop_url = f"http://127.0.0.1:{shop_port}"
        bank_url = f"http://127.0.0.1:{bank_port}"
        password = secrets.token_urlsafe(24)
        environment = {
            **os.environ,
            "APP_ENV": "test",
            "DATABASE_URL": f"sqlite:///{temporary / 'shop.db'}",
            "BANK_DATABASE_URL": f"sqlite:///{temporary / 'bank.db'}",
            "BANK_BASE_URL": bank_url,
            "BANK_PUBLIC_URL": bank_url,
            "SHOP_WEBHOOK_URL": shop_url + "/api/v1/webhooks/mock-bank",
            "BANK_MERCHANT_API_KEY": secrets.token_urlsafe(32),
            "WEBHOOK_SECRET": secrets.token_urlsafe(32),
            "SECRET_KEY": secrets.token_urlsafe(32),
            "PAYMENT_TTL_SECONDS": "5",
            "PAYMENT_EXPIRY_GRACE_SECONDS": "0",
            "SMOKE_ADMIN_PASSWORD": password,
        }

        def run(*arguments: str) -> None:
            result = subprocess.run(
                [sys.executable, *arguments],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, result.stderr

        run("-m", "alembic", "upgrade", "head")
        run("-m", "app.seed")
        run("-m", "app.seed")
        run("-m", "mock_bank.seed")
        run("-m", "mock_bank.seed")
        run(
            "-c",
            "import os; from app.core.config import get_settings; "
            "from app.db.session import create_db_engine, create_session_factory; "
            "from app.schemas.auth import CreateUserInput; "
            "from app.services.auth import create_user; "
            "engine=create_db_engine(get_settings().database_url); "
            "create_user(create_session_factory(engine), CreateUserInput("
            "username='smoke-admin', password=os.environ['SMOKE_ADMIN_PASSWORD'], role='ADMIN')); "
            "engine.dispose()",
        )
        print("Migration, idempotent seeds, and generated admin: OK")
        processes = []
        logs = []
        shutdown_logs = []
        try:
            for module, port in (("mock_bank.main:app", bank_port), ("app.main:app", shop_port)):
                log = (temporary / f"{port}.log").open("w+")
                logs.append(log)
                processes.append(
                    subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "uvicorn",
                            module,
                            "--host",
                            "127.0.0.1",
                            "--port",
                            str(port),
                            "--no-access-log",
                        ],
                        cwd=ROOT,
                        env=environment,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                    )
                )
            with httpx.Client(trust_env=False, timeout=15) as client:
                wait_for(client, shop_url + "/health", lambda data: data["status"] == "ok")
                wait_for(client, bank_url + "/health", lambda data: data["status"] == "ok")
                login = client.post(
                    shop_url + "/api/v1/auth/login",
                    json={
                        "username": "smoke-admin",
                        "password": password,
                    },
                )
                assert login.status_code == 200, login.text
                headers = {"Authorization": "Bearer " + login.json()["access_token"]}
                client.cookies.clear()

                def api(method: str, path: str, **kwargs) -> dict:
                    response = client.request(
                        method, shop_url + "/api/v1" + path, headers=headers, **kwargs
                    )
                    assert 200 <= response.status_code < 300, response.text
                    return response.json()

                products = api("GET", "/products", params={"limit": 100})["items"]
                assert len(products) >= 40
                pieces = sorted(
                    (p for p in products if p["unit"] == "PIECE" and p["stock_quantity"] > 0),
                    key=lambda p: p["price_minor"],
                    reverse=True,
                )[:3]
                weight = next(
                    p for p in products if p["unit"] == "KG" and p["stock_quantity"] > 3000
                )
                selected = pieces + [weight]

                def create_cart(terminal: str) -> dict:
                    order = api("POST", "/orders", json={"terminal_code": terminal})
                    for product in selected:
                        order = api(
                            "POST",
                            f"/orders/{order['public_id']}/items",
                            json={
                                "barcode": product["barcode"],
                                "quantity": 750 if product["unit"] == "KG" else 1,
                            },
                        )
                    return order

                order = create_cart("smoke-paid")
                payment = api("POST", f"/orders/{order['public_id']}/checkout")
                qr = client.get(shop_url + f"/api/v1/payments/{payment['public_id']}/qr.png")
                assert qr.status_code == 200 and qr.content.startswith(b"\x89PNG\r\n\x1a\n")
                token = urlsplit(payment["pay_url"]).path.rsplit("/", 1)[-1]
                invoice = client.get(bank_url + f"/api/pay/{token}").json()
                rich = max(invoice["accounts"], key=lambda account: account["balance_minor"])
                assert client.get(payment["pay_url"]).status_code == 200
                paid = client.post(
                    bank_url + f"/api/pay/{token}", json={"account_id": rich["public_id"]}
                )
                assert paid.status_code == 200, paid.text
                wait_for(
                    client,
                    shop_url + f"/api/v1/payments/{payment['public_id']}",
                    lambda data: data["status"] == "SUCCEEDED",
                )
                assert api("GET", f"/orders/{order['public_id']}")["status"] == "PAID"
                assert api("GET", f"/orders/{order['public_id']}/receipt")["payment_method"] == "QR"
                assert (
                    client.get(shop_url + "/api/v1/public/terminals/smoke-paid/display").json()[
                        "state"
                    ]
                    == "paid"
                )
                with sqlite3.connect(temporary / "shop.db") as connection:
                    for product in selected:
                        row = connection.execute(
                            "SELECT stock_quantity, reserved_quantity FROM products "
                            "WHERE public_id=?",
                            (product["public_id"].replace("-", ""),),
                        ).fetchone()
                        quantity = 750 if product["unit"] == "KG" else 1
                        assert row == (product["stock_quantity"] - quantity, 0)
                print("Real TCP: 3 piece products + weighted item + QR + signed webhook + PAID: OK")

                poor_order = create_cart("smoke-poor")
                poor_payment = api("POST", f"/orders/{poor_order['public_id']}/checkout")
                token = urlsplit(poor_payment["pay_url"]).path.rsplit("/", 1)[-1]
                invoice = client.get(bank_url + f"/api/pay/{token}").json()
                poor = min(
                    (a for a in invoice["accounts"] if a["balance_minor"] > 0),
                    key=lambda account: account["balance_minor"],
                )
                assert (
                    client.post(
                        bank_url + f"/api/pay/{token}", json={"account_id": poor["public_id"]}
                    ).status_code
                    == 200
                )
                wait_for(
                    client,
                    shop_url + f"/api/v1/payments/{poor_payment['public_id']}",
                    lambda data: data["status"] == "FAILED",
                )
                assert api("GET", f"/orders/{poor_order['public_id']}")["status"] == "OPEN"
                print("Real TCP: insufficient funds + webhook + order reopened: OK")

                retry = api("POST", f"/orders/{poor_order['public_id']}/checkout")
                wait_for(
                    client,
                    shop_url + f"/api/v1/payments/{retry['public_id']}",
                    lambda data: data["status"] == "EXPIRED",
                    timeout=15,
                )
                assert api("GET", f"/orders/{poor_order['public_id']}")["status"] == "OPEN"
                with sqlite3.connect(temporary / "shop.db") as connection:
                    assert (
                        connection.execute(
                            "SELECT sum(reserved_quantity) FROM products"
                        ).fetchone()[0]
                        == 0
                    )
                for path in ("/login", "/price-check", "/display/main"):
                    assert client.get(shop_url + path).status_code == 200
                print("Real TCP: background expiry + reserve released + public pages: OK")
        except Exception:
            for log in logs:
                log.flush()
                log.seek(0)
                print(log.read(), file=sys.stderr)
            raise
        finally:
            for process in processes:
                process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            for log in logs:
                log.flush()
                log.seek(0)
                shutdown_logs.append(log.read())
                log.close()
        assert all(process.returncode in (0, -signal.SIGTERM) for process in processes)
        assert all("Application shutdown complete." in output for output in shutdown_logs)
        print("Both Uvicorn processes stopped cleanly; temporary databases removed: OK")


if __name__ == "__main__":
    main()
````

tests/e2e/test_market.py

````python
"""Exercise checkout, bank settlement, notifications, recovery, and stock contention."""

import hashlib
import hmac
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import BytesIO
from threading import Barrier
from urllib.parse import urlsplit
from uuid import UUID

import pytest
from PIL import Image
from sqlalchemy import func, select

from app.core.barcodes import generate_internal_ean13
from app.core.enums import StockReason
from app.models import PaymentEvent, Product, StockMovement
from mock_bank.models import Invoice


def build_cart(market, terminal: str = "demo") -> tuple[dict, list[dict]]:
    category = market.api("POST", "/categories", json={"name": "Еда", "slug": "food"})
    products = []
    for number, (name, unit, price, stock) in enumerate(
        [
            ("Хлеб", "PIECE", 40000, 10),
            ("Молоко", "PIECE", 70000, 10),
            ("Шоколад", "PIECE", 100000, 10),
            ("Яблоки", "KG", 80000, 5000),
        ],
        start=1,
    ):
        products.append(
            market.api(
                "POST",
                "/products",
                json={
                    "name": name,
                    "barcode": generate_internal_ean13(number),
                    "category_id": category["public_id"],
                    "unit": unit,
                    "price_minor": price,
                    "stock_quantity": stock,
                },
            )
        )
    order = market.api("POST", "/orders", json={"terminal_code": terminal})
    for product in products:
        order = market.api(
            "POST",
            f"/orders/{order['public_id']}/items",
            json={"barcode": product["barcode"], "quantity": 750 if product["unit"] == "KG" else 1},
        )
    assert order["total_minor"] == 270000
    assert len(order["items"]) == 4
    return order, products


def checkout(market, order: dict) -> tuple[dict, str, dict]:
    payment = market.api("POST", f"/orders/{order['public_id']}/checkout")
    assert payment["status"] == "PENDING"
    assert payment["amount_minor"] == order["total_minor"]
    token = urlsplit(payment["pay_url"]).path.rsplit("/", 1)[-1]
    response = market.bank.get(f"/api/pay/{token}")
    assert response.status_code == 200, response.text
    return payment, token, response.json()


def stock_snapshot(market, products: list[dict]) -> dict[str, tuple[int, int]]:
    with market.shop.app.state.session_factory() as session:
        rows = session.scalars(
            select(Product).where(Product.public_id.in_([UUID(p["public_id"]) for p in products]))
        )
        return {str(row.public_id): (row.stock_quantity, row.reserved_quantity) for row in rows}


def assert_no_private_fields(value: object) -> None:
    if isinstance(value, dict):
        assert not value.keys() & {
            "id",
            "provider_invoice_id",
            "password_hash",
            "cashier_id",
            "reserved_quantity",
            "min_stock_quantity",
            "raw_body",
        }
        for child in value.values():
            assert_no_private_fields(child)
    elif isinstance(value, list):
        for child in value:
            assert_no_private_fields(child)


def test_three_piece_products_and_weight_are_paid_once_over_http(market) -> None:
    order, products = build_cart(market)
    payment, token, invoice = checkout(market, order)
    display = market.shop.get("/api/v1/public/terminals/demo/display")
    assert display.status_code == 200
    assert display.json()["state"] == "awaiting_payment"
    assert display.json()["seconds_left"] > 0
    assert_no_private_fields(display.json())

    qr = market.shop.get(f"/api/v1/payments/{payment['public_id']}/qr.png")
    assert qr.status_code == 200
    assert qr.headers["content-type"] == "image/png"
    assert qr.headers["cache-control"] == "no-store"
    assert qr.content.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(BytesIO(qr.content)) as image:
        assert image.width >= 300 and image.height >= 300

    rich = max(invoice["accounts"], key=lambda account: account["balance_minor"])
    paid = market.bank.post(f"/api/pay/{token}", json={"account_id": rich["public_id"]})
    assert paid.status_code == 200, paid.text
    result = market.api("GET", f"/orders/{order['public_id']}")
    assert result["status"] == "PAID"
    assert result["payment"]["status"] == "SUCCEEDED"
    assert market.shop.get("/api/v1/public/terminals/demo/display").json()["state"] == "paid"
    assert (
        market.shop.get(f"/api/v1/payments/{payment['public_id']}").json()["status"] == "SUCCEEDED"
    )
    assert market.shop.get(f"/api/v1/payments/{payment['public_id']}/qr.png").status_code in (
        409,
        410,
    )

    stock = stock_snapshot(market, products)
    for product in products:
        quantity = 750 if product["unit"] == "KG" else 1
        assert stock[product["public_id"]] == (product["stock_quantity"] - quantity, 0)
    receipt = market.api("GET", f"/orders/{order['public_id']}/receipt")
    assert receipt["total_minor"] == 270000
    assert receipt["payment_method"] == "QR"
    assert "не фискальный" in receipt["disclaimer"]

    assert len(market.bridge.requests) == 1
    _, raw, headers = market.bridge.requests[0]
    lowered_headers = {name.lower(): value for name, value in headers.items()}
    timestamp = lowered_headers["x-timestamp"]
    signature = hmac.new(
        market.settings.webhook_secret.get_secret_value().encode(),
        timestamp.encode() + b"." + raw,
        hashlib.sha256,
    ).hexdigest()
    assert hmac.compare_digest(lowered_headers["x-signature"], signature)
    duplicate = market.shop.post("/api/v1/webhooks/mock-bank", content=raw, headers=headers)
    assert duplicate.status_code == 200
    repeated_pay = market.bank.post(f"/api/pay/{token}", json={"account_id": rich["public_id"]})
    assert repeated_pay.status_code == 409
    assert stock_snapshot(market, products) == stock
    with market.shop.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PaymentEvent)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(StockMovement)
                .where(StockMovement.reason == StockReason.SALE)
            )
            == 4
        )
    updated = market.bank.get(f"/api/pay/{token}").json()
    rich_after = next(a for a in updated["accounts"] if a["public_id"] == rich["public_id"])
    assert rich_after["balance_minor"] == rich["balance_minor"] - payment["amount_minor"]


def test_poor_account_releases_reserve_and_order_can_be_retried(market) -> None:
    order, products = build_cart(market)
    payment, token, invoice = checkout(market, order)
    poor = min(
        (account for account in invoice["accounts"] if account["balance_minor"] > 0),
        key=lambda account: account["balance_minor"],
    )
    response = market.bank.post(f"/api/pay/{token}", json={"account_id": poor["public_id"]})
    assert response.status_code == 200, response.text
    assert market.shop.get(f"/api/v1/payments/{payment['public_id']}").json()["status"] == "FAILED"
    assert market.api("GET", f"/orders/{order['public_id']}")["status"] == "OPEN"
    display = market.shop.get("/api/v1/public/terminals/demo/display").json()
    assert display["state"] == "payment_failed"
    for product in products:
        assert stock_snapshot(market, products)[product["public_id"]] == (
            product["stock_quantity"],
            0,
        )
    updated = market.bank.get(f"/api/pay/{token}").json()
    poor_after = next(a for a in updated["accounts"] if a["public_id"] == poor["public_id"])
    assert poor_after["balance_minor"] == poor["balance_minor"]
    retry = market.api("POST", f"/orders/{order['public_id']}/checkout")
    assert retry["status"] == "PENDING"
    assert retry["public_id"] != payment["public_id"]


def test_lost_webhook_is_recovered_by_refresh_without_double_sale(market) -> None:
    order, products = build_cart(market)
    payment, token, invoice = checkout(market, order)
    market.bridge.unavailable = True
    rich = max(invoice["accounts"], key=lambda account: account["balance_minor"])
    response = market.bank.post(f"/api/pay/{token}", json={"account_id": rich["public_id"]})
    assert response.status_code == 200
    assert market.api("GET", f"/orders/{order['public_id']}")["status"] == "PENDING_PAYMENT"
    result = market.api("POST", f"/payments/{payment['public_id']}/refresh")
    assert result["status"] == "SUCCEEDED"
    stock = stock_snapshot(market, products)
    market.bridge.unavailable = False
    _, raw, headers = market.bridge.requests[0]
    assert (
        market.shop.post("/api/v1/webhooks/mock-bank", content=raw, headers=headers).status_code
        == 200
    )
    assert market.api("POST", f"/payments/{payment['public_id']}/refresh")["status"] == "SUCCEEDED"
    assert stock_snapshot(market, products) == stock
    with market.shop.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PaymentEvent)) == 1


def test_expiration_queries_bank_and_releases_reserve(market) -> None:
    order, products = build_cart(market)
    payment, token, invoice = checkout(market, order)
    with market.bank.app.state.session_factory.begin() as session:
        bank_invoice = session.scalar(select(Invoice).where(Invoice.token == token))
        bank_invoice.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    result = market.api("POST", f"/payments/{payment['public_id']}/refresh")
    assert result["status"] == "EXPIRED"
    assert market.api("GET", f"/orders/{order['public_id']}")["status"] == "OPEN"
    for product in products:
        assert stock_snapshot(market, products)[product["public_id"]] == (
            product["stock_quantity"],
            0,
        )
    rich = max(invoice["accounts"], key=lambda account: account["balance_minor"])
    assert (
        market.bank.post(f"/api/pay/{token}", json={"account_id": rich["public_id"]}).status_code
        == 410
    )


@pytest.mark.parametrize("cancel_order", [False, True])
def test_cashier_cancellation_reaches_bank_and_releases_reserve(market, cancel_order: bool) -> None:
    order, products = build_cart(market)
    payment, token, _ = checkout(market, order)
    path = (
        f"/orders/{order['public_id']}/cancel"
        if cancel_order
        else f"/payments/{payment['public_id']}/cancel"
    )
    market.api("POST", path)
    expected = "CANCELLED" if cancel_order else "OPEN"
    assert market.api("GET", f"/orders/{order['public_id']}")["status"] == expected
    assert market.bank.get(f"/api/pay/{token}").json()["status"] == "CANCELLED"
    assert (
        market.shop.get(f"/api/v1/payments/{payment['public_id']}").json()["status"] == "CANCELLED"
    )
    for product in products:
        assert stock_snapshot(market, products)[product["public_id"]] == (
            product["stock_quantity"],
            0,
        )


def test_last_product_can_be_reserved_by_only_one_terminal(market) -> None:
    category = market.api("POST", "/categories", json={"name": "Еда", "slug": "food"})
    product = market.api(
        "POST",
        "/products",
        json={
            "name": "Последний хлеб",
            "barcode": generate_internal_ean13(1),
            "category_id": category["public_id"],
            "unit": "PIECE",
            "price_minor": 30000,
            "stock_quantity": 1,
        },
    )
    orders = []
    for terminal in ("left", "right"):
        order = market.api("POST", "/orders", json={"terminal_code": terminal})
        market.api(
            "POST",
            f"/orders/{order['public_id']}/items",
            json={"product_id": product["public_id"], "quantity": 1},
        )
        orders.append(order)
    barrier = Barrier(2)

    def reserve(order: dict):
        barrier.wait(timeout=10)
        return market.shop.post(
            f"/api/v1/orders/{order['public_id']}/checkout", headers=market.headers
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(reserve, orders))
    assert sorted(response.status_code for response in responses) == [200, 409]
    failed = next(response for response in responses if response.status_code == 409)
    assert failed.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    assert stock_snapshot(market, [product])[product["public_id"]] == (1, 1)
    with market.bank.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Invoice)) == 1


def test_public_price_check_and_payment_status_do_not_grant_catalog_access(market) -> None:
    order, _ = build_cart(market)
    payment, _, _ = checkout(market, order)
    products = market.shop.get("/api/v1/public/products", params={"q": "МОЛОКО"})
    assert products.status_code == 200
    assert products.json()["total"] == 1
    product = products.json()["items"][0]
    assert "stock_quantity" not in product
    assert_no_private_fields(product)
    assert_no_private_fields(market.shop.get(f"/api/v1/payments/{payment['public_id']}").json())
    for method, path in [
        ("GET", "/products"),
        ("GET", f"/orders/{order['public_id']}/receipt"),
        ("POST", f"/payments/{payment['public_id']}/cancel"),
    ]:
        assert market.shop.request(method, "/api/v1" + path).status_code == 401
````

tests/e2e/test_service_boundaries.py

````python
"""Protect the independent deployments from accidental direct cross-service imports."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(("service", "forbidden"), [("app", "mock_bank"), ("mock_bank", "app")])
def test_services_do_not_import_each_other(service: str, forbidden: str) -> None:
    for path in (ROOT / service).rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                modules = [node.module or ""]
            else:
                continue
            assert all(module.split(".")[0] != forbidden for module in modules), (
                f"{path.relative_to(ROOT)}:{node.lineno} imports {forbidden} directly"
            )
````

tests/integration/test_api.py

````python
"""Exercise application lifecycle, error contracts, and session cleanup."""

import os
import secrets
from pathlib import Path
from typing import Annotated
from unittest.mock import Mock

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Column, Integer, MetaData, Table, func, inspect, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

import app.main as main_module
from app.core.config import Settings
from app.core.errors import AppError
from app.dependencies import get_session
from app.main import create_app
from app.schemas.common import HealthResponse

CANARY = "test-only-sensitive-value"


class InputPayload(BaseModel):
    quantity: int = Field(gt=0)
    password: str

    @field_validator("password")
    @classmethod
    def reject_canary(cls, value: str) -> str:
        if value == CANARY:
            raise ValueError(value)
        return value


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    for name in list(os.environ):
        if name.casefold() in Settings.model_fields:
            monkeypatch.delenv(name)
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        bank_merchant_api_key=secrets.token_urlsafe(32),
        webhook_secret=secrets.token_urlsafe(32),
        secret_key=secrets.token_urlsafe(32),
    )


@pytest.fixture
def application(settings: Settings) -> FastAPI:
    app = create_app(settings, run_worker=False)

    @app.post("/_test/input", include_in_schema=False)
    def validate_input(payload: InputPayload) -> dict[str, int]:
        return {"quantity": payload.quantity}

    @app.get("/_test/domain", include_in_schema=False)
    def domain_error() -> None:
        raise AppError(409, "ORDER_NOT_OPEN", "Чек нельзя изменить.", {"status": "PAID"})

    @app.get("/_test/http/{status_code}", include_in_schema=False)
    def http_error(status_code: int) -> None:
        raise HTTPException(status_code, detail=CANARY, headers={"WWW-Authenticate": "Bearer"})

    @app.get("/_test/failure", include_in_schema=False)
    def unexpected_error() -> None:
        raise RuntimeError(CANARY)

    @app.get("/_test/response", response_model=HealthResponse, include_in_schema=False)
    def invalid_response() -> dict[str, str]:
        return {"status": CANARY, "database": "ok"}

    return app


def test_factory_is_lazy(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    engine_factory = Mock(side_effect=AssertionError("Engine must not be created yet"))
    monkeypatch.setattr(main_module, "create_db_engine", engine_factory)
    app = create_app(settings, run_worker=False)
    assert not hasattr(app.state, "engine")
    engine_factory.assert_not_called()


def test_health_lifecycle_and_no_schema_creation(settings: Settings) -> None:
    app = create_app(settings, run_worker=False)
    with TestClient(app) as client:
        engine = app.state.engine
        dispose = Mock(wraps=engine.dispose)
        engine.dispose = dispose
        response = client.get("/health", headers={"Origin": "http://untrusted.example"})
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "ok"}
        assert response.headers["cache-control"] == "no-store"
        assert "access-control-allow-origin" not in response.headers
        assert inspect(engine).get_table_names() == []
    dispose.assert_called_once_with()
    assert not hasattr(app.state, "session_factory")
    assert not hasattr(app.state, "engine")


def test_dispose_after_startup_failure(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = main_module.create_db_engine(settings.database_url)
    dispose = Mock(wraps=engine.dispose)
    monkeypatch.setattr(engine, "dispose", dispose)
    monkeypatch.setattr(main_module, "create_db_engine", lambda _url: engine)
    monkeypatch.setattr(
        main_module, "ping_database", Mock(side_effect=RuntimeError("Startup failed"))
    )
    app = create_app(settings, run_worker=False)
    with pytest.raises(RuntimeError, match="Startup failed"), TestClient(app):
        pytest.fail("Startup must fail")
    dispose.assert_called_once_with()
    assert not hasattr(app.state, "engine")


@pytest.mark.parametrize("path", ["/missing", "/docs", "/redoc"])
def test_not_found_is_json(application: FastAPI, path: str) -> None:
    with TestClient(application) as client:
        response = client.get(path)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_method_error_preserves_allow_header(application: FastAPI) -> None:
    with TestClient(application) as client:
        response = client.post("/health")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert "GET" in response.headers["allow"]


def test_domain_error_contract(application: FastAPI) -> None:
    with TestClient(application) as client:
        response = client.get("/_test/domain")
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "ORDER_NOT_OPEN",
            "message": "Чек нельзя изменить.",
            "details": {"status": "PAID"},
        }
    }


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 409, 410, 422, 429, 500, 502, 503])
def test_http_errors_do_not_echo_detail(
    application: FastAPI, status_code: int, caplog: pytest.LogCaptureFixture
) -> None:
    with TestClient(application) as client:
        response = client.get(f"/_test/http/{status_code}")
    assert response.status_code == status_code
    assert set(response.json()["error"]) == {"code", "message", "details"}
    assert response.headers["www-authenticate"] == "Bearer"
    assert CANARY not in response.text
    assert CANARY not in caplog.text


@pytest.mark.parametrize("quantity", [None, 0, -1, "invalid"])
def test_validation_does_not_echo_sensitive_values(application: FastAPI, quantity: object) -> None:
    with TestClient(application) as client:
        response = client.post("/_test/input", json={"quantity": quantity, "password": CANARY})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["fields"]
    assert CANARY not in response.text
    for field in error["details"]["fields"]:
        assert set(field) == {"location", "type"}


@pytest.mark.parametrize("path", ["/_test/failure", "/_test/response"])
def test_internal_error_is_safe_without_reraising(
    application: FastAPI, path: str, caplog: pytest.LogCaptureFixture
) -> None:
    with TestClient(application) as client:
        response = client.get(path)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "Traceback" not in response.text
    assert CANARY not in response.text
    assert CANARY not in caplog.text
    assert "Request failure" in caplog.text


def test_database_failure_is_503(
    application: FastAPI, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with TestClient(application) as client:
        failure = OperationalError("SELECT 1", {}, RuntimeError(CANARY))
        monkeypatch.setattr(application.state.engine, "connect", Mock(side_effect=failure))
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert CANARY not in response.text
    assert CANARY not in caplog.text


@pytest.mark.parametrize("fail", [False, True])
def test_request_session_closes_without_commit(application: FastAPI, fail: bool) -> None:
    metadata = MetaData()
    probe = Table("request_probe", metadata, Column("id", Integer, primary_key=True))

    @application.post("/_test/session", include_in_schema=False)
    def write_without_commit(session: Annotated[Session, Depends(get_session)]) -> dict[str, bool]:
        session.execute(probe.insert().values(id=1))
        if fail:
            raise RuntimeError(CANARY)
        return {"ok": True}

    with TestClient(application) as client:
        engine = application.state.engine
        metadata.create_all(engine)
        assert client.post("/_test/session").status_code == (500 if fail else 200)
        assert engine.pool.checkedout() == 0
        with engine.connect() as connection:
            assert connection.scalar(select(func.count()).select_from(probe)) == 0


def test_openapi_exposes_only_real_routes_and_error_schema(settings: Settings) -> None:
    with TestClient(create_app(settings, run_worker=False)) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert {
        "/health",
        "/api/v1/products",
        "/api/v1/orders",
        "/api/v1/auth/login",
        "/api/v1/webhooks/mock-bank",
    } <= set(schema["paths"])
    assert not any(path.startswith("/_test") for path in schema["paths"])
    response_schema = schema["paths"]["/health"]["get"]["responses"]["503"]
    assert response_schema["content"]["application/json"]["schema"]["$ref"].endswith(
        "ErrorResponse"
    )
````

tests/integration/test_auth_reports.py

````python
"""Exercise real password/JWT validation, browser CSRF, roles, and report snapshots."""

import secrets
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated

import jwt
import pytest
from alembic import command
from alembic.config import Config
from argon2 import PasswordHasher
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event, inspect, select

import app.create_user as create_user_cli
from app.core.barcodes import generate_internal_ean13
from app.core.config import Settings
from app.core.enums import OrderStatus, PaymentStatus, ProductUnit, UserRole
from app.core.errors import AppError, install_error_handlers
from app.db.session import create_db_engine, create_session_factory
from app.models import Category, Order, OrderItem, Payment, Product, User
from app.routers.auth import router as auth_router
from app.routers.reports import router as reports_router
from app.schemas.auth import CreateUserInput, LoginInput
from app.services.auth import (
    PASSWORD_HASHER,
    TOKEN_AUDIENCE,
    TOKEN_ISSUER,
    authenticate,
    create_user,
    require_admin,
    require_cashier,
)
from app.services.reports import low_stock_report, payments_review_report, sales_report

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def credentials() -> tuple[str, str]:
    password = secrets.token_urlsafe(24)
    return password, PASSWORD_HASHER.hash(password)


@pytest.fixture
def auth_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, credentials: tuple[str, str]):
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite:///{tmp_path / 'auth.db'}",
        secret_key=secrets.token_urlsafe(32),
        webhook_secret=secrets.token_urlsafe(32),
        bank_merchant_api_key=secrets.token_urlsafe(32),
    )
    engine = create_db_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        with engine.begin() as connection:
            config = Config(str(ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        with factory.begin() as session:
            admin = User(username="admin", password_hash=credentials[1], role=UserRole.ADMIN)
            cashier = User(username="cashier", password_hash=credentials[1], role=UserRole.CASHIER)
            session.add_all([admin, cashier])
            session.flush()
        app = FastAPI()
        app.state.settings = settings
        app.state.session_factory = factory
        install_error_handlers(app)
        app.include_router(auth_router)
        app.include_router(reports_router)

        @app.get("/_test/cashier")
        def cashier_only(user: Annotated[User, Depends(require_cashier)]) -> dict:
            return {"username": user.username, "detached": inspect(user).detached}

        @app.post("/_test/admin")
        def admin_only(user: Annotated[User, Depends(require_admin)]) -> dict:
            return {"username": user.username}

        yield app, settings, factory, admin, cashier
    finally:
        engine.dispose()


@pytest.fixture
def client(auth_context) -> Iterator[TestClient]:
    with TestClient(auth_context[0]) as value:
        yield value


def login(client: TestClient, credentials: tuple[str, str], username: str = "admin") -> dict:
    response = client.post(
        "/api/v1/auth/login", json={"username": username, "password": credentials[0]}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_login_cookie_flags_me_and_logout(client: TestClient, credentials: tuple[str, str]) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": credentials[0]}
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    cookies = response.headers.get_list("set-cookie")
    assert "HttpOnly" in cookies[0] and "SameSite=lax" in cookies[0]
    assert "HttpOnly" not in cookies[1]
    me = client.get("/api/v1/auth/me")
    assert set(me.json()) == {"public_id", "username", "role"}
    assert me.json()["role"] == "ADMIN"
    assert credentials[0] not in response.text and credentials[1] not in response.text
    assert client.post("/api/v1/auth/logout").status_code == 403
    assert (
        client.post(
            "/api/v1/auth/logout", headers={"X-CSRF-Token": response.json()["csrf_token"]}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/auth/me").status_code == 401


def test_cookie_mutations_require_signed_double_submit_token(
    client: TestClient, credentials
) -> None:
    result = login(client, credentials)
    assert client.post("/_test/admin").status_code == 403
    assert client.post("/_test/admin", headers={"X-CSRF-Token": "forged"}).status_code == 403
    headers = {"X-CSRF-Token": result["csrf_token"]}
    assert client.post("/_test/admin", headers=headers).status_code == 200
    assert (
        client.post(
            "/_test/admin", headers={**headers, "Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    client.cookies.set("csrf_token", "forged")
    assert client.post("/_test/admin", headers=headers).status_code == 403


def test_bearer_does_not_need_cookie_csrf_and_users_are_detached(
    client: TestClient, credentials
) -> None:
    token = login(client, credentials)["access_token"]
    client.cookies.clear()
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/_test/admin", headers=headers).status_code == 200
    assert client.get("/_test/cashier", headers=headers).json()["detached"] is True


@pytest.mark.parametrize(
    "origin",
    ["https://evil.example", "null", "http://testserver:81", "http://testserver@evil.example"],
)
def test_cross_origin_login_rejected(client: TestClient, credentials, origin: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": credentials[0]},
        headers={"Origin": origin},
    )
    assert response.status_code == 403


def test_same_origin_login_allowed(client: TestClient, credentials) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": credentials[0]},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 200


@pytest.mark.parametrize("username", ["admin", "unknown"])
def test_wrong_credentials_are_generic(client: TestClient, username: str, caplog) -> None:
    canary = "not-a-valid-password-'; DROP TABLE users;--"
    response = client.post("/api/v1/auth/login", json={"username": username, "password": canary})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert canary not in response.text and canary not in caplog.text


def test_invalid_username_form_login_and_password_overflow_rejected(client: TestClient) -> None:
    for body in (
        {"username": "admin' OR 1=1--", "password": "x"},
        {"username": "admin", "password": "x" * 129},
        {"username": "admin", "password": "x", "role": "ADMIN"},
    ):
        assert client.post("/api/v1/auth/login", json=body).status_code == 422
    assert (
        client.post("/api/v1/auth/login", data={"username": "admin", "password": "x"}).status_code
        == 422
    )


def test_live_role_and_active_checks(client: TestClient, auth_context, credentials) -> None:
    _, _, factory, admin, _ = auth_context
    result = login(client, credentials)
    headers = {"Authorization": f"Bearer {result['access_token']}"}
    with factory.begin() as session:
        session.get(User, admin.id).role = UserRole.CASHIER
    assert client.post("/_test/admin", headers=headers).status_code == 403
    assert client.get("/_test/cashier", headers=headers).status_code == 200
    with factory.begin() as session:
        session.get(User, admin.id).is_active = False
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": credentials[0]}
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/reports/sales",
        "/api/v1/reports/low-stock",
        "/api/v1/reports/payments-needing-review",
    ],
)
def test_reports_require_admin(client: TestClient, credentials, path: str) -> None:
    assert client.get(path).status_code == 401
    login(client, credentials, "cashier")
    assert client.get(path).status_code == 403


@pytest.mark.parametrize(
    "kind",
    [
        "expired",
        "future",
        "issuer",
        "audience",
        "missing_exp",
        "missing_csrf",
        "bad_sub",
        "none",
        "wrong_signature",
    ],
)
def test_invalid_jwt_rejected(client: TestClient, auth_context, kind: str) -> None:
    _, settings, _, admin, _ = auth_context
    now = datetime.now(UTC)
    claims = {
        "sub": str(admin.public_id),
        "iss": TOKEN_ISSUER,
        "aud": TOKEN_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=1),
        "jti": "test",
        "csrf": "x" * 32,
    }
    if kind == "expired":
        claims["exp"] = now - timedelta(seconds=1)
    elif kind == "future":
        claims["nbf"] = now + timedelta(hours=1)
    elif kind in ("issuer", "audience"):
        claims["iss" if kind == "issuer" else "aud"] = "wrong"
    elif kind.startswith("missing_"):
        claims.pop(kind.removeprefix("missing_"))
    elif kind == "bad_sub":
        claims["sub"] = "123"
    key = (
        secrets.token_urlsafe(32)
        if kind == "wrong_signature"
        else settings.secret_key.get_secret_value()
    )
    token = jwt.encode(
        claims, None if kind == "none" else key, algorithm="none" if kind == "none" else "HS256"
    )
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_bad_authorization_does_not_fall_back_to_cookie(client: TestClient, credentials) -> None:
    login(client, credentials)
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Basic abc"}).status_code == 401


def test_production_cookie_uses_secure_flag(client: TestClient, auth_context, credentials) -> None:
    app, settings, *_ = auth_context
    app.state.settings = settings.model_copy(update={"app_env": "production"})
    response = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": credentials[0]}
    )
    assert response.status_code == 200
    assert all("Secure" in item for item in response.headers.get_list("set-cookie"))


def test_corrupt_password_hash_returns_generic_401(
    client: TestClient, auth_context, credentials
) -> None:
    _, _, factory, admin, _ = auth_context
    with factory.begin() as session:
        session.get(User, admin.id).password_hash = "corrupted-hash"
    response = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": credentials[0]}
    )
    assert response.status_code == 401
    assert "corrupted-hash" not in response.text


def test_create_user_cli_getpass_and_safe_output(
    auth_context, credentials, monkeypatch, capsys
) -> None:
    _, settings, factory, _, _ = auth_context
    monkeypatch.setattr("sys.argv", ["create_user", "--username", "cli-user", "--role", "CASHIER"])
    monkeypatch.setattr(create_user_cli.getpass, "getpass", lambda _prompt: credentials[0])
    monkeypatch.setattr(create_user_cli, "get_settings", lambda: settings)
    assert create_user_cli.main() == 0
    with factory() as session:
        user = session.scalar(select(User).where(User.username == "cli-user"))
        assert user is not None and PASSWORD_HASHER.verify(user.password_hash, credentials[0])
    output = capsys.readouterr()
    assert "cli-user" in output.out
    assert credentials[0] not in output.out + output.err


def test_create_user_cli_password_mismatch_never_opens_database(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.argv", ["create_user", "--username", "cli-user", "--role", "ADMIN"])
    passwords = iter(["one-test-password", "another-test-password"])
    monkeypatch.setattr(create_user_cli.getpass, "getpass", lambda _prompt: next(passwords))
    monkeypatch.setattr(create_user_cli, "get_settings", lambda: pytest.fail("No database needed"))
    assert create_user_cli.main() == 1
    assert "Пароли не совпадают" in capsys.readouterr().err


def test_create_user_and_duplicate_are_safe(auth_context, credentials) -> None:
    _, settings, factory, _, _ = auth_context
    data = CreateUserInput(username="new-user", password=credentials[0], role="CASHIER")
    user = create_user(factory, data)
    assert user.password_hash.startswith("$argon2id$")
    assert user.password_hash != credentials[0]
    response = authenticate(
        factory, LoginInput(username="new-user", password=credentials[0]), settings
    )
    assert response.user.public_id == user.public_id
    with pytest.raises(AppError) as error:
        create_user(factory, data)
    assert error.value.status_code == 409
    with pytest.raises(ValidationError):
        CreateUserInput(username="new", password="short", role="ADMIN")


def test_successful_login_rehashes_old_argon_parameters(auth_context, credentials) -> None:
    _, settings, factory, admin, _ = auth_context
    old_hash = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(credentials[0])
    with factory.begin() as session:
        session.get(User, admin.id).password_hash = old_hash
    authenticate(factory, LoginInput(username="admin", password=credentials[0]), settings)
    with factory() as session:
        new_hash = session.get(User, admin.id).password_hash
    assert new_hash != old_hash
    assert not PASSWORD_HASHER.check_needs_rehash(new_hash)


@pytest.fixture
def report_data(auth_context):
    _, _, factory, admin, _ = auth_context
    with factory.begin() as session:
        category = Category(name="Еда", slug="report-food")
        session.add(category)
        session.flush()
        product = Product(
            name="Новое имя",
            barcode=generate_internal_ean13(500),
            category_id=category.id,
            unit=ProductUnit.PIECE,
            price_minor=999,
            stock_quantity=10,
            reserved_quantity=8,
            min_stock_quantity=2,
        )
        inactive = Product(
            name="Неактивный",
            barcode=generate_internal_ean13(501),
            category_id=category.id,
            unit=ProductUnit.PIECE,
            price_minor=999,
            stock_quantity=0,
            min_stock_quantity=10,
            is_active=False,
        )
        session.add_all([product, inactive])
        session.flush()
        # 2026-10-10 starts at 19:00 UTC on the previous day in Asia/Almaty.
        paid_times = [
            datetime(2026, 10, 9, 18, 59, 59, tzinfo=UTC),
            datetime(2026, 10, 9, 19, tzinfo=UTC),
            datetime(2026, 10, 10, 18, 59, 59, tzinfo=UTC),
            datetime(2026, 10, 10, 19, tzinfo=UTC),
        ]
        orders = []
        for index, paid_at in enumerate(paid_times):
            order = Order(
                number=f"report-{index}",
                terminal_code=f"report-{index}",
                status=OrderStatus.PAID,
                total_minor=250,
                paid_at=paid_at,
                cashier_id=admin.id,
            )
            session.add(order)
            session.flush()
            session.add(
                OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    product_name="Старое имя",
                    barcode=product.barcode,
                    unit=ProductUnit.PIECE,
                    unit_price_minor=125,
                    quantity=2,
                    line_total_minor=250,
                )
            )
            orders.append(order)
        excluded = Order(
            number="report-open",
            terminal_code="report-open",
            total_minor=999,
            status=OrderStatus.OPEN,
        )
        session.add(excluded)
        session.flush()
        payment = Payment(
            order_id=orders[0].id,
            status=PaymentStatus.FAILED,
            amount_minor=250,
            needs_review=True,
            review_reason="late_success",
            provider_invoice_id="internal-provider-id",
        )
        session.add(payment)
        session.flush()
        return product.public_id, category.public_id, payment.public_id


def test_report_filters_local_days_and_uses_historical_snapshots(auth_context, report_data) -> None:
    _, settings, factory, _, _ = auth_context
    report = sales_report(factory, settings, date(2026, 10, 10), date(2026, 10, 10))
    assert report["orders_count"] == 2
    assert report["revenue_minor"] == 500
    assert report["revenue_minor_text"] == "500"
    assert report["days"] == [
        {"date": "2026-10-10", "orders_count": 2, "revenue_minor": 500, "revenue_minor_text": "500"}
    ]
    assert report["products"][0]["name"] == "Старое имя"
    assert report["products"][0]["quantity"] == 4
    assert report["categories"][0]["public_id"] == str(report_data[1])
    assert report["categories"][0]["revenue_minor"] == 500


def test_sales_totals_do_not_overflow_sqlite_or_python(auth_context, report_data) -> None:
    _, settings, factory, _, _ = auth_context
    with factory.begin() as session:
        for item in session.scalars(select(OrderItem)):
            item.line_total_minor = 2**63 - 1
    report = sales_report(factory, settings, date(2026, 10, 10), date(2026, 10, 10))
    assert report["revenue_minor"] == (2**63 - 1) * 2
    assert report["revenue_minor_text"] == str((2**63 - 1) * 2)


def test_sales_counts_multi_item_orders_in_one_statement_snapshot(
    auth_context, report_data
) -> None:
    """Header counts and line sums must share a statement snapshot on PostgreSQL."""
    _, settings, factory, _, _ = auth_context
    with factory.begin() as session:
        order = session.scalar(select(Order).where(Order.number == "report-1"))
        product = session.scalar(select(Product).where(Product.is_active.is_(False)))
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name="Вторая позиция",
                barcode=product.barcode,
                unit=ProductUnit.PIECE,
                unit_price_minor=150,
                quantity=1,
                line_total_minor=150,
            )
        )
    engine = factory.kw["bind"]
    statements = []

    def record(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        report = sales_report(factory, settings, date(2026, 10, 10), date(2026, 10, 10))
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert len(statements) == 1
    assert report["orders_count"] == 2
    assert report["revenue_minor"] == 650
    assert len(report["products"]) == 2
    assert report["days"][0]["orders_count"] == 2
    assert report["days"][0]["revenue_minor"] == 650


@pytest.mark.parametrize(
    "dates",
    [
        (date(2026, 10, 11), date(2026, 10, 10)),
        (date(2025, 1, 1), date(2026, 10, 10)),
        (date.min, date.min),
        (date.max, date.max),
    ],
)
def test_invalid_report_period_rejected(auth_context, dates) -> None:
    with pytest.raises(AppError) as error:
        sales_report(auth_context[2], auth_context[1], *dates)
    assert error.value.status_code == 422


def test_low_stock_counts_available_and_excludes_inactive(auth_context, report_data) -> None:
    report = low_stock_report(auth_context[2], limit=1)
    assert report["total"] == 1
    item = report["items"][0]
    assert item["public_id"] == str(report_data[0])
    assert item["available_quantity"] == 2
    assert item["stock_quantity"] == 10
    assert item["category_id"] == str(report_data[1])
    assert "id" not in item
    assert low_stock_report(auth_context[2], limit=1, offset=1)["items"] == []


def test_payment_review_pagination_excludes_internal_fields(auth_context, report_data) -> None:
    report = payments_review_report(auth_context[2])
    assert report["total"] == 1
    item = report["items"][0]
    assert item["public_id"] == str(report_data[2])
    assert item["review_reason"] == "late_success"
    assert "provider_invoice_id" not in item
    assert "id" not in item
    assert payments_review_report(auth_context[2], limit=1, offset=1)["items"] == []


@pytest.mark.parametrize("parameters", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_report_pagination_validation(auth_context, parameters) -> None:
    with pytest.raises(AppError):
        low_stock_report(auth_context[2], **parameters)


def test_report_api_serializes_and_validates_parameters(
    client: TestClient, credentials, report_data
) -> None:
    login(client, credentials)
    response = client.get(
        "/api/v1/reports/sales", params={"date_from": "2026-10-10", "date_to": "2026-10-10"}
    )
    assert response.status_code == 200
    assert response.json()["revenue_minor"] == 500
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/reports/sales?date_from=bad").status_code == 422
    assert client.get("/api/v1/reports/low-stock?limit=101").status_code == 422
    assert client.get("/api/v1/reports/payments-needing-review").status_code == 200
````

tests/integration/test_catalog_orders_services.py

````python
"""Exercise catalog and order behavior against the migrated database."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.barcodes import generate_internal_ean13
from app.core.enums import OrderStatus, PaymentStatus, ProductUnit, StockReason
from app.core.errors import AppError, install_error_handlers
from app.core.money import MAX_SAFE_MINOR
from app.db.session import create_db_engine, create_session_factory
from app.models import Order, Payment, Product, StockMovement
from app.models.catalog import MAX_QUANTITY
from app.routers.catalog import router as catalog_router
from app.routers.orders import router as orders_router
from app.schemas.catalog import (
    CategoryCreate,
    CategoryPatch,
    ProductCreate,
    ProductPatch,
    StockAdjustment,
)
from app.schemas.orders import ItemAdd, ItemPatch, OrderCreate
from app.seed import CATEGORIES, PRODUCTS, seed_catalog
from app.services.auth import require_admin, require_cashier
from app.services.catalog import CatalogService
from app.services.orders import OrderService


@pytest.fixture
def factory(tmp_path: Path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'services.db'}")
    with engine.begin() as connection:
        config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    yield create_session_factory(engine)
    engine.dispose()


@pytest.fixture
def market(factory):
    catalog = CatalogService(factory)
    orders = OrderService(factory)
    root = catalog.create_category(CategoryCreate(name="Еда", slug="food"))
    leaf = catalog.create_category(
        CategoryCreate(name="Молочное", slug="milk", parent_id=root["public_id"])
    )
    piece = catalog.create_product(
        ProductCreate(
            name="МОЛОКО",
            barcode=generate_internal_ean13(1),
            category_id=leaf["public_id"],
            unit=ProductUnit.PIECE,
            price_minor=125000,
            stock_quantity=20,
        )
    )
    weight = catalog.create_product(
        ProductCreate(
            name="Яблоки 100%",
            barcode=generate_internal_ean13(2),
            category_id=root["public_id"],
            unit=ProductUnit.KG,
            price_minor=1,
            stock_quantity=10000,
        )
    )
    return SimpleNamespace(
        factory=factory,
        catalog=catalog,
        orders=orders,
        root=root,
        leaf=leaf,
        piece=piece,
        weight=weight,
    )


def assert_error(code, operation):
    with pytest.raises(AppError) as caught:
        operation()
    assert caught.value.code == code


def test_catalog_search_descendants_pagination_and_safe_public_projection(market):
    service = market.catalog
    assert service.list_products(q="мОлОкО")["total"] == 1
    assert service.list_products(q="%")["items"][0]["name"] == "Яблоки 100%"
    assert service.list_products(q="_")["total"] == 0
    assert service.list_products(category_id=market.root["public_id"])["total"] == 1
    assert (
        service.list_products(category_id=market.root["public_id"], include_subcategories=True)[
            "total"
        ]
        == 2
    )
    page = service.list_products(limit=1, offset=1, public=True)
    assert page["total"] == 2 and len(page["items"]) == 1
    assert (
        not {
            "id",
            "stock_quantity",
            "reserved_quantity",
            "min_stock_quantity",
            "available_quantity",
        }
        & page["items"][0].keys()
    )
    assert service.list_categories(limit=1, offset=1)["total"] == 2
    assert service.get_by_barcode(market.piece["barcode"])["public_id"] == market.piece["public_id"]
    assert service.get_product(market.piece["public_id"])["unit"] is ProductUnit.PIECE
    assert service.list_products(barcode=market.piece["barcode"])["total"] == 1


def test_catalog_soft_delete_parent_activity_and_uniqueness(market):
    service = market.catalog
    assert_error(
        "CATALOG_CONFLICT",
        lambda: service.create_category(CategoryCreate(name="Дубль", slug="food")),
    )
    assert_error(
        "CATALOG_CONFLICT",
        lambda: service.create_product(
            ProductCreate(
                name="Дубль",
                barcode=market.piece["barcode"],
                category_id=market.root["public_id"],
                unit=ProductUnit.PIECE,
                price_minor=1,
            )
        ),
    )
    result = service.delete_product(market.piece["public_id"])
    assert result["is_active"] is False
    assert service.list_products()["total"] == 1
    assert service.list_products(is_active=False)["total"] == 1
    assert service.list_products(is_active=None)["total"] == 2
    assert_error("PRODUCT_NOT_FOUND", lambda: service.get_by_barcode(market.piece["barcode"]))
    service.update_product(
        market.piece["public_id"], ProductPatch(is_active=True, name="  КеФиР  ")
    )
    assert service.list_products(q="кефир")["total"] == 1
    service.delete_category(market.root["public_id"])
    assert service.list_categories(public=True)["total"] == 0
    assert service.list_products(public=True)["total"] == 0
    with market.factory() as session:
        assert session.scalar(select(func.count()).select_from(Product)) == 2


def test_category_cycle_and_reparenting(market):
    service = market.catalog
    assert_error(
        "CATEGORY_CYCLE",
        lambda: service.update_category(
            market.root["public_id"], CategoryPatch(parent_id=market.leaf["public_id"])
        ),
    )
    assert_error(
        "CATEGORY_CYCLE",
        lambda: service.update_category(
            market.leaf["public_id"], CategoryPatch(parent_id=market.leaf["public_id"])
        ),
    )
    result = service.update_category(
        market.leaf["public_id"], CategoryPatch(parent_id=None, slug="dairy")
    )
    assert result["parent_id"] is None and result["slug"] == "dairy"
    assert_error(
        "CATEGORY_NOT_FOUND", lambda: service.update_category(uuid4(), CategoryPatch(name="Нет"))
    )
    assert_error("CATEGORY_NOT_FOUND", lambda: service.list_products(category_id=uuid4()))


def test_opposite_category_moves_cannot_form_a_cycle(market):
    service = market.catalog
    first = service.create_category(CategoryCreate(name="Первый", slug="first"))["public_id"]
    second = service.create_category(CategoryCreate(name="Второй", slug="second"))["public_id"]

    def move(pair):
        try:
            service.update_category(pair[0], CategoryPatch(parent_id=pair[1]))
            return "ok"
        except AppError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(move, [(first, second), (second, first)]))
    assert sorted(outcomes) == ["CATEGORY_CYCLE", "ok"]


def test_stock_adjustments_are_atomic_guard_reserved_and_journaled(market):
    service = market.catalog
    with market.factory.begin() as session:
        product = session.scalar(
            select(Product).where(Product.public_id == market.piece["public_id"])
        )
        product.reserved_quantity = 18
    assert_error(
        "STOCK_CONFLICT",
        lambda: service.adjust_stock(market.piece["public_id"], StockAdjustment(delta=-3)),
    )
    changed = service.adjust_stock(market.piece["public_id"], StockAdjustment(delta=-2))
    assert changed["stock_quantity"] == 18 and changed["available_quantity"] == 0
    changed = service.adjust_stock(
        market.piece["public_id"], StockAdjustment(delta=5, reason=StockReason.RESTOCK)
    )
    assert changed["available_quantity"] == 5
    with market.factory() as session:
        deltas = list(session.scalars(select(StockMovement.delta).order_by(StockMovement.id)))
        assert deltas == [20, 10000, -2, 5]
    assert_error(
        "UNIT_IMMUTABLE",
        lambda: service.update_product(
            market.piece["public_id"], ProductPatch(unit=ProductUnit.KG)
        ),
    )
    assert_error(
        "PRODUCT_NOT_FOUND", lambda: service.adjust_stock(uuid4(), StockAdjustment(delta=1))
    )
    assert_error("PRODUCT_NOT_FOUND", lambda: service.get_by_barcode(generate_internal_ean13(99)))
    assert_error("PRODUCT_NOT_FOUND", lambda: service.get_product(uuid4()))


@pytest.mark.parametrize("stock,delta", [(MAX_QUANTITY, 1), (0, -1)])
def test_stock_adjustment_rejects_range_overflow_without_ledger_entry(market, stock, delta):
    with market.factory.begin() as session:
        product = session.scalar(
            select(Product).where(Product.public_id == market.piece["public_id"])
        )
        product.stock_quantity = stock
        movement_count = session.scalar(select(func.count()).select_from(StockMovement))
    assert_error(
        "STOCK_CONFLICT",
        lambda: market.catalog.adjust_stock(
            market.piece["public_id"], StockAdjustment(delta=delta)
        ),
    )
    assert market.catalog.get_product(market.piece["public_id"])["stock_quantity"] == stock
    with market.factory() as session:
        assert session.scalar(select(func.count()).select_from(StockMovement)) == movement_count


def test_repeated_scan_snapshots_weight_rounding_edit_and_delete(market):
    order = market.orders.create_order(OrderCreate())
    order_id = order["public_id"]
    order = market.orders.add_item(order_id, ItemAdd(barcode=market.piece["barcode"], quantity=1))
    snapshot = order["items"][0]
    market.catalog.update_product(
        market.piece["public_id"], ProductPatch(price_minor=990000, name="Новое имя")
    )
    order = market.orders.add_item(
        order_id, ItemAdd(product_id=market.piece["public_id"], quantity=2)
    )
    assert len(order["items"]) == 1 and order["items"][0]["quantity"] == 3
    assert order["items"][0]["unit_price_minor"] == 125000
    assert order["items"][0]["product_name"] == "МОЛОКО"
    order = market.orders.add_item(
        order_id, ItemAdd(product_id=market.weight["public_id"], quantity=500)
    )
    order = market.orders.add_item(
        order_id, ItemAdd(product_id=market.weight["public_id"], quantity=500)
    )
    assert order["total_minor"] == 375001
    assert order["total_minor"] == sum(item["line_total_minor"] for item in order["items"])
    order = market.orders.update_item(order_id, snapshot["public_id"], ItemPatch(quantity=2))
    assert order["total_minor"] == 250001
    order = market.orders.remove_item(order_id, snapshot["public_id"])
    assert len(order["items"]) == 1 and order["total_minor"] == 1
    assert market.orders.get_order(order_id)["items"] == order["items"]
    assert market.orders.list_orders(terminal_code="main", status=OrderStatus.OPEN)["total"] == 1
    assert_error("ACTIVE_ORDER_EXISTS", lambda: market.orders.create_order(OrderCreate()))
    assert_error("RECEIPT_NOT_READY", lambda: market.orders.receipt(order_id))
    assert_error("ITEM_NOT_FOUND", lambda: market.orders.remove_item(order_id, uuid4()))


@pytest.mark.parametrize(
    "status", [OrderStatus.PENDING_PAYMENT, OrderStatus.PAID, OrderStatus.CANCELLED]
)
def test_non_open_orders_cannot_be_mutated(market, status):
    order = market.orders.create_order(OrderCreate())
    order_id = order["public_id"]
    order = market.orders.add_item(order_id, ItemAdd(product_id=market.piece["public_id"]))
    with market.factory.begin() as session:
        session.scalar(select(Order).where(Order.public_id == order_id)).status = status
    assert_error(
        "ORDER_NOT_OPEN",
        lambda: market.orders.add_item(order_id, ItemAdd(product_id=market.piece["public_id"])),
    )
    assert_error(
        "ORDER_NOT_OPEN",
        lambda: market.orders.update_item(
            order_id, order["items"][0]["public_id"], ItemPatch(quantity=2)
        ),
    )
    assert_error(
        "ORDER_NOT_OPEN",
        lambda: market.orders.remove_item(order_id, order["items"][0]["public_id"]),
    )


def test_orders_reject_unknown_inactive_unavailable_and_unsafe_totals(market):
    order = market.orders.create_order(OrderCreate())
    order_id = order["public_id"]
    assert_error("ORDER_NOT_FOUND", lambda: market.orders.get_order(uuid4()))
    assert_error(
        "ORDER_NOT_FOUND",
        lambda: market.orders.add_item(uuid4(), ItemAdd(product_id=market.piece["public_id"])),
    )
    assert_error(
        "PRODUCT_NOT_FOUND", lambda: market.orders.add_item(order_id, ItemAdd(product_id=uuid4()))
    )
    assert_error(
        "INSUFFICIENT_STOCK",
        lambda: market.orders.add_item(
            order_id, ItemAdd(product_id=market.piece["public_id"], quantity=21)
        ),
    )
    market.catalog.delete_product(market.piece["public_id"])
    assert_error(
        "PRODUCT_INACTIVE",
        lambda: market.orders.add_item(order_id, ItemAdd(product_id=market.piece["public_id"])),
    )
    market.catalog.update_product(
        market.piece["public_id"], ProductPatch(is_active=True, price_minor=MAX_SAFE_MINOR)
    )
    assert_error(
        "AMOUNT_TOO_LARGE",
        lambda: market.orders.add_item(
            order_id, ItemAdd(product_id=market.piece["public_id"], quantity=2)
        ),
    )
    market.orders.add_item(order_id, ItemAdd(product_id=market.piece["public_id"]))
    assert_error(
        "AMOUNT_TOO_LARGE",
        lambda: market.orders.add_item(
            order_id, ItemAdd(product_id=market.weight["public_id"], quantity=1000)
        ),
    )
    assert market.orders.get_order(order_id)["total_minor"] == MAX_SAFE_MINOR
    assert len(market.orders.get_order(order_id)["items"]) == 1


def test_concurrent_repeated_scans_do_not_lose_quantities(market):
    order_id = market.orders.create_order(OrderCreate())["public_id"]

    def scan(_index):
        market.orders.add_item(order_id, ItemAdd(product_id=market.piece["public_id"]))

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(scan, range(8)))
    order = market.orders.get_order(order_id)
    assert order["items"][0]["quantity"] == 8
    assert order["total_minor"] == 1000000


def test_display_timer_final_failure_and_paid_visibility_are_server_owned(market):
    assert market.orders.display("main")["state"] == "idle"
    order_id = market.orders.create_order(OrderCreate())["public_id"]
    assert market.orders.display("main")["state"] == "cart"
    with market.factory.begin() as session:
        order = session.scalar(select(Order).where(Order.public_id == order_id))
        order.status = OrderStatus.PENDING_PAYMENT
        payment = Payment(
            order_id=order.id,
            amount_minor=100,
            currency="KZT",
            expires_at=datetime.now(UTC) + timedelta(seconds=60),
            pay_url="http://bank/pay/demo",
        )
        session.add(payment)
    display = market.orders.display("main")
    assert display["state"] == "awaiting_payment" and 0 < display["seconds_left"] <= 60
    with market.factory.begin() as session:
        order = session.scalar(select(Order).where(Order.public_id == order_id))
        order.status = OrderStatus.OPEN
        payment = session.scalar(select(Payment).where(Payment.order_id == order.id))
        payment.status = PaymentStatus.EXPIRED
    assert market.orders.display("main")["failure_reason"] == "expired"
    with market.factory.begin() as session:
        order = session.scalar(select(Order).where(Order.public_id == order_id))
        order.status = OrderStatus.PAID
        order.paid_at = datetime.now(UTC)
    assert market.orders.display("main")["state"] == "paid"
    assert market.orders.receipt(order_id)["payment_method"] == "QR"
    with market.factory.begin() as session:
        order = session.scalar(select(Order).where(Order.public_id == order_id))
        order.paid_at = datetime.now(UTC) - timedelta(seconds=16)
    assert market.orders.display("main")["state"] == "idle"
    assert market.orders.display("main")["state"] == "idle"


def test_seed_is_idempotent_and_does_not_reset_existing_stock(factory):
    assert seed_catalog(factory) == {
        "categories_created": len(CATEGORIES),
        "products_created": len(PRODUCTS),
    }
    with factory.begin() as session:
        product = session.scalar(
            select(Product).where(Product.barcode == generate_internal_ean13(1))
        )
        product.stock_quantity = 1
    assert seed_catalog(factory) == {"categories_created": 0, "products_created": 0}
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Product)) >= 40
        assert (
            session.scalar(
                select(func.count()).select_from(Product).where(Product.is_active.is_(False))
            )
            == 1
        )
        assert (
            session.scalar(
                select(Product.stock_quantity).where(Product.barcode == generate_internal_ean13(1))
            )
            == 1
        )
        assert session.scalar(select(func.count()).select_from(StockMovement)) == len(PRODUCTS) - 1


@pytest.mark.parametrize(
    "schema,data",
    [
        (CategoryCreate, {"name": " ", "slug": "blank"}),
        (CategoryCreate, {"name": "Еда", "slug": "../bad"}),
        (CategoryPatch, {}),
        (CategoryPatch, {"name": None}),
        (ProductPatch, {"price_minor": True}),
        (ProductPatch, {"price_minor": MAX_SAFE_MINOR + 1}),
        (ProductPatch, {"category_id": None}),
        (ProductPatch, {"barcode": "2000000000016"}),
        (ProductPatch, {}),
        (StockAdjustment, {"delta": 0}),
        (StockAdjustment, {"delta": 1, "reason": "SALE"}),
        (StockAdjustment, {"delta": -1, "reason": "RESTOCK"}),
        (ItemAdd, {}),
        (ItemAdd, {"barcode": "2000000000015", "product_id": str(uuid4())}),
        (ItemPatch, {"quantity": True}),
        (ItemPatch, {"quantity": 0}),
        (OrderCreate, {"terminal_code": "../bad"}),
    ],
)
def test_commands_reject_ambiguous_or_invalid_inputs(schema, data):
    with pytest.raises(ValidationError):
        schema.model_validate(data)


def test_public_routes_validate_ids_and_hide_stock_fields(market):
    app = FastAPI()
    app.state.session_factory = market.factory
    app.state.settings = SimpleNamespace(currency="KZT")
    app.include_router(catalog_router)
    app.include_router(orders_router)
    install_error_handlers(app)
    app.dependency_overrides[require_cashier] = lambda: SimpleNamespace(id=None)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=None)
    with TestClient(app) as client:
        products = client.get("/api/v1/public/products")
        assert products.status_code == 200
        assert "stock_quantity" not in products.json()["items"][0]
        assert client.get("/api/v1/public/categories").json()["total"] == 2
        assert client.get("/api/v1/products/1").status_code == 422
        assert client.get("/api/v1/products/by-barcode/2000000000016").status_code == 422
        assert client.get("/api/v1/public/products?barcode=2000000000016").status_code == 422
        assert client.get("/api/v1/products", params={"limit": 101}).status_code == 422
        created = client.post("/api/v1/orders", json={"terminal_code": "main"})
        assert created.status_code == 201
        order_id = created.json()["public_id"]
        added = client.post(
            f"/api/v1/orders/{order_id}/items",
            json={"barcode": market.piece["barcode"], "quantity": 2},
        )
        assert added.status_code == 200 and added.json()["total_minor"] == 250000
        display = client.get("/api/v1/public/terminals/main/display")
        assert display.status_code == 200
        assert display.headers["cache-control"] == "no-store"
        assert display.json()["state"] == "cart"
````

tests/integration/test_catalog_schema.py

````python
"""Verify migrated tables, persisted models, and database-level constraints."""

from collections.abc import Iterator
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import URL, CheckConstraint, inspect, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from app.core.barcodes import generate_internal_ean13
from app.core.enums import ProductUnit
from app.db.base import Base
from app.db.session import create_db_engine, create_session_factory
from app.models import Category, Product
from app.models.catalog import MAX_PRICE_MINOR, MAX_QUANTITY

ROOT = Path(__file__).resolve().parents[2]


def migration_config(connection: Connection) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_db_engine(URL.create("sqlite", database=str(tmp_path / "catalog.db")))
    try:
        with engine.begin() as connection:
            command.upgrade(migration_config(connection), "head")
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def populated(engine: Engine) -> tuple[int, int, int]:
    with create_session_factory(engine).begin() as session:
        root = Category(name="Еда", slug="food")
        session.add(root)
        session.flush()
        child = Category(name="Молочные продукты", slug="dairy", parent_id=root.id)
        session.add(child)
        session.flush()
        product = Product(
            name="  МОЛОКО  ",
            barcode=generate_internal_ean13(1),
            category_id=child.id,
            unit=ProductUnit.PIECE,
            price_minor=125000,
            stock_quantity=10,
            reserved_quantity=2,
            min_stock_quantity=1,
            created_at=datetime(2020, 1, 1, tzinfo=UTC),
            updated_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
        session.add(product)
        session.flush()
        return root.id, child.id, product.id


def test_migration_matches_models_and_has_required_indexes(engine: Engine) -> None:
    schema = inspect(engine)
    assert set(schema.get_table_names()) == {"alembic_version", *Base.metadata.tables}
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "compare_server_default": True}
        )
        assert compare_metadata(context, Base.metadata) == []
    for table in Base.metadata.sorted_tables:
        expected = {item.name for item in table.constraints if isinstance(item, CheckConstraint)}
        assert {item["name"] for item in schema.get_check_constraints(table.name)} == expected
        assert all(
            fk["options"]["ondelete"] == "RESTRICT" for fk in schema.get_foreign_keys(table.name)
        )
    indexes = {item["name"]: item for item in schema.get_indexes("products")}
    assert indexes["ix_products_barcode"]["unique"]
    assert indexes["ix_products_category_id"]["column_names"] == ["category_id"]
    assert indexes["ix_products_name_normalized"]["column_names"] == ["name_normalized"]


def test_uuid_normalization_timestamps_and_soft_deactivation(
    engine: Engine, populated: tuple[int, int, int]
) -> None:
    sessions = create_session_factory(engine)
    with sessions.begin() as session:
        product = session.get(Product, populated[2])
        assert isinstance(product.public_id, UUID)
        assert product.public_id.version == 4
        assert isinstance(session.get(Category, populated[0]).public_id, UUID)
        assert product.name == "МОЛОКО"
        assert product.name_normalized == "молоко"
        assert product.unit is ProductUnit.PIECE
        assert product.created_at.tzinfo is UTC
        product.name = "КеФиР"
        product.is_active = False
    with sessions() as session:
        product = session.get(Product, populated[2])
        assert product.name_normalized == "кефир"
        assert product.updated_at > product.created_at
        assert product.updated_at.tzinfo is UTC
        assert product.is_active is False
        assert session.scalar(select(Product).where(Product.name_normalized == "КЕФИР".casefold()))


def test_casefold_expansion_and_numeric_boundaries(
    engine: Engine, populated: tuple[int, int, int]
) -> None:
    with create_session_factory(engine).begin() as session:
        product = session.get(Product, populated[2])
        product.name = "ß" * 200
        product.price_minor = MAX_PRICE_MINOR
        product.stock_quantity = MAX_QUANTITY
        product.reserved_quantity = MAX_QUANTITY
        product.min_stock_quantity = MAX_QUANTITY
    with create_session_factory(engine)() as session:
        product = session.get(Product, populated[2])
        assert product.name_normalized == "ss" * 200
        assert product.price_minor == MAX_PRICE_MINOR
        assert type(product.price_minor) is int
        assert product.stock_quantity == MAX_QUANTITY


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("price_minor", -1),
        ("price_minor", "1.5"),
        ("price_minor", "invalid"),
        ("stock_quantity", -1),
        ("stock_quantity", "2.5"),
        ("stock_quantity", MAX_QUANTITY + 1),
        ("stock_quantity", 1),
        ("reserved_quantity", -1),
        ("reserved_quantity", 11),
        ("reserved_quantity", "1.5"),
        ("min_stock_quantity", -1),
        ("min_stock_quantity", "1.5"),
        ("min_stock_quantity", MAX_QUANTITY + 1),
        ("unit", "LITRE"),
        ("is_active", 2),
        ("category_id", 99999),
        ("name", ""),
        ("name", "x" * 201),
        ("barcode", "123"),
        ("description", "x" * 2001),
    ],
)
def test_database_rejects_invalid_product_values(
    engine: Engine, populated: tuple[int, int, int], column: str, value: object
) -> None:
    # Column names are test-owned constants; values always use bound parameters.
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text(f"UPDATE products SET {column} = :value"), {"value": value})


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("parent_id", 99999),
        ("name", ""),
        ("slug", "x" * 101),
        ("sort_order", "0.5"),
        ("sort_order", MAX_QUANTITY + 1),
        ("is_active", 2),
    ],
)
def test_database_rejects_invalid_category_values(
    engine: Engine, populated: tuple[int, int, int], column: str, value: object
) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text(f"UPDATE categories SET {column} = :value"), {"value": value})


def test_category_cannot_parent_itself(engine: Engine, populated: tuple[int, int, int]) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text("UPDATE categories SET parent_id = id"))


@pytest.mark.parametrize(
    "kind", ["parent", "product_category", "slug", "category_uuid", "barcode", "product_uuid"]
)
def test_restrict_and_uniqueness(
    engine: Engine, populated: tuple[int, int, int], kind: str
) -> None:
    root_id, child_id, product_id = populated
    sessions = create_session_factory(engine)
    with pytest.raises(IntegrityError), sessions.begin() as session:
        if kind in ("parent", "product_category"):
            session.delete(session.get(Category, root_id if kind == "parent" else child_id))
        elif kind in ("slug", "category_uuid"):
            original = session.get(Category, root_id)
            new = Category(name="Другая", slug="food" if kind == "slug" else "other")
            if kind == "category_uuid":
                new.public_id = original.public_id
            session.add(new)
        else:
            original = session.get(Product, product_id)
            new = Product(
                name="Другой товар",
                category_id=child_id,
                unit=ProductUnit.KG,
                price_minor=100,
                barcode=original.barcode if kind == "barcode" else generate_internal_ean13(2),
            )
            if kind == "product_uuid":
                new.public_id = original.public_id
            session.add(new)


@pytest.mark.parametrize("value", [True, "100", 1.5, -1, MAX_PRICE_MINOR + 1])
def test_orm_rejects_invalid_price_before_sql(value: object) -> None:
    with pytest.raises(ValueError, match="price_minor"):
        Product(price_minor=value)


def test_orm_rejects_invalid_barcode_before_sql() -> None:
    with pytest.raises(ValueError, match="EAN"):
        Product(barcode="2000000000016")


def test_populated_downgrade_and_reupgrade(engine: Engine, populated: tuple[int, int, int]) -> None:
    with engine.begin() as connection:
        config = migration_config(connection)
        command.downgrade(config, "base")
        assert set(inspect(connection).get_table_names()) == {"alembic_version"}
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        assert connection.scalar(text("SELECT count(*) FROM products")) == 0
        command.check(config)
    assert inspect(engine).has_table("categories")


def test_migration_rollback_is_atomic(tmp_path: Path) -> None:
    engine = create_db_engine(URL.create("sqlite", database=str(tmp_path / "rollback.db")))
    try:
        with pytest.raises(RuntimeError, match="Abort"), engine.begin() as connection:
            command.upgrade(migration_config(connection), "head")
            raise RuntimeError("Abort")
        assert inspect(engine).get_table_names() == []
    finally:
        engine.dispose()


def test_postgresql_offline_sql_without_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(database_url="postgresql://"),
    )
    config = Config(str(ROOT / "alembic.ini"))
    output = StringIO()
    config.output_buffer = output
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "CREATE TABLE categories" in sql
    assert "CREATE TABLE products" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql
    assert "ON DELETE RESTRICT" in sql
    assert "UUID" in sql
    assert "CREATE TYPE" not in sql
    assert "unit VARCHAR(5)" in sql
````

tests/integration/test_db.py

````python
"""Exercise real SQLite transactions and UTC storage in a temporary database."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from pathlib import Path

import pytest
from sqlalchemy import URL, ForeignKey, MetaData, delete, func, inspect, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from app.db.base import Base
from app.db.session import create_db_engine, create_session_factory
from app.db.types import UTCDateTime


class DatabaseTestBase(Base):
    __abstract__ = True
    metadata = MetaData(naming_convention=Base.metadata.naming_convention)


class Parent(DatabaseTestBase):
    __tablename__ = "test_parents"

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class Child(DatabaseTestBase):
    __tablename__ = "test_children"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("test_parents.id", ondelete="RESTRICT"))


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    url = URL.create("sqlite+pysqlite", database=str(tmp_path / "test.db"))
    engine = create_db_engine(url)
    try:
        DatabaseTestBase.metadata.create_all(engine)
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


def test_pragmas_on_two_physical_connections(engine: Engine) -> None:
    with engine.connect() as first, engine.connect() as second:
        assert first.connection.driver_connection is not second.connection.driver_connection
        for connection in (first, second):
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 5000
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"


def test_foreign_key_rejects_unknown_parent(sessions: sessionmaker[Session]) -> None:
    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.add(Child(parent_id=999))


def test_restrict_prevents_deleting_parent(sessions: sessionmaker[Session]) -> None:
    with sessions.begin() as session:
        session.add(Parent(id=1))
        session.flush()
        session.add(Child(parent_id=1))
    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.execute(delete(Parent).where(Parent.id == 1))
    with sessions() as session:
        assert session.get(Parent, 1) is not None


def test_rollback_reverts_all_changes(sessions: sessionmaker[Session]) -> None:
    with pytest.raises(RuntimeError, match="Abort transaction"), sessions.begin() as session:
        session.add(Parent(id=1))
        session.flush()
        session.add(Child(parent_id=1))
        session.flush()
        raise RuntimeError("Abort transaction")
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Parent)) == 0
        assert session.scalar(select(func.count()).select_from(Child)) == 0


def test_close_without_commit_discards_changes(sessions: sessionmaker[Session]) -> None:
    with sessions() as session:
        session.add(Parent(id=1))
        session.flush()
    with sessions() as session:
        assert session.get(Parent, 1) is None


def test_outer_rollback_includes_released_savepoint(sessions: sessionmaker[Session]) -> None:
    with pytest.raises(RuntimeError, match="Abort outer transaction"), sessions.begin() as session:
        with session.begin_nested():
            session.add(Parent(id=1))
        raise RuntimeError("Abort outer transaction")
    with sessions() as session:
        assert session.get(Parent, 1) is None


def test_ddl_is_transactional(engine: Engine) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text("CREATE TABLE rollback_probe (id INTEGER PRIMARY KEY)"))
        transaction.rollback()
    assert not inspect(engine).has_table("rollback_probe")


@pytest.mark.parametrize(
    "value",
    [
        None,
        datetime(2026, 1, 1, 1, 2, 3, 123456, tzinfo=timezone(timedelta(hours=5))),
        datetime(2026, 1, 1, 23, 59, 59, tzinfo=timezone(timedelta(hours=-7))),
        datetime(2026, 10, 10, tzinfo=UTC),
    ],
)
def test_datetime_roundtrip_uses_utc(
    sessions: sessionmaker[Session], value: datetime | None
) -> None:
    with sessions.begin() as session:
        session.add(Parent(id=1, occurred_at=value))
    with sessions() as session:
        actual = session.scalar(select(Parent.occurred_at).where(Parent.id == 1))
        if value is None:
            assert actual is None
        else:
            assert actual == value.astimezone(UTC)
            assert actual.tzinfo is UTC
            raw = session.execute(
                text("SELECT occurred_at FROM test_parents WHERE id = :id"), {"id": 1}
            )
            stored = datetime.fromisoformat(raw.scalar_one())
            assert stored.tzinfo is None
            assert stored == value.astimezone(UTC).replace(tzinfo=None)


class MissingOffset(tzinfo):
    def utcoffset(self, value: datetime | None) -> None:
        return None


@pytest.mark.parametrize(
    "value", [datetime(2026, 1, 1), datetime(2026, 1, 1, tzinfo=MissingOffset())]
)
def test_datetime_without_offset_is_rejected(
    sessions: sessionmaker[Session], value: datetime
) -> None:
    with pytest.raises(StatementError, match="timezone-aware"), sessions.begin() as session:
        session.add(Parent(occurred_at=value))


def test_postgresql_datetime_conversion_without_server() -> None:
    dialect = postgresql.dialect()
    column_type = UTCDateTime()
    local = datetime(2026, 1, 1, 1, tzinfo=timezone(timedelta(hours=5)))
    expected = datetime(2025, 12, 31, 20, tzinfo=UTC)
    assert column_type.process_bind_param(local, dialect) == expected
    assert column_type.process_result_value(local, dialect) == expected
    assert column_type.process_bind_param(None, dialect) is None
    assert column_type.process_result_value(None, dialect) is None
    assert str(column_type.compile(dialect=dialect)) == "TIMESTAMP WITH TIME ZONE"


@pytest.mark.parametrize(
    "url", ["not-a-url", "mysql://localhost/shop", "sqlite+aiosqlite:///shop.db"]
)
def test_invalid_or_unsupported_database_url_is_rejected(url: str) -> None:
    with pytest.raises(ValueError, match="DATABASE_URL"):
        create_db_engine(url)


def test_memory_database_can_be_used_sequentially() -> None:
    engine = create_db_engine("sqlite:///:memory:")
    try:
        DatabaseTestBase.metadata.create_all(engine)
        sessions = create_session_factory(engine)
        with sessions.begin() as session:
            session.add(Parent(id=1))
        with sessions() as session:
            assert session.get(Parent, 1) is not None
    finally:
        engine.dispose()
````

tests/integration/test_payments.py

````python
"""Payment invariants, ambiguous network outcomes, and signed event processing."""

import hashlib
import hmac
import json
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select

from app.core.config import Settings
from app.core.enums import OrderStatus, PaymentStatus, ProductUnit
from app.core.errors import AppError, install_error_handlers
from app.db.session import create_db_engine, create_session_factory
from app.models import Category, Order, OrderItem, Payment, PaymentEvent, Product, StockMovement
from app.providers.base import BankStatus, ProviderUnavailable
from app.providers.fake import FakeProvider
from app.providers.mock_bank import MockBankProvider
from app.routers.payments import router
from app.services.payments import PaymentService
from app.services.qr_service import make_qr_png

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def setup(tmp_path, monkeypatch):
    for key in Settings.model_fields:
        monkeypatch.delenv(key.upper(), raising=False)
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite:///{tmp_path / 'payments.db'}",
        secret_key=secrets.token_urlsafe(32),
        webhook_secret=secrets.token_urlsafe(32),
        bank_merchant_api_key=secrets.token_urlsafe(32),
    )
    engine = create_db_engine(settings.database_url)
    config = Config(str(ROOT / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    factory = create_session_factory(engine)
    with factory.begin() as session:
        category = Category(name="Еда", slug="food")
        session.add(category)
        session.flush()
        product = Product(
            name="Молоко",
            barcode="2000000000015",
            category_id=category.id,
            unit=ProductUnit.PIECE,
            price_minor=100,
            stock_quantity=5,
        )
        session.add(product)
        order = Order(number="TEST-1", terminal_code="main")
        session.add(order)
        session.flush()
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                barcode=product.barcode,
                unit=product.unit,
                unit_price_minor=100,
                quantity=2,
                line_total_minor=200,
            )
        )
        order_uuid = order.public_id
    provider = FakeProvider()
    service = PaymentService(factory, provider, settings)
    yield service, factory, provider, settings, order_uuid
    engine.dispose()


def make_event(provider, payment, *, status=BankStatus.PAID, **changes):
    invoice = provider.finish(provider.references[UUID(payment["public_id"])], status)
    body = {
        "event_id": str(invoice.event_id),
        "type": f"invoice.{status.value.lower()}",
        "created_at": datetime.now(UTC).isoformat(),
        "data": {
            "invoice_id": str(invoice.invoice_id),
            "merchant_reference": str(invoice.merchant_reference),
            "amount_minor": invoice.amount_minor,
            "currency": invoice.currency,
            "failure_reason": invoice.failure_reason,
        },
    }
    body["data"].update(changes)
    return json.dumps(body).encode()


def deliver(service, settings, body, timestamp=None):
    timestamp = str(int(time.time())) if timestamp is None else timestamp
    signature = hmac.new(
        settings.webhook_secret.get_secret_value().encode(),
        timestamp.encode() + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    return service.process_webhook(body, timestamp, signature)


def test_checkout_is_idempotent_and_success_commits_once(setup):
    service, factory, provider, settings, order_uuid = setup
    payment = service.checkout(order_uuid)
    assert service.checkout(order_uuid)["public_id"] == payment["public_id"]
    assert provider.create_calls == 1
    body = make_event(provider, payment)
    assert deliver(service, settings, body)["outcome"] == "applied"
    assert deliver(service, settings, body)["outcome"] == "duplicate"
    assert service.refresh(UUID(payment["public_id"]))["status"] == "SUCCEEDED"
    with factory() as session:
        product = session.scalar(select(Product))
        assert (product.stock_quantity, product.reserved_quantity) == (3, 0)
        assert session.scalar(select(Order.status)) is OrderStatus.PAID
        assert session.scalar(select(func.count()).select_from(StockMovement)) == 1
        assert session.scalar(select(func.count()).select_from(PaymentEvent)) == 1


@pytest.mark.parametrize("mode", ["signature", "past", "future", "malformed"])
def test_invalid_signed_input_changes_nothing(setup, mode):
    service, factory, provider, settings, order_uuid = setup
    payment = service.checkout(order_uuid)
    body = make_event(provider, payment)
    with pytest.raises(AppError) as error:
        if mode == "signature":
            service.process_webhook(body, str(int(time.time())), "0" * 64)
        elif mode == "malformed":
            deliver(service, settings, body, "not-a-timestamp")
        else:
            offset = -301 if mode == "past" else 301
            deliver(service, settings, body, str(int(time.time()) + offset))
    assert error.value.status_code == 401
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(PaymentEvent)) == 0
        assert session.scalar(select(Payment.status)) is PaymentStatus.PENDING
        assert session.scalar(select(Product.reserved_quantity)) == 2


@pytest.mark.parametrize(
    "change",
    [
        {"amount_minor": 201},
        {"currency": "USD"},
        {"merchant_reference": str(uuid4())},
        {"invoice_id": str(uuid4())},
    ],
)
def test_wrong_signed_data_is_durable_review_without_transition(setup, change):
    service, factory, provider, settings, order_uuid = setup
    payment = service.checkout(order_uuid)
    body = make_event(provider, payment, **change)
    with pytest.raises(AppError) as error:
        deliver(service, settings, body)
    assert error.value.status_code == 422
    assert deliver(service, settings, body)["outcome"] == "duplicate"
    with factory() as session:
        payment = session.scalar(select(Payment))
        assert payment.status is PaymentStatus.PENDING and payment.needs_review
        assert session.scalar(select(Product.reserved_quantity)) == 2
        assert session.scalar(select(PaymentEvent.outcome)) == "mismatch"


def test_late_success_after_cancellation_does_not_sell_stock(setup):
    service, factory, provider, settings, order_uuid = setup
    payment = service.checkout(order_uuid)
    assert service.cancel(UUID(payment["public_id"]))["status"] == "CANCELLED"
    body = json.loads(make_event(provider, payment))
    body["event_id"] = str(uuid4())
    body["type"] = "invoice.paid"
    assert deliver(service, settings, json.dumps(body).encode())["outcome"] == "late_success"
    with factory() as session:
        payment = session.scalar(select(Payment))
        assert payment.status is PaymentStatus.CANCELLED and payment.needs_review
        assert payment.review_reason == "late_success"
        assert session.scalar(select(Order.status)) is OrderStatus.OPEN
        assert session.scalar(select(Product.stock_quantity)) == 5
        assert session.scalar(select(Product.reserved_quantity)) == 0


def test_connection_refusal_compensates_but_timeout_preserves_reservation(setup):
    service, factory, provider, settings, order_uuid = setup
    provider.create_error = ProviderUnavailable(definitely_not_created=True)
    with pytest.raises(AppError) as error:
        service.checkout(order_uuid)
    assert error.value.status_code == 503
    with factory() as session:
        assert session.scalar(select(Payment.status)) is PaymentStatus.FAILED
        assert session.scalar(select(Order.status)) is OrderStatus.OPEN
        assert session.scalar(select(Product.reserved_quantity)) == 0
    provider.create_error = ProviderUnavailable()
    with pytest.raises(AppError):
        service.checkout(order_uuid)
    with factory() as session:
        pending_id = session.scalar(
            select(Payment.public_id).where(Payment.status == PaymentStatus.PENDING)
        )
        assert session.scalar(select(Order.status)) is OrderStatus.PENDING_PAYMENT
        assert session.scalar(select(Product.reserved_quantity)) == 2
    provider.create_error = None
    recovered = service.refresh(pending_id)
    assert recovered["public_id"] == str(pending_id)
    assert recovered["pay_url"]


def test_lost_creation_response_recovers_same_invoice(setup, monkeypatch):
    service, factory, provider, settings, order_uuid = setup
    original = provider.create_invoice

    def lose_response(**kwargs):
        original(**kwargs)
        raise ProviderUnavailable()

    monkeypatch.setattr(provider, "create_invoice", lose_response)
    with pytest.raises(AppError):
        service.checkout(order_uuid)
    with factory() as session:
        payment_id = session.scalar(select(Payment.public_id))
    assert len(provider.invoices) == 1
    monkeypatch.setattr(provider, "create_invoice", original)
    assert service.refresh(payment_id)["pay_url"]
    assert len(provider.invoices) == 1


def test_early_webhook_waits_for_invoice_binding(setup, monkeypatch):
    service, factory, provider, settings, order_uuid = setup
    original = provider.create_invoice

    def early_event(**kwargs):
        invoice = original(**kwargs)
        body = make_event(provider, {"public_id": str(invoice.merchant_reference)})
        assert deliver(service, settings, body)["outcome"] == "awaiting_invoice"
        return invoice

    monkeypatch.setattr(provider, "create_invoice", early_event)
    payment = service.checkout(order_uuid)
    assert payment["status"] == "SUCCEEDED"
    with factory() as session:
        assert session.scalar(select(PaymentEvent.outcome)) == "applied"
        assert session.scalar(select(Product.stock_quantity)) == 3


def test_multi_item_shortage_rolls_back_every_reservation(setup):
    service, factory, provider, settings, order_uuid = setup
    with factory.begin() as session:
        product = session.scalar(select(Product))
        second = Product(
            name="Сыр",
            barcode="2000000000022",
            category_id=product.category_id,
            unit=ProductUnit.PIECE,
            price_minor=100,
            stock_quantity=0,
        )
        session.add(second)
        session.flush()
        order = session.scalar(select(Order))
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=second.id,
                product_name=second.name,
                barcode=second.barcode,
                unit=second.unit,
                unit_price_minor=100,
                quantity=1,
                line_total_minor=100,
            )
        )
    with pytest.raises(AppError) as error:
        service.checkout(order_uuid)
    assert error.value.code == "INSUFFICIENT_STOCK"
    with factory() as session:
        assert list(session.scalars(select(Product.reserved_quantity))) == [0, 0]
        assert session.scalar(select(Order.status)) is OrderStatus.OPEN
        assert session.scalar(select(func.count()).select_from(Payment)) == 0
    assert provider.create_calls == 0


@pytest.mark.parametrize("operation", ["cancel", "refresh"])
def test_network_unavailable_during_existing_invoice_keeps_reserve(setup, monkeypatch, operation):
    service, factory, provider, settings, order_uuid = setup
    payment = service.checkout(order_uuid)

    def fail(_invoice_id):
        raise ProviderUnavailable(definitely_not_created=True)

    monkeypatch.setattr(
        provider, "cancel_invoice" if operation == "cancel" else "get_invoice_status", fail
    )
    with pytest.raises(AppError):
        getattr(service, operation)(UUID(payment["public_id"]))
    with factory() as session:
        assert session.scalar(select(Payment.status)) is PaymentStatus.PENDING
        assert session.scalar(select(Product.reserved_quantity)) == 2


def test_expiry_sweep_waits_for_grace_and_bank_confirmation(setup):
    service, factory, provider, settings, order_uuid = setup
    payment = service.checkout(order_uuid)
    invoice_id = provider.references[UUID(payment["public_id"])]
    with factory.begin() as session:
        session.scalar(select(Payment)).expires_at = datetime.now(UTC) - timedelta(seconds=10)
    assert service.sweep() == 0
    with factory.begin() as session:
        session.scalar(select(Payment)).expires_at = datetime.now(UTC) - timedelta(seconds=60)
    assert service.sweep() == 1
    assert service.get_payment(UUID(payment["public_id"]))["status"] == "PENDING"
    provider.invoices[invoice_id] = provider.invoices[invoice_id].model_copy(
        update={
            "expires_at": datetime.now(UTC) - timedelta(seconds=60),
        }
    )
    with factory.begin() as session:
        session.scalar(select(Payment)).expires_at = datetime.now(UTC) - timedelta(seconds=60)
    assert service.sweep() == 1
    assert service.get_payment(UUID(payment["public_id"]))["status"] == "EXPIRED"


def test_qr_png_size_and_exact_payload(monkeypatch):
    import qrcode

    captured = []
    original = qrcode.QRCode.add_data

    def capture(self, data, *args, **kwargs):
        captured.append(data)
        return original(self, data, *args, **kwargs)

    monkeypatch.setattr(qrcode.QRCode, "add_data", capture)
    url = "http://bank.test/pay/random-token"
    png = make_qr_png(url)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert min(Image.open(BytesIO(png)).size) >= 300
    assert captured == [url]


@pytest.mark.parametrize("kind", ["connect", "timeout", "server", "invalid", "unauthorized"])
def test_http_adapter_classifies_failure_without_echoing_secrets(setup, kind):
    service, factory, provider, settings, order_uuid = setup

    def transport(request):
        if kind == "connect":
            raise httpx.ConnectError("sensitive-value")
        if kind == "timeout":
            raise httpx.ReadTimeout("sensitive-value")
        return httpx.Response(
            {"server": 503, "invalid": 200, "unauthorized": 401}[kind],
            json={"sensitive-value": "do-not-echo"},
        )

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        adapter = MockBankProvider(client, settings)
        with pytest.raises(ProviderUnavailable) as error:
            adapter.create_invoice(
                amount_minor=100,
                currency="KZT",
                merchant_reference=uuid4(),
                description="Чек",
                ttl_seconds=300,
            )
    assert error.value.definitely_not_created == (kind in ("connect", "unauthorized"))
    assert "sensitive" not in str(error.value)


def test_simultaneous_checkout_uses_one_creation_lease(setup, monkeypatch):
    service, factory, provider, settings, order_uuid = setup
    started, release = Event(), Event()
    original = provider.create_invoice

    def delayed(**kwargs):
        started.set()
        assert release.wait(timeout=5)
        return original(**kwargs)

    monkeypatch.setattr(provider, "create_invoice", delayed)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(service.checkout, order_uuid)
        assert started.wait(timeout=5)
        try:
            second = service.checkout(order_uuid)
            assert second["status"] == "PENDING" and second["pay_url"] is None
            with pytest.raises(AppError) as error:
                service.cancel(UUID(second["public_id"]))
            assert error.value.code == "INVOICE_NOT_READY"
        finally:
            release.set()
        completed = first.result(timeout=5)
    assert completed["public_id"] == second["public_id"]
    assert completed["pay_url"] and provider.create_calls == 1
    with factory() as session:
        payment = session.scalar(select(Payment))
        assert payment.creation_attempts == 1 and payment.creation_started_at is None
        assert session.scalar(select(Product.reserved_quantity)) == 2


def test_connect_error_after_ambiguous_attempt_never_releases_reserve(setup):
    service, factory, provider, settings, order_uuid = setup
    provider.create_error = ProviderUnavailable()
    with pytest.raises(AppError):
        service.checkout(order_uuid)
    provider.create_error = ProviderUnavailable(definitely_not_created=True)
    with pytest.raises(AppError):
        service.checkout(order_uuid)
    with factory() as session:
        payment = session.scalar(select(Payment))
        assert payment.status is PaymentStatus.PENDING
        assert payment.creation_attempts == 2
        assert session.scalar(select(Product.reserved_quantity)) == 2


def test_creation_lease_recovers_after_process_crash(setup):
    service, factory, provider, settings, order_uuid = setup
    provider.create_error = ProviderUnavailable()
    with pytest.raises(AppError):
        service.checkout(order_uuid)
    with factory.begin() as session:
        payment = session.scalar(select(Payment))
        payment.creation_started_at = datetime.now(UTC) - timedelta(seconds=31)
        payment_id = payment.public_id
    provider.create_error = None
    assert service.sweep() == 1
    assert service.get_payment(payment_id)["pay_url"]


def test_empty_inactive_and_zero_total_checkout_rollback(setup):
    service, factory, provider, settings, order_uuid = setup
    with factory.begin() as session:
        session.scalar(select(Category)).is_active = False
    with pytest.raises(AppError) as error:
        service.checkout(order_uuid)
    assert error.value.code == "INSUFFICIENT_STOCK"
    with factory.begin() as session:
        session.scalar(select(Category)).is_active = True
        session.scalar(select(OrderItem)).unit_price_minor = 0
    with pytest.raises(AppError) as error:
        service.checkout(order_uuid)
    assert error.value.code == "INVALID_PAYMENT_AMOUNT"
    with factory.begin() as session:
        session.delete(session.scalar(select(OrderItem)))
    with pytest.raises(AppError) as error:
        service.checkout(order_uuid)
    assert error.value.code == "EMPTY_ORDER"
    with factory() as session:
        assert session.scalar(select(Product.reserved_quantity)) == 0
        assert session.scalar(select(Order.status)) is OrderStatus.OPEN


def test_public_qr_route_signature_webhook_and_private_mutations(setup):
    service, factory, provider, settings, order_uuid = setup
    payment = service.checkout(order_uuid)
    app = FastAPI()
    app.state.session_factory, app.state.provider, app.state.settings = factory, provider, settings
    install_error_handlers(app)
    app.include_router(router)
    path = f"/api/v1/payments/{payment['public_id']}"
    with TestClient(app) as client:
        response = client.get(path)
        assert response.status_code == 200
        assert "provider_invoice_id" not in response.text
        assert response.headers["cache-control"] == "no-store"
        image = client.get(path + "/qr.png")
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"
        assert image.headers["cache-control"] == "no-store"
        assert min(Image.open(BytesIO(image.content)).size) >= 300
        assert client.post(path + "/cancel").status_code == 401
        assert client.post(path + "/refresh").status_code == 401
        raw = make_event(provider, payment)
        timestamp = str(int(time.time()))
        signature = hmac.new(
            settings.webhook_secret.get_secret_value().encode(),
            timestamp.encode() + b"." + raw,
            hashlib.sha256,
        ).hexdigest()
        result = client.post(
            "/api/v1/webhooks/mock-bank",
            content=raw,
            headers={"X-Timestamp": timestamp, "X-Signature": signature},
        )
        assert result.status_code == 200
        assert client.get(path + "/qr.png").status_code == 409
        assert client.post("/api/v1/webhooks/mock-bank", content=b"x" * 16385).status_code == 413


def test_cancel_order_and_already_paid_conflict(setup):
    service, factory, provider, settings, order_uuid = setup
    payment = service.checkout(order_uuid)
    cancelled = service.cancel_order(order_uuid)
    assert cancelled["status"] == "CANCELLED"
    assert service.cancel_order(order_uuid)["status"] == "CANCELLED"
    assert service.cancel(UUID(payment["public_id"]))["status"] == "CANCELLED"
    with pytest.raises(AppError):
        service.checkout(order_uuid)
    with pytest.raises(AppError) as error:
        service.cancel_order(uuid4())
    assert error.value.status_code == 404
````

tests/integration/test_web_pages.py

````python
"""Verify protected HTML routes, template escaping, and offline asset delivery."""

import secrets
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.enums import UserRole
from app.db.session import create_db_engine, create_session_factory
from app.main import create_app
from app.models import User
from app.providers.fake import FakeProvider
from app.services.auth import PASSWORD_HASHER

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def password_pair():
    password = secrets.token_urlsafe(24)
    return password, PASSWORD_HASHER.hash(password)


@pytest.fixture
def web_client(tmp_path, monkeypatch, password_pair):
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite:///{tmp_path / 'pages.db'}",
        secret_key=secrets.token_urlsafe(32),
        webhook_secret=secrets.token_urlsafe(32),
        bank_merchant_api_key=secrets.token_urlsafe(32),
    )
    engine = create_db_engine(settings.database_url)
    try:
        with engine.begin() as connection:
            config = Config(str(ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        with create_session_factory(engine).begin() as session:
            session.add_all(
                [
                    User(username="admin", password_hash=password_pair[1], role=UserRole.ADMIN),
                    User(username="cashier", password_hash=password_pair[1], role=UserRole.CASHIER),
                ]
            )
    finally:
        engine.dispose()
    with TestClient(create_app(settings, provider=FakeProvider(), run_worker=False)) as client:
        yield client


def login(client, password_pair, username="admin"):
    response = client.post(
        "/api/v1/auth/login", json={"username": username, "password": password_pair[0]}
    )
    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/cashier", "/admin", f"/receipt/{uuid4()}"])
def test_protected_html_redirects_before_render(web_client, path):
    response = web_client.get(path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert "product-form" not in response.text


@pytest.mark.parametrize("path", ["/login", "/price-check", "/display/main"])
def test_public_html_uses_local_assets_and_security_policy(web_client, path):
    response = web_client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-store"
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert 'src="/static/shop.js"' in response.text
    assert 'href="/static/shop.css"' in response.text
    assert "https://" not in response.text
    assert 'lang="ru"' in response.text


def test_cashier_role_cannot_render_admin(web_client, password_pair):
    login(web_client, password_pair, "cashier")
    response = web_client.get("/admin")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    response = web_client.get("/cashier")
    assert response.status_code == 200
    assert 'id="scan-form"' in response.text
    assert 'href="/admin"' not in response.text


def test_admin_can_render_operational_pages(web_client, password_pair):
    login(web_client, password_pair)
    for path in ["/admin", "/cashier", f"/receipt/{uuid4()}"]:
        response = web_client.get(path)
        assert response.status_code == 200
        assert 'href="/admin"' in response.text
    assert 'id="print-receipt"' in response.text


def test_injected_terminal_does_not_render_html(web_client):
    response = web_client.get("/display/%3Cscript%3Ealert(1)%3C%2Fscript%3E")
    assert response.status_code in (404, 422)
    assert "<script>alert" not in response.text


@pytest.mark.parametrize("filename", ["shop.css", "shop.js", "mark.svg"])
def test_static_assets_are_delivered_without_auth(web_client, filename):
    response = web_client.get(f"/static/{filename}")
    assert response.status_code == 200
    assert response.content


def test_logout_protects_next_html_request(web_client, password_pair):
    login(web_client, password_pair)
    response = web_client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": web_client.cookies["csrf_token"]}
    )
    assert response.status_code == 200
    assert web_client.get("/cashier", follow_redirects=False).status_code == 303
````

tests/test_mock_bank.py

````python
"""Exercise the independent bank through HTTP and durable transaction boundaries."""

import hashlib
import hmac
import json
import os
import secrets
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from mock_bank.config import Settings
from mock_bank.db import utc_now
from mock_bank.errors import BankError
from mock_bank.main import create_app
from mock_bank.models import BankAccount, BankEvent, BankTransaction, Invoice, WebhookDelivery
from mock_bank.schemas import InvoiceCreate
from mock_bank.seed import seed_accounts


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    for name in list(os.environ):
        if name.casefold() in Settings.model_fields:
            monkeypatch.delenv(name)
    return Settings(
        _env_file=None,
        bank_database_url=f"sqlite:///{tmp_path / 'bank.db'}",
        bank_public_url="http://bank.test",
        shop_webhook_url="http://shop.test/webhook",
        bank_merchant_api_key=secrets.token_urlsafe(32),
        webhook_secret=secrets.token_urlsafe(32),
    )


@pytest.fixture
def bank(settings: Settings):
    deliveries = []

    def webhook(request: httpx.Request) -> httpx.Response:
        assert application.state.engine.pool.checkedout() == 0
        deliveries.append(request)
        return httpx.Response(204)

    with httpx.Client(transport=httpx.MockTransport(webhook)) as client:
        application = create_app(settings, webhook_client=client, run_worker=False)
        with TestClient(application) as api:
            seed_accounts(application.state.session_factory)
            yield api, application, deliveries


def auth(settings: Settings) -> dict:
    return {"Authorization": "Bearer " + settings.bank_merchant_api_key.get_secret_value()}


def payload(**changes) -> dict:
    return {
        "merchant_reference": str(uuid4()),
        "amount_minor": 10000,
        "currency": "KZT",
        "description": "Учебная покупка",
        "ttl_seconds": 300,
        **changes,
    }


def create(bank, settings: Settings, **changes) -> dict:
    result = bank[0].post("/api/merchant/invoices", json=payload(**changes), headers=auth(settings))
    assert result.status_code == 200, result.text
    return result.json()


def token(invoice: dict) -> str:
    return invoice["pay_url"].rsplit("/", 1)[1]


def account(bank, *, richest=True) -> BankAccount:
    with bank[1].state.session_factory() as session:
        ordering = BankAccount.balance_minor.desc() if richest else BankAccount.balance_minor
        return session.scalar(select(BankAccount).order_by(ordering).limit(1))


def test_bank_merchant_auth_and_health(bank, settings: Settings) -> None:
    api, app, _ = bank
    assert api.get("/health").json() == {"status": "ok", "database": "ok"}
    for headers in ({}, {"Authorization": "Bearer invalid"}, {"Authorization": "Basic x"}):
        result = api.post("/api/merchant/invoices", json=payload(), headers=headers)
        assert result.status_code == 401
        assert result.json()["error"]["code"] == "UNAUTHORIZED"
    assert api.get(f"/api/merchant/invoices/{uuid4()}", headers=auth(settings)).status_code == 404
    assert not app.state.engine.url.database.endswith("shop.db")


def test_idempotent_create_current_status_and_parameter_conflict(bank, settings: Settings) -> None:
    api, _, _ = bank
    data = payload()
    first = api.post("/api/merchant/invoices", json=data, headers=auth(settings)).json()
    second = api.post("/api/merchant/invoices", json=data, headers=auth(settings)).json()
    assert first["invoice_id"] == second["invoice_id"]
    assert first["expires_at"] == second["expires_at"]
    assert len(token(first)) == 32
    assert UUID(first["invoice_id"]).version == 4
    assert first["event_id"] is None
    conflict = api.post(
        "/api/merchant/invoices", json={**data, "amount_minor": 2}, headers=auth(settings)
    )
    assert conflict.status_code == 409
    cancelled = api.post(
        f"/api/merchant/invoices/{first['invoice_id']}/cancel", headers=auth(settings)
    ).json()
    replay = api.post("/api/merchant/invoices", json=data, headers=auth(settings)).json()
    assert replay["status"] == "CANCELLED"
    assert replay["event_id"] == cancelled["event_id"]


@pytest.mark.parametrize("value", [True, False, 0, -1, "100", 1.5, 2**63])
def test_amounts_require_positive_bounded_integers(bank, settings: Settings, value) -> None:
    assert (
        bank[0]
        .post("/api/merchant/invoices", json=payload(amount_minor=value), headers=auth(settings))
        .status_code
        == 422
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"currency": "USD"},
        {"ttl_seconds": 0},
        {"ttl_seconds": True},
        {"ttl_seconds": 86401},
        {"description": ""},
        {"unexpected": "secret-canary"},
    ],
)
def test_invalid_invoice_fields_are_sanitized(bank, settings: Settings, changes: dict) -> None:
    result = bank[0].post("/api/merchant/invoices", json=payload(**changes), headers=auth(settings))
    assert result.status_code == 422
    assert "secret-canary" not in result.text


def test_payment_once_signed_webhook_and_transaction(bank, settings: Settings) -> None:
    api, app, deliveries = bank
    invoice = create(bank, settings)
    selected = account(bank)
    result = api.post(f"/api/pay/{token(invoice)}", json={"account_id": str(selected.id)})
    assert result.status_code == 200
    paid = result.json()
    assert paid["status"] == "PAID"
    assert paid["event_id"] and paid["paid_at"]
    assert (
        api.post(f"/api/pay/{token(invoice)}", json={"account_id": str(selected.id)}).status_code
        == 409
    )
    assert (
        api.post(
            f"/api/merchant/invoices/{invoice['invoice_id']}/cancel", headers=auth(settings)
        ).status_code
        == 409
    )
    assert len(deliveries) == 1
    request = deliveries[0]
    expected = hmac.new(
        settings.webhook_secret.get_secret_value().encode(),
        request.headers["X-Timestamp"].encode() + b"." + request.content,
        hashlib.sha256,
    ).hexdigest()
    assert request.headers["X-Signature"] == expected
    event = json.loads(request.content)
    assert event["event_id"] == paid["event_id"]
    assert event["type"] == "invoice.paid"
    assert event["data"]["merchant_reference"] == invoice["merchant_reference"]
    with app.state.session_factory() as session:
        assert (
            session.get(BankAccount, selected.id).balance_minor
            == selected.balance_minor - invoice["amount_minor"]
        )
        assert session.scalar(select(func.count()).select_from(BankTransaction)) == 1
        assert session.scalar(select(func.count()).select_from(BankEvent)) == 1
        assert session.scalar(select(WebhookDelivery)).response_status == 204


def test_insufficient_funds_preserves_balance_and_emits_failure(bank, settings: Settings) -> None:
    invoice = create(bank, settings)
    selected = account(bank, richest=False)
    result = bank[0].post(f"/api/pay/{token(invoice)}", json={"account_id": str(selected.id)})
    assert result.status_code == 200
    assert result.json()["status"] == "FAILED"
    assert result.json()["failure_reason"] == "insufficient_funds"
    with bank[1].state.session_factory() as session:
        assert session.get(BankAccount, selected.id).balance_minor == 0
        assert session.scalar(select(BankTransaction)).status == "FAILED"
    assert json.loads(bank[2][0].content)["type"] == "invoice.failed"


def test_expired_payment_commits_event_before_410(bank, settings: Settings) -> None:
    invoice = create(bank, settings)
    with bank[1].state.session_factory.begin() as session:
        session.execute(update(Invoice).values(expires_at=utc_now() - timedelta(seconds=1)))
    result = bank[0].post(f"/api/pay/{token(invoice)}", json={"account_id": str(account(bank).id)})
    assert result.status_code == 410
    with bank[1].state.session_factory() as session:
        assert session.scalar(select(Invoice)).status == "EXPIRED"
        assert session.scalar(select(BankEvent)).event_type == "invoice.expired"
        assert session.scalar(select(func.count()).select_from(BankTransaction)) == 0
    bank[1].state.notifier.deliver_due()
    assert len(bank[2]) == 1


def test_sweep_expiry_is_idempotent(bank, settings: Settings) -> None:
    create(bank, settings)
    with bank[1].state.session_factory.begin() as session:
        session.execute(update(Invoice).values(expires_at=utc_now() - timedelta(seconds=1)))
    assert bank[1].state.service.sweep_expired() == 1
    assert bank[1].state.service.sweep_expired() == 0
    bank[1].state.notifier.deliver_due()
    assert json.loads(bank[2][0].content)["type"] == "invoice.expired"


def test_unknown_account_leaves_invoice_created(bank, settings: Settings) -> None:
    invoice = create(bank, settings)
    assert (
        bank[0].post(f"/api/pay/{token(invoice)}", json={"account_id": str(uuid4())}).status_code
        == 404
    )
    assert bank[0].get(f"/api/pay/{token(invoice)}").json()["status"] == "CREATED"


def test_customer_page_accounts_cancel_and_decline(bank, settings: Settings) -> None:
    invoice = create(bank, settings, description="<script>alert(1)</script>")
    page = bank[0].get(f"/pay/{token(invoice)}")
    assert page.status_code == 200
    assert "Учебный эмулятор банка" in page.text
    assert "&lt;script&gt;" in page.text and "<script>alert" not in page.text
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert bank[0].get("/static/bank.js").status_code == 200
    choices = bank[0].get(f"/api/pay/{token(invoice)}").json()["accounts"]
    assert len(choices) == 3
    assert all(
        set(choice) == {"public_id", "holder_name", "balance_minor", "balance_minor_text"}
        for choice in choices
    )
    assert bank[0].post(f"/api/pay/{token(invoice)}/cancel").json()["status"] == "CANCELLED"
    other = create(bank, settings)
    declined = bank[0].post(f"/api/pay/{token(other)}/decline").json()
    assert declined["status"] == "FAILED" and declined["failure_reason"] == "bank_declined"


def test_seed_never_restores_spent_balances(bank, settings: Settings) -> None:
    selected = account(bank)
    invoice = create(bank, settings)
    bank[1].state.service.pay(token(invoice), selected.id)
    seeded = seed_accounts(bank[1].state.session_factory)
    assert len(seeded) == 3
    assert (
        next(item for item in seeded if item["public_id"] == str(selected.id))["balance_minor"]
        == selected.balance_minor - 10000
    )


def test_negative_and_fractional_balance_rejected(bank) -> None:
    for value in (-1, "1.5"):
        with pytest.raises(IntegrityError), bank[1].state.session_factory.begin() as session:
            session.execute(
                text("UPDATE bank_accounts SET balance_minor = :value"), {"value": value}
            )


def test_concurrent_payment_debits_once(bank, settings: Settings) -> None:
    invoice = create(bank, settings)
    selected = account(bank)

    def pay():
        try:
            return bank[1].state.service.pay(token(invoice), selected.id)["status"]
        except BankError as exc:
            return exc.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: pay(), range(2)))
    assert sorted(map(str, results)) == ["409", "PAID"]
    with bank[1].state.session_factory() as session:
        assert session.get(BankAccount, selected.id).balance_minor == selected.balance_minor - 10000


def test_two_invoices_compete_for_last_balance(bank, settings: Settings) -> None:
    invoices = [create(bank, settings, amount_minor=60000) for _ in range(2)]
    with bank[1].state.session_factory() as session:
        selected = session.scalar(select(BankAccount).where(BankAccount.seed_key == "poor"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda invoice: bank[1].state.service.pay(token(invoice), selected.id)["status"],
                invoices,
            )
        )
    assert sorted(results) == ["FAILED", "PAID"]
    with bank[1].state.session_factory() as session:
        assert session.get(BankAccount, selected.id).balance_minor == 40000


def test_invoice_event_and_balance_roll_back_together(
    bank, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    invoice = create(bank, settings)
    selected = account(bank)
    original = bank[1].state.service._finalize

    def broken(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Injected rollback")

    monkeypatch.setattr(bank[1].state.service, "_finalize", broken)
    with pytest.raises(RuntimeError, match="Injected rollback"):
        bank[1].state.service.pay(token(invoice), selected.id)
    with bank[1].state.session_factory() as session:
        assert session.get(BankAccount, selected.id).balance_minor == selected.balance_minor
        assert session.scalar(select(Invoice)).status == "CREATED"
        assert session.scalar(select(func.count()).select_from(BankEvent)) == 0
        assert session.scalar(select(func.count()).select_from(BankTransaction)) == 0


@pytest.mark.parametrize("response_status", [400, 401, 422, 302])
def test_permanent_webhook_response_stops_retries(settings: Settings, response_status: int) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(response_status))
    ) as client:
        app = create_app(settings, webhook_client=client, run_worker=False)
        with TestClient(app):
            invoice = app.state.service.create_invoice(InvoiceCreate(**payload()))
            app.state.service.cancel(UUID(invoice["invoice_id"]))
            assert app.state.notifier.deliver_due() == 1
            assert app.state.notifier.deliver_due() == 0
            with app.state.session_factory() as session:
                event = session.scalar(select(BankEvent))
                assert event.stopped and not event.delivered and event.attempts == 1


def test_webhook_retries_survive_restart_and_keep_body(settings: Settings) -> None:
    requests = []

    def flaky(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ConnectError("not stored secret", request=request)
        return httpx.Response(503)

    with httpx.Client(transport=httpx.MockTransport(flaky)) as client:
        first = create_app(settings, webhook_client=client, run_worker=False)
        with TestClient(first):
            invoice = first.state.service.create_invoice(InvoiceCreate(**payload()))
            first.state.service.cancel(UUID(invoice["invoice_id"]))
            assert first.state.notifier.deliver_due() == 1
        second = create_app(settings, webhook_client=client, run_worker=False)
        with TestClient(second):
            for expected_attempt, delay in [(2, 5), (3, 25), (4, 25)]:
                with second.state.session_factory.begin() as session:
                    session.execute(
                        update(BankEvent).values(next_attempt_at=utc_now() - timedelta(seconds=1))
                    )
                before = utc_now()
                assert second.state.notifier.deliver_due() == 1
                with second.state.session_factory() as session:
                    event = session.scalar(select(BankEvent))
                    assert event.attempts == expected_attempt
                    assert event.next_attempt_at >= before + timedelta(seconds=delay)
            with second.state.session_factory() as session:
                event = session.scalar(select(BankEvent))
                assert event.stopped and not event.delivered
                assert session.scalar(select(func.count()).select_from(WebhookDelivery)) == 4
                assert (
                    session.scalar(
                        select(WebhookDelivery).where(WebhookDelivery.attempt == 1)
                    ).error_kind
                    == "ConnectError"
                )
            assert second.state.notifier.deliver_due() == 0
    assert len({request.content for request in requests}) == 1


def test_unexpected_error_does_not_expose_input_or_log_message(bank, caplog) -> None:
    @bank[1].get("/_test/failure")
    def failure():
        raise RuntimeError("secret-canary")

    result = bank[0].get("/_test/failure")
    assert result.status_code == 500
    assert result.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret-canary" not in result.text + caplog.text


def test_concurrent_idempotent_creation_returns_one_invoice(bank) -> None:
    request = InvoiceCreate(**payload())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: bank[1].state.service.create_invoice(request), range(2)))
    assert results[0]["invoice_id"] == results[1]["invoice_id"]
    with bank[1].state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Invoice)) == 1


def test_payment_and_cancel_race_has_one_final_event(bank, settings: Settings) -> None:
    invoice = create(bank, settings)
    selected = account(bank)

    def transition(pay: bool):
        try:
            if pay:
                return bank[1].state.service.pay(token(invoice), selected.id)
            return bank[1].state.service.cancel(UUID(invoice["invoice_id"]))
        except BankError as exc:
            return exc.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(transition, [True, False]))
    with bank[1].state.session_factory() as session:
        final = session.scalar(select(Invoice))
        assert final.status in ("PAID", "CANCELLED")
        debit = invoice["amount_minor"] if final.status == "PAID" else 0
        assert session.get(BankAccount, selected.id).balance_minor == selected.balance_minor - debit
        assert session.scalar(select(func.count()).select_from(BankEvent)) == 1


def test_abandoned_delivery_lease_recovers_and_keeps_event_id(bank, settings: Settings) -> None:
    invoice = create(bank, settings)
    final = bank[1].state.service.cancel(UUID(invoice["invoice_id"]))
    abandoned = bank[1].state.notifier._claim()
    assert abandoned is not None
    assert bank[1].state.notifier.deliver_due() == 0
    with bank[1].state.session_factory.begin() as session:
        session.execute(update(BankEvent).values(lease_until=utc_now() - timedelta(seconds=1)))
    assert bank[1].state.notifier.deliver_due() == 1
    assert json.loads(bank[2][0].content)["event_id"] == final["event_id"]
    with bank[1].state.session_factory() as session:
        assert session.scalar(select(BankEvent)).delivered
        attempts = session.scalars(select(WebhookDelivery).order_by(WebhookDelivery.attempt)).all()
        assert len(attempts) == 2
        assert attempts[0].completed_at is None
        assert attempts[1].response_status == 204


def test_concurrent_notifiers_claim_one_delivery(bank, settings: Settings) -> None:
    invoice = create(bank, settings)
    bank[1].state.service.cancel(UUID(invoice["invoice_id"]))
    # Test the claim boundary: one worker owns the event before any HTTP begins.
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: bank[1].state.notifier._claim(), range(2)))
    assert sum(claim is not None for claim in claims) == 1


def test_int64_money_has_exact_decimal_text_for_browser(bank, settings: Settings) -> None:
    maximum = 2**63 - 1
    invoice = create(bank, settings, amount_minor=maximum)
    assert invoice["amount_minor_text"] == str(maximum)
    selected = account(bank)
    with bank[1].state.session_factory.begin() as session:
        session.execute(
            update(BankAccount).where(BankAccount.id == selected.id).values(balance_minor=maximum)
        )
    data = bank[0].get(f"/api/pay/{token(invoice)}").json()
    chosen = next(item for item in data["accounts"] if item["public_id"] == str(selected.id))
    assert chosen["balance_minor_text"] == str(maximum)
    paid = bank[0].post(f"/api/pay/{token(invoice)}", json={"account_id": str(selected.id)}).json()
    assert paid["status"] == "PAID" and paid["amount_minor_text"] == str(maximum)
    with bank[1].state.session_factory() as session:
        assert session.get(BankAccount, selected.id).balance_minor == 0


def test_browser_money_formatter_keeps_final_minor_units() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required only for the browser formatter check")
    source = Path(__file__).resolve().parents[1] / "mock_bank" / "static" / "money.js"
    script = (
        source.read_text()
        + """
for (const value of ['0', '10001', '9007199254740991', '9223372036854775807']) {
  console.log(formatBankMoney(value).replace(/\\s/g, ''));
}
"""
    )
    result = subprocess.run([node, "-e", script], check=True, text=True, capture_output=True)
    assert result.stdout.splitlines() == [
        "0,00₸",
        "100,01₸",
        "90071992547409,91₸",
        "92233720368547758,07₸",
    ]
````

tests/unit/test_barcodes.py

````python
"""Check known EAN vectors, exact input preservation, and demo generation bounds."""

from decimal import Decimal

import pytest

from app.core.barcodes import (
    calculate_ean_check_digit,
    generate_internal_ean13,
    validate_ean,
)

KNOWN_EANS = (
    "6291041500213",  # Published GS1 manual-calculation example.
    "4006381333931",
    "5901234123457",
    "73513537",
    "96385074",
    "12345670",  # Weighted sum is 60; the check digit is zero.
    "5012345678900",  # Weighted sum is 90; the check digit is zero.
    "00000017",
    "0036000241457",
)


@pytest.mark.parametrize("barcode", KNOWN_EANS)
def test_known_ean_and_check_digit(barcode: str) -> None:
    assert calculate_ean_check_digit(barcode[:-1]) == barcode[-1]
    assert validate_ean(barcode) == barcode


@pytest.mark.parametrize("barcode", KNOWN_EANS)
def test_every_wrong_check_digit_is_rejected(barcode: str) -> None:
    for check_digit in "0123456789":
        if check_digit != barcode[-1]:
            with pytest.raises(ValueError, match="^EAN check digit is invalid$"):
                validate_ean(barcode[:-1] + check_digit)


@pytest.mark.parametrize("barcode", ["00000000", "0000000000000"])
def test_checksum_validation_does_not_claim_registration(barcode: str) -> None:
    assert validate_ean(barcode) == barcode


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        73513537,
        73513537.0,
        b"73513537",
        ["73513537"],
        "",
        "7351353",
        "735135370",
        "036000241457",
        "04006381333931",
        " 73513537",
        "73513537 ",
        "73513537\n",
        "7351 537",
        "7351353x",
        "+3513537",
        "７３５１３５３７",
        "٧٣٥١٣٥٣٧",
        "²3513537",
    ],
)
def test_ean_rejects_invalid_format_without_normalizing(value: object) -> None:
    with pytest.raises(ValueError, match="^EAN must contain exactly 8 or 13 ASCII digits$"):
        validate_ean(value)


@pytest.mark.parametrize(
    "value",
    [
        None,
        False,
        7351353,
        b"7351353",
        "",
        "123456",
        "12345678",
        "12345678901",
        "1234567890123",
        " 351353",
        "735135\n",
        "7351x53",
        "７３５１３５３",
        "٧٣٥١٣٥٣",
    ],
)
def test_check_digit_rejects_invalid_body(value: object) -> None:
    with pytest.raises(ValueError, match="^EAN body must contain exactly 7 or 12 ASCII digits$"):
        calculate_ean_check_digit(value)


@pytest.mark.parametrize(
    ("sequence", "barcode"),
    [(1, "2000000000015"), (40, "2000000000404"), (999_999_999, "2009999999997")],
)
def test_internal_generator_known_boundaries(sequence: int, barcode: str) -> None:
    assert generate_internal_ean13(sequence) == barcode


def test_internal_generator_is_stable_and_unique_for_seed_items() -> None:
    barcodes = [generate_internal_ean13(sequence) for sequence in range(1, 41)]
    assert len(set(barcodes)) == 40
    assert barcodes == [generate_internal_ean13(sequence) for sequence in range(1, 41)]
    for barcode in barcodes:
        assert barcode.startswith("200")
        assert len(barcode) == 13
        assert validate_ean(barcode) == barcode


@pytest.mark.parametrize(
    "sequence", [0, -1, 1_000_000_000, True, False, 1.0, "1", None, Decimal(1)]
)
def test_internal_generator_rejects_invalid_sequence(sequence: object) -> None:
    with pytest.raises(
        ValueError, match="^EAN sequence must be an integer between 1 and 999999999$"
    ):
        generate_internal_ean13(sequence)
````

tests/unit/test_config.py

````python
"""Test environment isolation, configuration validation, and secret handling."""

import os
import secrets
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in list(os.environ):
        if name.casefold() in Settings.model_fields:
            monkeypatch.delenv(name)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def secret_values() -> dict[str, str]:
    return {
        name: secrets.token_urlsafe(32)
        for name in ("bank_merchant_api_key", "webhook_secret", "secret_key")
    }


def test_defaults_and_masked_secrets(secret_values: dict[str, str]) -> None:
    settings = Settings(_env_file=None, **secret_values)
    assert settings.app_env == "development"
    assert settings.currency == "KZT"
    assert settings.timezone == "Asia/Almaty"
    assert settings.payment_ttl_seconds == 300
    assert settings.payment_expiry_grace_seconds == 30
    for value in secret_values.values():
        assert value not in repr(settings)
        assert value not in settings.model_dump_json()


def test_dotenv_and_environment_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, secret_values: dict[str, str]
) -> None:
    env_file = tmp_path / ".env"
    lines = [f"{name.upper()}={value}" for name, value in secret_values.items()]
    lines.extend(
        [
            "APP_ENV=test",
            "TIMEZONE=UTC",
            "PAYMENT_TTL_SECONDS=30",
            "BANK_DATABASE_URL=sqlite:///./bank.db",
            'MERCHANT_NAME="Учебный магазин"',
        ]
    )
    env_file.write_text("\n".join(lines), encoding="utf-8")
    settings = Settings(_env_file=env_file)
    assert settings.app_env == "test"
    assert settings.timezone == "UTC"
    assert settings.payment_ttl_seconds == 30
    assert not hasattr(settings, "bank_database_url")
    monkeypatch.setenv("PAYMENT_TTL_SECONDS", "45")
    assert Settings(_env_file=env_file).payment_ttl_seconds == 45


@pytest.mark.parametrize("field", ["bank_merchant_api_key", "webhook_secret", "secret_key"])
def test_missing_secret_is_rejected(field: str, secret_values: dict[str, str]) -> None:
    del secret_values[field]
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **secret_values)


@pytest.mark.parametrize("value", ["", "short", "x" * 32 + " ", "change-me-" + "x" * 32])
def test_invalid_secret_is_rejected_without_exposing_input(
    value: str, secret_values: dict[str, str]
) -> None:
    secret_values["secret_key"] = value
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, **secret_values)
    assert "input_value" not in str(error.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("app_env", "unknown"),
        ("currency", "USD"),
        ("timezone", "Unknown/City"),
        ("timezone", "/absolute/path"),
        ("payment_provider", "fake"),
        ("payment_ttl_seconds", 0),
        ("payment_ttl_seconds", -1),
        ("payment_ttl_seconds", 86401),
        ("payment_expiry_grace_seconds", -1),
        ("access_token_expire_minutes", 0),
        ("database_url", ""),
        ("bank_base_url", "ftp://localhost:8001"),
        ("bank_base_url", "not-a-url"),
        ("bank_base_url", "http://user:password@localhost:8001"),
        ("bank_base_url", "http://localhost:8001/api"),
        ("bank_base_url", "http://localhost:8001?key=value"),
        ("bank_base_url", "http://localhost:8001#fragment"),
    ],
)
def test_invalid_settings_are_rejected(
    field: str, value: str | int, secret_values: dict[str, str]
) -> None:
    data = {**secret_values, field: value}
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **data)


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:8001", "http://192.168.1.50:8001", "http://mock_bank:8001"]
)
def test_local_bank_urls_are_allowed(url: str, secret_values: dict[str, str]) -> None:
    settings = Settings(_env_file=None, bank_base_url=url, **secret_values)
    assert str(settings.bank_base_url).rstrip("/") == url


def test_short_demo_ttl_and_zero_grace_are_allowed(secret_values: dict[str, str]) -> None:
    settings = Settings(
        _env_file=None, payment_ttl_seconds=30, payment_expiry_grace_seconds=0, **secret_values
    )
    assert settings.payment_ttl_seconds == 30
    assert settings.payment_expiry_grace_seconds == 0


def test_production_is_enabled_with_valid_secrets(secret_values: dict[str, str]) -> None:
    assert Settings(_env_file=None, app_env="production", **secret_values).app_env == "production"
````

tests/unit/test_money.py

````python
"""Verify integer arithmetic, weight rounding, and strict domain inputs."""

from decimal import Decimal

import pytest

from app.core.enums import ProductUnit
from app.core.money import calculate_line_total


@pytest.mark.parametrize(
    ("price_minor", "quantity", "expected"),
    [(125000, 3, 375000), (1, 1, 1), (0, 5, 0)],
)
def test_piece_total(price_minor: int, quantity: int, expected: int) -> None:
    result = calculate_line_total(ProductUnit.PIECE, price_minor, quantity)
    assert result == expected
    assert type(result) is int


@pytest.mark.parametrize(
    ("price_minor", "grams", "expected"),
    [
        (1, 499, 0),
        (1, 500, 1),
        (1, 501, 1),
        (1, 1499, 1),
        (1, 1500, 2),
        (1, 1501, 2),
        (499, 1, 0),
        (500, 1, 1),
        (501, 1, 1),
        (125000, 333, 41625),
        (129999, 333, 43290),
        (125000, 1000, 125000),
        (125000, 1500, 187500),
        (0, 500, 0),
    ],
)
def test_weight_total_rounds_half_up(price_minor: int, grams: int, expected: int) -> None:
    result = calculate_line_total(ProductUnit.KG, price_minor, grams)
    assert result == expected
    assert type(result) is int


def test_large_integer_prices_remain_exact() -> None:
    price_minor = 2**53 + 1
    assert calculate_line_total(ProductUnit.PIECE, price_minor, 3) == 27021597764222979
    assert calculate_line_total(ProductUnit.KG, price_minor, 1000) == price_minor
    assert calculate_line_total(ProductUnit.KG, price_minor, 500) == 4503599627370497


def test_repeated_scans_must_recalculate_the_combined_quantity() -> None:
    combined = calculate_line_total(ProductUnit.KG, 1, 500 + 500)
    separate = calculate_line_total(ProductUnit.KG, 1, 500) * 2
    assert combined == 1
    assert separate == 2


@pytest.mark.parametrize("unit", list(ProductUnit))
@pytest.mark.parametrize("price_minor", [-1, True, False, 100.0, "100", Decimal("100"), None])
def test_invalid_prices_are_rejected(unit: ProductUnit, price_minor: object) -> None:
    with pytest.raises(ValueError, match="price_minor"):
        calculate_line_total(unit, price_minor, 1)


@pytest.mark.parametrize("unit", list(ProductUnit))
@pytest.mark.parametrize("quantity", [0, -1, True, False, 1.0, "1", Decimal("1"), None])
def test_invalid_quantities_are_rejected(unit: ProductUnit, quantity: object) -> None:
    with pytest.raises(ValueError, match="quantity"):
        calculate_line_total(unit, 100, quantity)


@pytest.mark.parametrize("unit", ["PIECE", "KG", "LITRE", "", None, 1])
def test_units_require_an_explicit_enum(unit: object) -> None:
    with pytest.raises(ValueError, match="unit"):
        calculate_line_total(unit, 100, 1)


def test_unit_values_are_stable_for_storage() -> None:
    assert str(ProductUnit.PIECE) == "PIECE"
    assert str(ProductUnit.KG) == "KG"
    with pytest.raises(ValueError):
        ProductUnit("LITRE")
````

tests/unit/test_setup_env.py

````python
"""Bootstrap configuration must preserve previous values and generate distinct keys."""

from pathlib import Path

from app.core.config import Settings
from app.setup_env import PROJECT_ROOT, SECRET_NAMES, create_env


def test_create_and_preserve_configuration(tmp_path: Path) -> None:
    target = tmp_path / ".env"
    assert create_env(target, PROJECT_ROOT / ".env.example")
    original = target.read_text(encoding="utf-8")
    values = dict(
        line.split("=", 1)
        for line in original.splitlines()
        if "=" in line and not line.startswith("#")
    )
    assert len({values[name] for name in SECRET_NAMES}) == 3
    settings = Settings(_env_file=target)
    assert settings.currency == "KZT"
    assert not create_env(target, PROJECT_ROOT / ".env.example")
    assert target.read_text(encoding="utf-8") == original
````
