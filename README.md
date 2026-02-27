# Farmers Markets CLI

Учебное консольное приложение на Python для работы с данными фермерских рынков из CSV-файла.
Интерфейс — REPL (ввод команд в консоли).

## Возможности

- Загрузка рынков из `farmers_markets.csv` (CSV → память).
- Регистрация и вход пользователей (пароли хэшируются Argon2id).
- Поиск рынков по городу/штату/ZIP/части названия.
- Сортировка: по имени, городу, штату, рейтингу, дистанции.
- Пагинация (page/size).
- Отзывы: просмотр, добавление, удаление (удалять можно только свои).
- Расчёт среднего рейтинга по отзывам.
- Расчёт расстояния (haversine) при заданном центре `center=lat,lon`.

## Требования

- Python 3.10+

## Установка

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows (PowerShell)

pip install -r requirements.txt
````

## Запуск

```bash
python app.py
```

## Файлы данных

Приложение ожидает рядом со скриптом:

* `farmers_markets.csv` — исходные данные рынков
* `users.json` — пользователи (JSON-массив)
* `reviews.json` — отзывы (JSON-массив)

Если `users.json` / `reviews.json` не существуют — будут созданы автоматически с `[]`.

Для удобства тестирования `users.json` и `reviews.json` могут быть заранее заполнены тестовыми данными.

### Ожидаемые колонки в CSV

Используются поля:

* `FMID` (id)
* `MarketName` (название)
* `city`
* `State`
* `zip`
* `x` (lon)
* `y` (lat)

## Команды (REPL)

Формат: `cmd key=value key=value`

Если значение содержит пробелы, заключайте его в кавычки.

Пример:
`review_add market=1009994 rating=5 text="Очень хороший рынок"`

### Справка и выход

* `help`
* `exit` (также `quit`, `q`)

### Авторизация

* `register email=... login=... password=... first=... last=...`
* `login login=... password=...`
* `logout`

### Рынки

* `list [page=N] [size=N] [sort=name|city|state|rating|distance] [order=asc|desc] [center=lat,lon]`

* `search [city=...] [state=...] [zip=...] [name=...] [radius=N] [center=lat,lon]       [page=N] [size=N] [sort=name|city|state|rating|distance] [order=asc|desc]`

Правила:

* `sort=distance` требует `center=lat,lon`
* `radius` работает только если задан `center=lat,lon`

### Детали рынка

* `show id=12345`

### Отзывы

* `reviews market=12345`
* `review_add market=12345 rating=1..5 [text="..."]`
* `review_delete id=...`

## Правила валидации

### Login
- обязателен
- длина: от 3 до 32 символов
- допустимы только латинские буквы, цифры, `_` и `-`
- не должен начинаться или заканчиваться символами `_` или `-`
- не должен содержать подряд `__` или `--`
- не должен совпадать с зарезервированными значениями (`admin`, `root`, `login`, `logout`, `register` и др.)

### Password
- обязателен
- длина: от 8 до 128 символов
- не должен быть слишком простым или часто используемым
- не должен состоять только из цифр
- не должен состоять только из букв
- должен содержать хотя бы одну букву
- должен содержать хотя бы одну цифру
- должен содержать буквы в разных регистрах
- не должен содержать login
- должен состоять только из печатаемых символов

### Email
- обязателен
- проверяется на корректный формат
- проверка выполняется без проверки существования почтового ящика

## Примеры

```bash
register email=ivan@example.com login=ivan password=Qwerty123 first=Иван last=Иванов
logout
login login=ivan password=Qwerty123

list page=1 size=10 sort=name order=asc
search city=Chicago sort=rating order=desc page=1 size=10
search name=market state=California
list sort=distance order=asc center=41.8819,-87.6278

show id=1009994
reviews market=1009994
review_add market=1009994 rating=5 text="Отличный рынок!"
review_delete id=0
```

## Примечания по безопасности

* Пароли хранятся только в виде Argon2id-хэша.
* Валидация email выполняется без проверки доставляемости (`check_deliverability=False`).
