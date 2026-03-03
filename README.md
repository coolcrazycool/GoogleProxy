# Google API Proxy

FastAPI-прокси для работы с Google Sheets и Google Drive API.
Несколько пользователей, каждый со своим service account — прокси управляет токенами автоматически.

---

## Быстрый старт

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
# Swagger UI: http://localhost:9000/docs
```

---

## Аутентификация

Все эндпоинты (кроме `/auth/register`) требуют заголовок:

```
Authorization: Bearer <internal_token>
```

`internal_token` — стабильный UUID, выдаётся при регистрации и **никогда не меняется** для одного и того же service account.

---

## Эндпоинты

### Содержание

- [POST /auth/register](#post-authregister)
- [GET /auth/google-token](#get-authgoogle-token)
- [GET /drive/spreadsheets](#get-drivespreadsheets)
- [GET /drive/spreadsheets/by-name](#get-drivespreadsheetsBy-name)
- [GET /sheets/{id}/download](#get-sheetsiddownload)
- [GET /sheets/{id}](#get-sheetsid)
- [GET /sheets/{id}/sheets](#get-sheetsidsheets)
- [GET /sheets/{id}/read](#get-sheetsidread)
- [PUT /sheets/{id}/cell](#put-sheetsidcell)
- [PUT /sheets/{id}/cells/bulk](#put-sheetsidcellsbulk)
- [PUT /sheets/{id}/rows](#put-sheetsidrows)
- [PUT /sheets/{id}/format](#put-sheetsidformat)
- [GET /calendar/events/today](#get-calendarevendstoday)
- [GET /calendar/events/week](#get-calendarevendsweek)
- [GET /calendar/events/next](#get-calendareventsnext)
- [GET /calendar/freebusy](#get-calendarfreebusy)
- [POST /calendar/events](#post-calendarevents)
- [PUT /calendar/events/{id}](#put-calendareventid)
- [DELETE /calendar/events/{id}](#delete-calendareventid)

---

## Auth

### POST /auth/register

Регистрация service account. Возвращает стабильный `internal_token`.
Повторная регистрация **того же** account вернёт тот же токен.

**Тело запроса:**

| Поле | Тип | Описание |
|---|---|---|
| `account_json_b64` | `string` | Base64-кодированный JSON service account от Google |

**Как получить `account_json_b64`:**

```python
import base64, json

with open("service_account.json") as f:
    account_json = json.load(f)

account_json_b64 = base64.b64encode(json.dumps(account_json).encode()).decode()
```

**Пример запроса:**

```bash
curl -X POST http://localhost:9000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"account_json_b64": "<base64-строка>"}'
```

**Ответ `200`:**

```json
{
  "internal_token": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "message": "Registered successfully"
}
```

**Ошибки:**

| Код | Причина |
|---|---|
| `400` | Невалидный base64 или не JSON внутри |

---

### GET /auth/google-token

Возвращает актуальный Google access token для текущего пользователя.
Если токен протух — перевыпускается автоматически. Новый токен не запрашивается без пользовательского вызова.

**Заголовки:** `Authorization: Bearer <internal_token>`

**Пример запроса:**

```bash
curl http://localhost:9000/auth/google-token \
  -H "Authorization: Bearer a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

**Ответ `200`:**

```json
{
  "access_token": "ya29.a0AfB_byC...",
  "expires_at": "2024-03-15T12:00:00+00:00",
  "token_type": "Bearer"
}
```

**Ошибки:**

| Код | Причина |
|---|---|
| `401` | Отсутствует заголовок или `internal_token` не зарегистрирован |

---

## Drive

### GET /drive/spreadsheets

Список всех Google Spreadsheets, доступных service account на Drive.

**Заголовки:** `Authorization: Bearer <internal_token>`

**Пример запроса:**

```bash
curl http://localhost:9000/drive/spreadsheets \
  -H "Authorization: Bearer <internal_token>"
```

