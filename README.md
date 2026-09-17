# Google API Proxy

Python-сервис с единым REST API для Google Sheets, Drive и Calendar. Клиент получает внутренний токен, а прокси хранит настройки service account и обновляет Google access token по мере необходимости.

**Стек:** Python, FastAPI, Pydantic, Google API Client, pytest, Docker.

## Задача

Вынести повторяющуюся работу с Google API из клиентских скриптов: авторизацию, обновление токенов, чтение и запись таблиц, поиск файлов и операции с календарём. Несколько service accounts могут использовать один экземпляр сервиса.

## Что реализовано

- Регистрация service account и выдача стабильного UUID-токена для идентичного JSON аккаунта.
- Кеширование Google credentials и обновление перед истечением срока действия.
- Чтение таблиц, запись ячеек и диапазонов, форматирование, экспорт файлов.
- Поиск таблиц в Drive; чтение, создание, изменение и удаление событий Calendar, поиск свободных интервалов.
- Разделение HTTP-маршрутов, моделей, сервисов Google API и управления токенами.
- Тесты HTTP API и менеджера токенов с подменой внешних вызовов.

## Запуск

### Локально

Ориентир окружения — Python 3.12, как в Dockerfile.

```bash
git clone https://github.com/coolcrazycool/GoogleProxy.git
cd GoogleProxy
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 9000
```

Открыть [Swagger UI](http://localhost:9000/docs). Проверка доступности:

```bash
curl --fail http://localhost:9000/health
```

Ответ: `{"status":"ok"}`. Для этой проверки Google credentials не нужны.

### Docker Compose

Compose использует внешнюю сеть `openclaw_google_api`. Перед первым запуском создайте её, если она ещё не существует:

```bash
docker network inspect openclaw_google_api >/dev/null 2>&1 || docker network create openclaw_google_api
mkdir -p data
docker compose up --build -d
```

На Linux каталог `data` должен быть доступен для записи UID `1001`, под которым работает контейнер. Порт по умолчанию — `9000`; изменить его можно через `HOST_PORT`. Настройки хранилища: `DATA_DIR` и `TOKENS_FILE` (по умолчанию `./data/tokens.json` при локальном запуске).

### Подключение Google

1. Подготовьте service account JSON, включите необходимые Google API и предоставьте аккаунту доступ к нужной таблице или календарю.
2. Передайте JSON, закодированный в base64, в `POST /auth/register` в поле `account_json_b64`.
3. Используйте полученный `internal_token` в заголовке `Authorization: Bearer ...`.

Регистрация сохраняет JSON, но не проверяет доступ к Google. Ошибки credentials или прав могут появиться при первом обращении к внешнему API. Base64 — кодирование, а не шифрование; credentials следует передавать только локально или по защищённому соединению.

## Пример результата

После регистрации задайте `INTERNAL_TOKEN` и `SPREADSHEET_ID` в окружении. В примере читается существующий лист `Sheet1`:

```bash
curl --fail --get "http://localhost:9000/sheets/$SPREADSHEET_ID/read" \
  -H "Authorization: Bearer $INTERNAL_TOKEN" \
  --data-urlencode 'sheet_name=Sheet1'
```

Иллюстративный ответ для таблицы из двух строк, а не результат опубликованного замера:

```json
{
  "sheet_name": "Sheet1",
  "values": [["Task", "Status"], ["Prepare report", "Done"]]
}
```

Остальные запросы и модели: [справочник API](docs/API.md) и Swagger UI запущенного сервиса.

## Ограничения

- Это сервис для доверенного окружения. Открытая регистрация, отсутствие ротации внутренних токенов и rate limiting требуют доработки перед публичным размещением.
- Service account JSON и внутренние токены хранятся на диске без шифрования. Не публикуйте каталог `data` и ограничьте доступ к нему.
- JSON-хранилище использует блокировку только внутри процесса и неатомарную запись; несколько worker-процессов или реплик с общим файлом не поддерживаются надёжно.
- Зависимости заданы нижними границами версий, без lock-файла.
- Тесты с mock-объектами не подтверждают реальные права service account, квоты и доступность Google API.

## Мой вклад

Инженерная часть, представленная в репозитории: REST-обёртка над Google API, менеджер токенов с дисковым хранением и кешем, модели запросов, контейнеризация и тестовые сценарии. Внешние API, OAuth-библиотеки и веб-фреймворк используются как готовые зависимости. Проект не заявляет собственную реализацию OAuth или подтверждённую production-нагрузку.

## Проверка

В активированном виртуальном окружении:

```bash
python -m pytest -q
```

Тесты используют искусственные credentials и подменяют обращения к Google. Для проверки реальной интеграции нужен отдельный service account и тестовые ресурсы.