**Ответ `200`:**

```json
[
  {
    "id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms",
    "name": "Бюджет 2024",
    "modified_time": "2024-03-01T10:30:00Z"
  },
  {
    "id": "2CyiNWt1YSB6gONLwCeCAbkhnVVrqumct85PhWF3vqnt",
    "name": "Отчёт Q1",
    "modified_time": "2024-02-15T08:00:00Z"
  }
]
```

---

### GET /drive/spreadsheets/by-name

Найти таблицу по точному имени. Возвращает первое совпадение.

**Заголовки:** `Authorization: Bearer <internal_token>`

**Query-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `name` | `string` | Точное название таблицы |

**Пример запроса:**

```bash
curl "http://localhost:9000/drive/spreadsheets/by-name?name=Бюджет+2024" \
  -H "Authorization: Bearer <internal_token>"
```

**Ответ `200`:**

```json
{
  "id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms",
  "name": "Бюджет 2024"
}
```

**Ошибки:**

| Код | Причина |
|---|---|
| `404` | Таблица с таким именем не найдена |

---

## Sheets

> Во всех эндпоинтах `{spreadsheet_id}` — ID таблицы из URL Google Sheets:
> `https://docs.google.com/spreadsheets/d/**{spreadsheet_id}**/edit`

---

### GET /sheets/{spreadsheet_id}/download

Скачать таблицу в указанном формате.

**Заголовки:** `Authorization: Bearer <internal_token>`

**Query-параметры:**

| Параметр | Тип | По умолчанию | Варианты |
|---|---|---|---|
| `format` | `string` | `xlsx` | `xlsx`, `csv`, `pdf`, `ods`, `tsv` |

**Пример запроса:**

```bash
# Скачать как Excel
curl "http://localhost:9000/sheets/1BxiMVs0.../download?format=xlsx" \
  -H "Authorization: Bearer <internal_token>" \
  -o report.xlsx

# Скачать как CSV
curl "http://localhost:9000/sheets/1BxiMVs0.../download?format=csv" \
  -H "Authorization: Bearer <internal_token>" \
  -o report.csv
```

**Ответ `200`:** бинарный файл с заголовком `Content-Disposition: attachment; filename="<id>.xlsx"`

**Ошибки:**

| Код | Причина |
|---|---|
| `400` | Неподдерживаемый формат |

---

### GET /sheets/{spreadsheet_id}

Прочитать всю таблицу целиком — все листы, все данные.

**Заголовки:** `Authorization: Bearer <internal_token>`

**Пример запроса:**

```bash
curl http://localhost:9000/sheets/1BxiMVs0... \
  -H "Authorization: Bearer <internal_token>"
```

**Ответ `200`:**

```json
{
  "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms",
  "title": "Бюджет 2024",
  "sheets": [
    {
      "sheet_name": "Январь",
      "values": [
        ["Статья", "Сумма", "Категория"],
        ["Аренда", "50000", "Расходы"],
        ["Зарплата", "120000", "Доходы"]
      ]
    },
    {
      "sheet_name": "Февраль",
      "values": [
        ["Статья", "Сумма", "Категория"],
        ["Аренда", "50000", "Расходы"]
      ]
    }
  ]
}
```

> Пустые ячейки в конце строки Google Sheets обрезает — строки могут быть разной длины.

---

### GET /sheets/{spreadsheet_id}/sheets

Получить список листов таблицы с их идентификаторами.

**Заголовки:** `Authorization: Bearer <internal_token>`

**Пример запроса:**

```bash
curl http://localhost:9000/sheets/1BxiMVs0.../sheets \
  -H "Authorization: Bearer <internal_token>"
```

**Ответ `200`:**

```json
[
  {"sheet_id": 0,      "title": "Январь",  "index": 0},
  {"sheet_id": 123456, "title": "Февраль", "index": 1},
  {"sheet_id": 789012, "title": "Итого",   "index": 2}
]
```

| Поле | Описание |
|---|---|
| `sheet_id` | Внутренний числовой ID листа (нужен для форматирования) |
| `title` | Название вкладки |
| `index` | Порядковый номер (0-based) |

---

### GET /sheets/{spreadsheet_id}/read

Прочитать данные конкретного листа.

**Заголовки:** `Authorization: Bearer <internal_token>`

**Query-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `sheet_name` | `string` | Название листа (вкладки) |

**Пример запроса:**

```bash
curl "http://localhost:9000/sheets/1BxiMVs0.../read?sheet_name=Январь" \
  -H "Authorization: Bearer <internal_token>"
```

**Ответ `200`:**

```json
{
  "sheet_name": "Январь",
  "values": [
    ["Статья",  "Сумма",  "Категория"],
    ["Аренда",  "50000",  "Расходы"],
    ["Зарплата","120000", "Доходы"]
  ]
}
```

**Ошибки:**

| Код | Причина |
|---|---|
| `404` | Лист с таким именем не существует |

---

### PUT /sheets/{spreadsheet_id}/cell

Записать значение в одну ячейку.

**Заголовки:** `Authorization: Bearer <internal_token>`, `Content-Type: application/json`

**Тело запроса:**

| Поле | Тип | Описание |
|---|---|---|
| `sheet_name` | `string` | Название листа |
| `row` | `int` | Номер строки, **начиная с 1** |
| `col` | `int` | Номер столбца, **начиная с 1** (1=A, 2=B, 3=C…) |
| `value` | `any` | Значение: строка, число, `null` |

**Пример запроса:**

```bash
# Записать "Привет" в ячейку B3 (строка 3, столбец 2)
curl -X PUT http://localhost:9000/sheets/1BxiMVs0.../cell \
  -H "Authorization: Bearer <internal_token>" \
  -H "Content-Type: application/json" \
  -d '{"sheet_name": "Январь", "row": 3, "col": 2, "value": "Привет"}'
```

**Ответ `200`:**

```json
{
  "updated_range": "Январь!B3",
  "updated_rows": 1,
  "updated_cells": 1
}
```

---

### PUT /sheets/{spreadsheet_id}/cells/bulk

Записать несколько диапазонов за один запрос к Google API (`batchUpdate`).
Используйте вместо множества одиночных записей — значительно быстрее.

**Заголовки:** `Authorization: Bearer <internal_token>`, `Content-Type: application/json`

**Тело запроса:**

```json
{
  "updates": [
    {
      "sheet_name": "Январь",
      "range": "A1:C1",
      "values": [["Статья", "Сумма", "Категория"]]
    },
    {
      "sheet_name": "Январь",
      "range": "A2:C4",
      "values": [
        ["Аренда",   50000,  "Расходы"],
        ["Зарплата", 120000, "Доходы"],
        ["Налоги",   15000,  "Расходы"]
      ]
    },
    {
      "sheet_name": "Февраль",
      "range": "D5",
      "values": [["одна ячейка"]]
    }
  ]
}
```

**Структура `updates[i]`:**

| Поле | Тип | Описание |
|---|---|---|
| `sheet_name` | `string` | Название листа |
| `range` | `string` | Диапазон в A1-нотации **без имени листа** |
| `values` | `array[][]` | Двумерный массив: `[строка][ячейка]`. Одна ячейка: `[["значение"]]` |

**Примеры диапазонов:**

| `range` | Что означает |
|---|---|
| `"A1"` | Одна ячейка A1 |
| `"B2:D2"` | Одна строка, столбцы B–D |
| `"A1:C3"` | Прямоугольник 3×3, начиная с A1 |
| `"A:A"` | Весь столбец A |

**Пример запроса:**

```bash
curl -X PUT http://localhost:9000/sheets/1BxiMVs0.../cells/bulk \
  -H "Authorization: Bearer <internal_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "updates": [
      {"sheet_name": "Лист1", "range": "A1:B1", "values": [["Имя", "Возраст"]]},
      {"sheet_name": "Лист1", "range": "A2:B3", "values": [["Алиса", 30], ["Боб", 25]]}
    ]
  }'
```

**Ответ `200`:**

```json
{
  "total_updated_rows": 3,
  "total_updated_cells": 6,
  "responses": 2
}
```

---

### PUT /sheets/{spreadsheet_id}/rows

Записать целые строки начиная с указанной позиции. Запись всегда начинается с колонки **A**.

**Заголовки:** `Authorization: Bearer <internal_token>`, `Content-Type: application/json`

**Тело запроса:**

| Поле | Тип | Описание |
|---|---|---|
| `sheet_name` | `string` | Название листа |
| `start_row` | `int` | Строка, с которой начинать запись (**начиная с 1**) |
| `rows` | `array[][]` | Массив строк; каждая строка — массив значений |

**Пример запроса:**

```bash
# Записать 3 строки начиная со строки 2
curl -X PUT http://localhost:9000/sheets/1BxiMVs0.../rows \
  -H "Authorization: Bearer <internal_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "sheet_name": "Сотрудники",
    "start_row": 2,
    "rows": [
      ["Алиса", "Иванова", "alice@company.com", "Разработчик"],
      ["Боб",   "Петров",  "bob@company.com",   "Дизайнер"],
      ["Карл",  "Сидоров", "carl@company.com",  "Менеджер"]
    ]
  }'
```

Результат в таблице:

```
Строка 2: Алиса | Иванова | alice@company.com | Разработчик
Строка 3: Боб   | Петров  | bob@company.com   | Дизайнер
Строка 4: Карл  | Сидоров | carl@company.com  | Менеджер
```

**Ответ `200`:**

```json
{
  "updated_range": "Сотрудники!A2:D4",
  "updated_rows": 3,
  "updated_cells": 12
}
```

---

### PUT /sheets/{spreadsheet_id}/format

Применить форматирование (цвет фона, цвет текста, жирность) к диапазонам ячеек.

**Заголовки:** `Authorization: Bearer <internal_token>`, `Content-Type: application/json`

**Тело запроса:**

```json
{
  "ranges": [
    {
      "sheet_name": "Лист1",
      "start_row": 1,
      "end_row": 1,
      "start_col": 1,
      "end_col": 5,
      "background_color": {"red": 0.2, "green": 0.5, "blue": 0.9},
      "text_color": {"red": 1.0, "green": 1.0, "blue": 1.0},
      "bold": true
    }
  ]
}
```

**Структура `ranges[i]`:**

| Поле | Тип | Описание |
|---|---|---|
| `sheet_name` | `string` | Название листа |
| `start_row` | `int?` | Начальная строка, **1-based**. `null` = с начала листа |
| `end_row` | `int?` | Конечная строка включительно, **1-based**. `null` = до конца |
| `start_col` | `int?` | Начальный столбец, **1-based** (1=A). `null` = с начала |
| `end_col` | `int?` | Конечный столбец включительно. `null` = до конца |
| `background_color` | `Color?` | Цвет фона ячейки |
| `text_color` | `Color?` | Цвет текста |
| `bold` | `bool?` | Жирный шрифт |

**Структура `Color`:**

| Поле | Тип | Диапазон | Описание |
|---|---|---|---|
| `red` | `float` | `0.0 – 1.0` | Красный канал |
| `green` | `float` | `0.0 – 1.0` | Зелёный канал |
| `blue` | `float` | `0.0 – 1.0` | Синий канал |

**Примеры цветов:**

| Цвет | `red` | `green` | `blue` |
|---|---|---|---|
| Красный | `1.0` | `0.0` | `0.0` |
| Зелёный | `0.0` | `1.0` | `0.0` |
| Синий | `0.0` | `0.0` | `1.0` |
| Жёлтый | `1.0` | `1.0` | `0.0` |
| Белый | `1.0` | `1.0` | `1.0` |
| Чёрный | `0.0` | `0.0` | `0.0` |
| Серый | `0.5` | `0.5` | `0.5` |

**Примеры ranges:**

```json5
// Вся строка 1 — синий фон, белый жирный текст (шапка таблицы)
{"sheet_name": "Лист1", "start_row": 1, "end_row": 1,
 "background_color": {"red": 0.2, "green": 0.4, "blue": 0.8},
 "text_color": {"red": 1, "green": 1, "blue": 1}, "bold": true}

// Весь столбец A — светло-серый фон
{"sheet_name": "Лист1", "start_col": 1, "end_col": 1,
 "background_color": {"red": 0.9, "green": 0.9, "blue": 0.9}}

// Конкретная ячейка C3 — красный фон
{"sheet_name": "Лист1", "start_row": 3, "end_row": 3, "start_col": 3, "end_col": 3,
 "background_color": {"red": 1.0, "green": 0.0, "blue": 0.0}}

// Диапазон B2:D5 — только жирный, без смены цвета
{"sheet_name": "Лист1", "start_row": 2, "end_row": 5,
 "start_col": 2, "end_col": 4, "bold": true}
```

**Пример запроса — оформление таблицы с заголовком:**

```bash
curl -X PUT http://localhost:9000/sheets/1BxiMVs0.../format \
  -H "Authorization: Bearer <internal_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "ranges": [
      {
        "sheet_name": "Отчёт",
        "start_row": 1, "end_row": 1,
        "background_color": {"red": 0.13, "green": 0.46, "blue": 0.71},
        "text_color": {"red": 1.0, "green": 1.0, "blue": 1.0},
        "bold": true
      },
      {
        "sheet_name": "Отчёт",
        "start_row": 2, "end_row": 100,
        "start_col": 3, "end_col": 3,
        "background_color": {"red": 0.95, "green": 0.95, "blue": 0.95}
      }
    ]
  }'
```

**Ответ `200`:**

```json
{
  "applied_ranges": 2
}
```

---

## Полный пример на Python

```python
import base64, json, requests

BASE_URL = "http://localhost:9000"

# 1. Подготовить base64 от service account
with open("service_account.json") as f:
    account_json = json.load(f)
b64 = base64.b64encode(json.dumps(account_json).encode()).decode()

# 2. Зарегистрироваться — получить internal_token
r = requests.post(f"{BASE_URL}/auth/register", json={"account_json_b64": b64})
token = r.json()["internal_token"]
headers = {"Authorization": f"Bearer {token}"}

# 3. Найти таблицу по имени
r = requests.get(f"{BASE_URL}/drive/spreadsheets/by-name",
                 params={"name": "Мой отчёт"}, headers=headers)
sid = r.json()["id"]

# 4. Прочитать лист
r = requests.get(f"{BASE_URL}/sheets/{sid}/read",
                 params={"sheet_name": "Sheet1"}, headers=headers)
print(r.json()["values"])

# 5. Записать заголовок и данные bulk-запросом
requests.put(f"{BASE_URL}/sheets/{sid}/cells/bulk", headers=headers, json={
    "updates": [
        {"sheet_name": "Sheet1", "range": "A1:C1",
         "values": [["Имя", "Сумма", "Статус"]]},
        {"sheet_name": "Sheet1", "range": "A2:C3",
         "values": [["Алиса", 1000, "OK"], ["Боб", 2000, "OK"]]},
    ]
})

# 6. Покрасить заголовок
requests.put(f"{BASE_URL}/sheets/{sid}/format", headers=headers, json={
    "ranges": [{
        "sheet_name": "Sheet1",
        "start_row": 1, "end_row": 1,
        "background_color": {"red": 0.2, "green": 0.6, "blue": 0.2},
        "text_color": {"red": 1.0, "green": 1.0, "blue": 1.0},
        "bold": True
    }]
})

# 7. Скачать как Excel
r = requests.get(f"{BASE_URL}/sheets/{sid}/download?format=xlsx", headers=headers)
with open("report.xlsx", "wb") as f:
    f.write(r.content)
```

---

---

## Calendar

> Для работы с Calendar API service account должен быть приглашён в нужный календарь как редактор, либо использоваться **domain-wide delegation** в Google Workspace.
> Все эндпоинты требуют заголовок `Authorization: Bearer <internal_token>`.

---

### GET /calendar/events/today

Получить все события на **сегодня** (по UTC).

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `calendar_id` | `string` | `primary` | ID календаря |

**Пример:**

```bash
curl "http://localhost:9000/calendar/events/today" \
  -H "Authorization: Bearer <internal_token>"
```

**Ответ `200`:**

```json
[
  {
    "id": "abc123xyz",
    "summary": "Ежедневный стендап",
    "description": "Синхронизация команды",
    "location": "Zoom",
    "start": "2024-06-15T10:00:00+03:00",
    "end": "2024-06-15T10:30:00+03:00",
    "status": "confirmed",
    "html_link": "https://calendar.google.com/event?id=abc123xyz",
    "attendees": [{"email": "alice@example.com", "responseStatus": "accepted"}],
    "recurrence": null,
    "creator": {"email": "me@example.com"}
  }
]
```

---

### GET /calendar/events/week

Получить события на **ближайшие 7 дней** (от начала сегодняшнего дня UTC).

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `calendar_id` | `string` | `primary` | ID календаря |

**Пример:**

```bash
curl "http://localhost:9000/calendar/events/week?calendar_id=primary" \
  -H "Authorization: Bearer <internal_token>"
```

**Ответ `200`:** массив объектов `CalendarEvent` (та же структура, что у `/events/today`).

---

### GET /calendar/events/next

**"Сколько времени до следующей встречи?"** — возвращает ближайшее предстоящее событие и количество минут до его начала. Горизонт поиска — 24 часа.

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `calendar_id` | `string` | `primary` | ID календаря |

**Пример:**

```bash
curl "http://localhost:9000/calendar/events/next" \
  -H "Authorization: Bearer <internal_token>"
```

**Ответ `200` — встреча найдена:**

```json
{
  "event": {
    "id": "abc123xyz",
    "summary": "Встреча с клиентом",
    "start": "2024-06-15T14:00:00+03:00",
    "end": "2024-06-15T15:00:00+03:00",
    "status": "confirmed"
  },
  "minutes_until": 47,
  "message": "Следующая встреча через 47 мин."
}
```

**Ответ `200` — встреч нет:**

```json
{
  "event": null,
  "minutes_until": null,
  "message": "Нет предстоящих встреч в ближайшие 24 часа"
}
```

---

### GET /calendar/freebusy

Найти **свободные временные слоты** в заданном интервале. Использует Google Calendar Freebusy API.

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `time_min` | `string` | — | Начало интервала, ISO-8601 с таймзоной |
| `time_max` | `string` | — | Конец интервала, ISO-8601 с таймзоной |
| `calendar_id` | `string` | `primary` | ID календаря |
| `min_duration` | `int` | `30` | Минимальная длина свободного слота, в минутах |

**Пример:**

```bash
curl "http://localhost:9000/calendar/freebusy?\
time_min=2024-06-15T09:00:00%2B03:00&\
time_max=2024-06-15T18:00:00%2B03:00&\
min_duration=30" \
  -H "Authorization: Bearer <internal_token>"
```

**Ответ `200`:**

```json
{
  "time_min": "2024-06-15T09:00:00+03:00",
  "time_max": "2024-06-15T18:00:00+03:00",
  "free_slots": [
    {
      "start": "2024-06-15T09:00:00+03:00",
      "end": "2024-06-15T10:00:00+03:00",
      "duration_minutes": 60
    },
    {
      "start": "2024-06-15T11:30:00+03:00",
      "end": "2024-06-15T14:00:00+03:00",
      "duration_minutes": 150
    }
  ]
}
```

---

### POST /calendar/events

Создать событие в календаре. Если указать поле `recurrence` — создаётся **повторяющееся событие**.

**Тело запроса:**

| Поле | Тип | Обяз. | Описание |
|---|---|---|---|
| `summary` | `string` | ✓ | Название события |
| `start` | `string` | ✓ | Начало, ISO-8601 с таймзоной |
| `end` | `string` | ✓ | Конец, ISO-8601 с таймзоной |
| `timezone` | `string` | | IANA-таймзона, напр. `Europe/Moscow` (по умолч. `UTC`) |
| `description` | `string` | | Описание |
| `location` | `string` | | Место проведения |
| `attendees` | `array` | | Список участников: `[{"email": "...", "optional": false}]` |
| `recurrence` | `object` | | Правило повторения (см. ниже) |
| `calendar_id` | `string` | | ID календаря (по умолч. `primary`) |

**Структура `recurrence`:**

| Поле | Тип | Описание |
|---|---|---|
| `frequency` | `string` | `DAILY`, `WEEKLY`, `MONTHLY`, `YEARLY` |
| `interval` | `int` | Повторять каждые N единиц (по умолч. `1`) |
| `count` | `int?` | Количество повторений |
| `until` | `string?` | Дата окончания `YYYYMMDDTHHMMSSZ` |
| `by_day` | `array?` | Дни недели: `["MO","WE","FR"]` |

**Пример — одиночное событие:**

```bash
curl -X POST http://localhost:9000/calendar/events \
  -H "Authorization: Bearer <internal_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "summary": "Встреча с клиентом",
    "start": "2024-06-20T14:00:00+03:00",
    "end": "2024-06-20T15:00:00+03:00",
    "timezone": "Europe/Moscow",
    "location": "Офис, переговорная 3",
    "attendees": [{"email": "client@example.com"}]
  }'
```

**Пример — еженедельное повторяющееся событие (пн и ср, 10 раз):**

```bash
curl -X POST http://localhost:9000/calendar/events \
  -H "Authorization: Bearer <internal_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "summary": "Еженедельный стендап",
    "start": "2024-06-17T10:00:00+03:00",
    "end": "2024-06-17T10:30:00+03:00",
    "timezone": "Europe/Moscow",
    "recurrence": {
      "frequency": "WEEKLY",
      "interval": 1,
      "by_day": ["MO", "WE"],
      "count": 10
    }
  }'
```

**Ответ `201`:** объект `CalendarEvent` созданного события.

---

### PUT /calendar/events/{event_id}

Обновить существующее событие. Передаются только изменяемые поля; остальные сохраняются.

**Path-параметры:** `event_id` — ID события из Google Calendar.

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `calendar_id` | `string` | `primary` | ID календаря |

**Тело запроса** (все поля опциональны):

| Поле | Тип | Описание |
|---|---|---|
| `summary` | `string?` | Новое название |
| `description` | `string?` | Новое описание |
| `location` | `string?` | Новое место |
| `start` | `string?` | Новое начало, ISO-8601 |
| `end` | `string?` | Новый конец, ISO-8601 |
| `timezone` | `string?` | IANA-таймзона |
| `attendees` | `array?` | Новый список участников |
| `recurrence` | `object?` | Новое правило повторения |

**Пример:**

```bash
curl -X PUT "http://localhost:9000/calendar/events/abc123xyz?calendar_id=primary" \
  -H "Authorization: Bearer <internal_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "summary": "Встреча с клиентом (перенесена)",
    "start": "2024-06-20T16:00:00+03:00",
    "end": "2024-06-20T17:00:00+03:00"
  }'
```

**Ответ `200`:** обновлённый объект `CalendarEvent`.

**Ошибки:**

| Код | Причина |
|---|---|
| `404` | Событие не найдено |

---

### DELETE /calendar/events/{event_id}

Удалить событие из календаря.

**Path-параметры:** `event_id` — ID события.

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `calendar_id` | `string` | `primary` | ID календаря |

**Пример:**

```bash
curl -X DELETE "http://localhost:9000/calendar/events/abc123xyz?calendar_id=primary" \
  -H "Authorization: Bearer <internal_token>"
```

**Ответ `200`:**

```json
{
  "message": "Event 'abc123xyz' deleted"
}
```

**Ошибки:**

| Код | Причина |
|---|---|
| `404` | Событие не найдено |
| `410` | Событие уже удалено |

---

## Полный пример на Python — Calendar

```python
import base64, json, requests
from datetime import datetime, timedelta, timezone

BASE_URL = "http://localhost:9000"

# 1. Зарегистрироваться
with open("service_account.json") as f:
    account_json = json.load(f)
b64 = base64.b64encode(json.dumps(account_json).encode()).decode()
r = requests.post(f"{BASE_URL}/auth/register", json={"account_json_b64": b64})
token = r.json()["internal_token"]
headers = {"Authorization": f"Bearer {token}"}

# 2. События на сегодня
today = requests.get(f"{BASE_URL}/calendar/events/today", headers=headers).json()
print(f"Сегодня {len(today)} событий")

# 3. Сколько до следующей встречи
nxt = requests.get(f"{BASE_URL}/calendar/events/next", headers=headers).json()
print(nxt["message"])

# 4. Свободные слоты сегодня
now = datetime.now(timezone.utc)
slots = requests.get(f"{BASE_URL}/calendar/freebusy", headers=headers, params={
    "time_min": now.replace(hour=9, minute=0, second=0).isoformat(),
    "time_max": now.replace(hour=18, minute=0, second=0).isoformat(),
    "min_duration": 60,
}).json()
print(f"Свободных часовых слотов: {len(slots['free_slots'])}")

# 5. Создать одиночное событие
start = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0).isoformat()
end   = (now + timedelta(days=1)).replace(hour=11, minute=0, second=0).isoformat()
event = requests.post(f"{BASE_URL}/calendar/events", headers=headers, json={
    "summary": "Демо-встреча",
    "start": start,
    "end": end,
    "timezone": "Europe/Moscow",
    "attendees": [{"email": "client@example.com"}],
}).json()
event_id = event["id"]

# 6. Создать повторяющееся событие (ежедневный стендап, пн–пт, 20 раз)
requests.post(f"{BASE_URL}/calendar/events", headers=headers, json={
    "summary": "Стендап",
    "start": start,
    "end": (now + timedelta(days=1)).replace(hour=10, minute=15, second=0).isoformat(),
    "recurrence": {
        "frequency": "WEEKLY",
        "interval": 1,
        "by_day": ["MO", "TU", "WE", "TH", "FR"],
        "count": 20,
    },
})

# 7. Обновить событие
requests.put(f"{BASE_URL}/calendar/events/{event_id}", headers=headers, json={
    "summary": "Демо-встреча (подтверждена)",
    "location": "Zoom link: https://zoom.us/j/...",
})

# 8. Удалить событие
requests.delete(f"{BASE_URL}/calendar/events/{event_id}", headers=headers)
print("Событие удалено")
```

---

## Запуск тестов

```bash
pytest tests/ -v

# С покрытием
pytest tests/ --cov=app --cov-report=term-missing
```

## Переменные окружения

Скопировать `.env.example` в `.env` и при необходимости изменить:

```env
DATA_DIR=./data       # Папка для хранения internal_token → account_json
TOKENS_FILE=tokens.json
```
