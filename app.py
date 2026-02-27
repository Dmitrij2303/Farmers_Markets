"""Console application for browsing farmers markets, managing users, and working with reviews."""

import csv
import json
import shlex
import string
from datetime import datetime, timezone
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any, Callable

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from email_validator import EmailNotValidError, validate_email

Market = dict[str, Any]
Markets = dict[int, Market]
User = dict[str, Any]
Review = dict[str, Any]
CommandArgs = dict[str, str]
AppState = dict[str, Any]

ph = PasswordHasher()

# Paths
BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "farmers_markets.csv"
USERS_PATH = BASE_DIR / "users.json"
REVIEWS_PATH = BASE_DIR / "reviews.json"

# Login validation
LOGIN_ALLOWED_CHARS = set(string.ascii_letters + string.digits + "_-")
MIN_LOGIN_LEN = 3
MAX_LOGIN_LEN = 32
RESERVED_LOGINS = {
    "admin",
    "root",
    "system",
    "support",
    "null",
    "none",
    "me",
    "self",
    "api",
    "auth",
    "login",
    "logout",
    "register",
    "user",
    "users",
    "test",
}

# Password validation
MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 128
COMMON_PASSWORDS = {
    "password",
    "12345678",
    "qwertyui",
    "abcdefgh",
    "11111111",
    "password1",
}

# Help text
HELP = """
Farmers Markets CLI

Формат ввода:
  команда key=value key=value
  Если значение содержит пробелы, заключайте его в кавычки:
  review_add market=123 rating=5 text="Очень хороший рынок"

Доступные команды:
  help
  exit

Авторизация:
  register email=... login=... password=... [first=...] [last=...]
      Регистрация нового пользователя.
      Обязательные поля: email, login, password.

  login login=... password=...
      Вход в существующий аккаунт.

  logout
      Выход из текущего аккаунта.

Рынки:
  list [page=N] [size=N] [sort=name|city|state|rating|distance]
       [order=asc|desc] [center=lat,lon]
      Показать список всех рынков.

  search [city=...] [state=...] [zip=...] [name=...]
         [radius=N] [center=lat,lon]
         [page=N] [size=N]
         [sort=name|city|state|rating|distance] [order=asc|desc]
      Поиск рынков по фильтрам.

  show id=12345
      Подробная информация о рынке по его ID.

Отзывы:
  reviews market=12345
      Показать отзывы по рынку.

  review_add market=12345 rating=1..5 [text="..."]
      Добавить отзыв. Требуется вход в аккаунт.

  review_delete id=...
      Удалить свой отзыв по ID. Требуется вход в аккаунт.

Примеры:
  register email=user@example.com login=ivan password=Qwerty12345
  register email=user@example.com login=ivan password=Qwerty12345 first=Иван last=Иванов

  login login=ivan password=Qwerty12345
  logout

  list
  list page=2 size=5
  list sort=city order=asc
  list sort=distance order=asc center=41.88,-87.63

  search city=Chicago
  search state=California name=market
  search zip=60621
  search name=farm center=41.88,-87.63 radius=10 sort=distance order=asc

  show id=1009994

  reviews market=1009994
  review_add market=1009994 rating=5 text="Отличный рынок"
  review_delete id=0

Примечания:
  - sort=distance требует center=lat,lon
  - radius работает только вместе с center=lat,lon
  - name в search ищется по вхождению подстроки
  - city, state и zip фильтруются по точному совпадению
  - review_add доступна только после входа в аккаунт
  - review_delete удаляет только ваш собственный отзыв
"""


def load_json_list(path: Path, invalid_type_message: str) -> list[dict[str, Any]]:
    """Load a JSON file expected to contain a list.

    If the file does not exist, create it with an empty JSON list and return an empty list.
    Raise ValueError if the file content is not a JSON array.
    """
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]\n", encoding="utf-8")
        return []

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(invalid_type_message)

    return data


def load_reviews(path: Path) -> list[dict[str, Any]]:
    """Load reviews from a JSON file."""
    return load_json_list(
        path,
        "reviews.json должен содержать JSON-массив (список отзывов).",
    )


def load_users(path: Path) -> list[dict[str, Any]]:
    """Load users from a JSON file."""
    return load_json_list(
        path,
        "users.json должен содержать JSON-массив (список пользователей).",
    )


def norm(s: str) -> str:
    """Normalize free-text input for case-insensitive comparison.

    Strip leading and trailing whitespace, collapse internal whitespace,
    and convert the string to case-insensitive form.
    """
    return " ".join((s or "").strip().casefold().split())


def parse_float(value: str | None) -> float | None:
    """Convert a string value to float.

    Return None if the value is missing or cannot be converted.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_market(row: dict[str, str]) -> Market:
    """Convert a raw CSV row into a normalized market dictionary."""
    return {
        "id": int(row["FMID"]),
        "name": row["MarketName"].strip(),
        "city": row["city"].strip(),
        "state": row["State"].strip(),
        "zip": row["zip"].strip(),
        "lat": parse_float(row.get("y")),
        "lon": parse_float(row.get("x")),
        "city_norm": norm(row["city"]),
        "state_norm": norm(row["State"]),
        "name_norm": norm(row["MarketName"]),
        "raw": row,
    }


def load_markets_csv(path: Path) -> Markets:
    """Load farmers markets from a CSV file.

    Invalid rows are skipped. The returned dictionary is keyed by market ID.
    """
    markets: Markets = {}
    skipped = 0

    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            try:
                market = normalize_market(row)
                markets[market["id"]] = market
            except (KeyError, TypeError, ValueError):
                skipped += 1

    if skipped:
        print(f"Предупреждение: пропущено строк CSV: {skipped}")

    return markets


def parse_line(line: str) -> tuple[str, dict[str, str]] | None:
    """Parse a REPL input line into a command name and key-value arguments.

    Return None for an empty line or invalid shell-like quoting.
    """
    line = line.strip()
    if not line:
        return None

    try:
        parts = shlex.split(line)
    except ValueError:
        print("Ошибка: некорректный ввод. Проверьте кавычки.")
        return None

    cmd = parts[0].lower()
    kwargs: dict[str, str] = {}

    for t in parts[1:]:
        if "=" in t:
            k, v = t.split("=", 1)
            kwargs[k.strip().lower()] = v.strip()

    return cmd, kwargs


def cmd_help(_state: AppState, _kv: CommandArgs) -> None:
    """Print the help message with available commands."""
    print(HELP)


def cmd_logout(state: AppState, kv: CommandArgs) -> None:
    """Log out the current user."""
    if state["session"]["user"] is None:
        print("Вы не авторизованы.")
        return
    state["session"]["user"] = None
    print("Вы вышли из аккаунта.")


def is_valid_email(email: str) -> bool:
    """Validate an email address format.

    Deliverability is not checked; only the email syntax is validated.
    """
    try:
        validate_email(email, check_deliverability=False)
        return True
    except EmailNotValidError:
        return False


def validate_login(login: str) -> str | None:
    """Validate a login string.

    Return an error message if validation fails, otherwise return None.
    """
    if not login:
        return "Логин не должен быть пустым."

    if len(login) < MIN_LOGIN_LEN:
        return f"Логин должен быть не короче {MIN_LOGIN_LEN} символов."

    if len(login) > MAX_LOGIN_LEN:
        return f"Логин должен быть не длиннее {MAX_LOGIN_LEN} символов."

    if not LOGIN_ALLOWED_CHARS.issuperset(login):
        return "Логин может содержать только латинские буквы, цифры, '_' и '-'."

    if login[0] in "_-":
        return "Логин не должен начинаться с '_' или '-'."

    if login[-1] in "_-":
        return "Логин не должен заканчиваться '_' или '-'."

    if "__" in login or "--" in login:
        return "Логин не должен содержать подряд '__' или '--'."

    if login.casefold() in RESERVED_LOGINS:
        return "Этот логин зарезервирован."

    return None


def validate_password(password: str, login: str) -> list[str]:
    """Validate a password against basic security rules.

    Return a list of validation error messages. Return an empty list if the password is valid.
    """
    errors: list[str] = []

    if not password:
        return ["Пароль не должен быть пустым."]

    if len(password) < MIN_PASSWORD_LEN:
        errors.append(f"Пароль должен быть не короче {MIN_PASSWORD_LEN} символов.")

    if len(password) > MAX_PASSWORD_LEN:
        errors.append(f"Пароль должен быть не длиннее {MAX_PASSWORD_LEN} символов.")

    if password.lower() in COMMON_PASSWORDS:
        errors.append("Пароль слишком простой (часто используемый).")

    if password.isdigit():
        errors.append("Пароль не должен состоять только из цифр.")

    if password.isalpha():
        errors.append("Пароль не должен состоять только из букв.")

    if password.islower() or password.isupper():
        errors.append("Используйте разные регистры букв.")

    if not any(ch.isdigit() for ch in password):
        errors.append("Добавьте хотя бы одну цифру.")

    if not any(ch.isalpha() for ch in password):
        errors.append("Добавьте хотя бы одну букву.")

    if not password.isprintable():
        errors.append("Пароль содержит недопустимые символы.")

    if login.lower() in password.lower():
        errors.append("Пароль не должен содержать логин.")

    return errors


def hash_password(password: str) -> str:
    """Hash a plain-text password using Argon2."""
    return ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plain-text password against its stored Argon2 hash."""
    try:
        return ph.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def now_iso() -> str:
    """Return the current UTC time in ISO 8601 format with a trailing 'Z'."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def save_json_list(path: Path, data: list[dict[str, Any]]) -> None:
    """Save a list of dictionaries to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def cmd_register(state: AppState, kv: CommandArgs) -> None:
    """Register a new user and start a session for that user.

    Validates login, email, and password before saving the user to disk.
    """
    email = (kv.get("email") or "").strip()
    login = (kv.get("login") or "").strip()
    password = kv.get("password") or ""
    first = (kv.get("first") or "").strip()
    last = (kv.get("last") or "").strip()

    if not email or not login or not password:
        print("Ошибка: register требует email=... login=... password=...")
        return

    error = validate_login(login)
    if error:
        print("Ошибка:", error)
        return

    if not is_valid_email(email):
        print("Ошибка: некорректный email.")
        return

    login_norm = login.casefold()
    email_norm = email.casefold()

    for u in state["users"]:
        if u.get("login", "").casefold() == login_norm:
            print("Ошибка: такой login уже занят.")
            return
        if u.get("email", "").casefold() == email_norm:
            print("Ошибка: такой email уже зарегистрирован.")
            return

    errors = validate_password(password, login)
    if errors:
        for err in errors:
            print("Ошибка:", err)
        return

    user = {
        "id": max((int(u["id"]) for u in state["users"]), default=-1) + 1,
        "email": email,
        "login": login,
        "password_hash": hash_password(password),
        "first": first,
        "last": last,
        "created_at": now_iso(),
    }

    state["users"].append(user)
    save_json_list(state["paths"]["users"], state["users"])
    state["session"]["user"] = user
    print("Регистрация успешна. Вы вошли в аккаунт.")


def find_user_by_login(users: list[User], login: str) -> User | None:
    """Find and return a user by login, using case-insensitive comparison."""
    login_norm = login.casefold()
    for user in users:
        if user.get("login", "").casefold() == login_norm:
            return user
    return None


def cmd_login(state: AppState, kv: CommandArgs) -> None:
    """Authenticate a user by login and password and start a session."""
    login = kv.get("login", "").strip()
    password = kv.get("password", "")
    if not login or not password:
        print("Ошибка: login требует login=... password=...")
        return

    user = find_user_by_login(state["users"], login)
    if not user or not verify_password(password, user.get("password_hash", "")):
        print("Неверный логин или пароль.")
        return

    state["session"]["user"] = user
    print("Вход выполнен.")


def parse_int(value: str | None, default: int, *, min_value: int = 1) -> int:
    """Parse an integer value with fallback and minimum bound.

    Return the default value if parsing fails.
    """
    try:
        n = int(value) if value is not None else default
        return max(n, min_value)
    except (TypeError, ValueError):
        return default


def parse_center(value: str | None) -> tuple[float, float] | None:
    """Parse a 'lat,lon' string into a coordinate tuple.

    Return None if the value is missing or invalid.
    """
    if not value:
        return None
    try:
        lat_s, lon_s = value.split(",", 1)
        return float(lat_s), float(lon_s)
    except (ValueError, AttributeError):
        return None


def build_rating_stats(reviews: list[Review]) -> dict[int, dict[str, Any]]:
    """Build aggregated rating statistics for markets from the review list.

    The result maps market IDs to dictionaries containing review count and average rating.
    """
    acc: dict[int, dict[str, Any]] = {}

    for review in reviews:
        try:
            market_id = int(review["market_id"])
            rating = int(review["rating"])
        except (KeyError, TypeError, ValueError):
            continue

        item = acc.setdefault(market_id, {"count": 0, "sum": 0})
        item["count"] += 1
        item["sum"] += rating

    result: dict[int, dict[str, Any]] = {}
    for market_id, item in acc.items():
        count = item["count"]
        total = item["sum"]
        result[market_id] = {
            "count": count,
            "avg": round(total / count, 2) if count else None,
        }

    return result


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two geographic points in kilometers."""
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return r * c


def enrich_market(
    market: Market,
    rating_stats: dict[int, dict[str, Any]],
    center: tuple[float, float] | None = None,
) -> Market:
    """Return a copy of a market enriched with rating and optional distance data."""
    item = market.copy()

    rs = rating_stats.get(market["id"], {"count": 0, "avg": None})
    item["rating_count"] = rs["count"]
    item["rating_avg"] = rs["avg"]

    item["distance"] = None
    if center and item["lat"] is not None and item["lon"] is not None:
        item["distance"] = round(
            haversine_km(center[0], center[1], item["lat"], item["lon"]), 2
        )

    return item


def sort_markets(items: list[Market], sort_by: str, order: str) -> list[Market]:
    """Sort market items by the requested field and order."""
    if sort_by not in {"name", "city", "state", "rating", "distance"}:
        sort_by = "name"

    def key_name(x: Market):
        return (x["name_norm"], x["id"])

    def key_city(x: Market):
        return (x["city_norm"], x["name_norm"], x["id"])

    def key_state(x: Market):
        return (x["state_norm"], x["city_norm"], x["name_norm"], x["id"])

    def key_rating(x: Market):
        rating = x["rating_avg"]
        has_rating = rating is not None
        return (not has_rating, -(rating or 0), x["name_norm"], x["id"])

    def key_distance(x: Market):
        distance = x["distance"]
        return (
            distance is None,
            distance if distance is not None else float("inf"),
            x["name_norm"],
            x["id"],
        )

    key_map = {
        "name": key_name,
        "city": key_city,
        "state": key_state,
        "rating": key_rating,
        "distance": key_distance,
    }

    reverse = order == "desc"
    result = sorted(items, key=key_map[sort_by], reverse=reverse)
    return result


def paginate(items: list[Market], page: int, size: int) -> tuple[list[Market], int]:
    """Return a page slice of items together with the total item count."""
    total = len(items)
    start = (page - 1) * size
    end = start + size
    return items[start:end], total


def format_cell(value: Any, width: int) -> str:
    """Format a value for fixed-width table output.

    Long values are truncated with an ellipsis.
    """
    text = str(value)
    if len(text) <= width:
        return text.ljust(width)
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "…"


def print_markets(items: list[Market]) -> None:
    """Print market items as a formatted table in the console."""
    if not items:
        print("Ничего не найдено.")
        return

    headers = {
        "id": "ID",
        "name": "NAME",
        "city": "CITY",
        "state": "STATE",
        "zip": "ZIP",
        "rating": "RATING",
        "distance": "DIST",
    }

    widths = {
        "id": 8,
        "name": 50,
        "city": 20,
        "state": 16,
        "zip": 8,
        "rating": 10,
        "distance": 10,
    }

    header_line = " | ".join(
        [
            format_cell(headers["id"], widths["id"]),
            format_cell(headers["name"], widths["name"]),
            format_cell(headers["city"], widths["city"]),
            format_cell(headers["state"], widths["state"]),
            format_cell(headers["zip"], widths["zip"]),
            format_cell(headers["rating"], widths["rating"]),
            format_cell(headers["distance"], widths["distance"]),
        ]
    )
    print(header_line)
    print("-" * len(header_line))

    for m in items:
        rating_text = (
            f"{m['rating_avg']} ({m['rating_count']})"
            if m["rating_avg"] is not None
            else "нет"
        )
        distance_text = f"{m['distance']} км" if m["distance"] is not None else "-"

        row = " | ".join(
            [
                format_cell(m["id"], widths["id"]),
                format_cell(m["name"], widths["name"]),
                format_cell(m["city"], widths["city"]),
                format_cell(m["state"], widths["state"]),
                format_cell(m["zip"], widths["zip"]),
                format_cell(rating_text, widths["rating"]),
                format_cell(distance_text, widths["distance"]),
            ]
        )
        print(row)


def cmd_list(state: AppState, kv: CommandArgs) -> None:
    """List all markets with optional pagination, sorting, and distance calculation."""
    page = parse_int(kv.get("page"), 1)
    size = parse_int(kv.get("size"), 10)
    sort_by = (kv.get("sort") or "name").strip().lower()
    order = (kv.get("order") or "asc").strip().lower()
    center = parse_center(kv.get("center"))

    if sort_by == "distance" and center is None:
        print("Ошибка: sort=distance требует center=lat,lon")
        return

    rating_stats = build_rating_stats(state["reviews"])
    items = [enrich_market(m, rating_stats, center) for m in state["markets"]]
    items = sort_markets(items, sort_by, order)

    page_items, total = paginate(items, page, size)

    print(f"Всего рынков: {total}. Страница {page}, размер {size}.")
    print_markets(page_items)


def cmd_search(state: AppState, kv: CommandArgs) -> None:
    """Search markets by filters such as city, state, ZIP code, name, and radius."""
    city = norm(kv.get("city", ""))
    state_q = norm(kv.get("state", ""))
    zip_q = (kv.get("zip") or "").strip()
    name = norm(kv.get("name", ""))

    page = parse_int(kv.get("page"), 1)
    size = parse_int(kv.get("size"), 10)
    sort_by = (kv.get("sort") or "name").strip().lower()
    order = (kv.get("order") or "asc").strip().lower()
    center = parse_center(kv.get("center"))

    radius_raw = kv.get("radius")
    radius = None
    if radius_raw is not None:
        try:
            radius = float(radius_raw)
            if radius < 0:
                raise ValueError
        except ValueError:
            print("Ошибка: radius должен быть неотрицательным числом.")
            return

    if radius is not None and center is None:
        print("Ошибка: radius работает только если задан center=lat,lon")
        return

    if sort_by == "distance" and center is None:
        print("Ошибка: sort=distance требует center=lat,lon")
        return

    rating_stats = build_rating_stats(state["reviews"])

    items = []
    for market in state["markets"]:
        if city and market["city_norm"] != city:
            continue
        if state_q and market["state_norm"] != state_q:
            continue
        if zip_q and market["zip"] != zip_q:
            continue
        if name and name not in market["name_norm"]:
            continue

        item = enrich_market(market, rating_stats, center)

        if radius is not None:
            if item["distance"] is None or item["distance"] > radius:
                continue

        items.append(item)

    items = sort_markets(items, sort_by, order)
    page_items, total = paginate(items, page, size)

    print(f"Найдено рынков: {total}. Страница {page}, размер {size}.")
    print_markets(page_items)


def cmd_show(state: AppState, kv: CommandArgs) -> None:
    """Show detailed information for a single market by its ID."""
    raw_id = kv.get("id")
    try:
        market_id = int(raw_id) if raw_id is not None else None
    except ValueError:
        print("Ошибка: id должен быть целым числом.")
        return

    if market_id is None:
        print("Ошибка: show требует id=...")
        return

    market = state["markets_by_id"].get(market_id)
    if not market:
        print("Рынок не найден.")
        return

    rating_stats = build_rating_stats(state["reviews"])
    item = enrich_market(market, rating_stats)

    print(f"ID: {item['id']}")
    print(f"Название: {item['name']}")
    print(f"Город: {item['city']}")
    print(f"Штат: {item['state']}")
    print(f"ZIP: {item['zip']}")
    print(f"Координаты: {item['lat']}, {item['lon']}")
    if item["rating_avg"] is None:
        print("Рейтинг: нет отзывов")
    else:
        print(f"Рейтинг: {item['rating_avg']} ({item['rating_count']} отзывов)")


def cmd_reviews(state: AppState, kv: CommandArgs) -> None:
    """Show all reviews for a market together with summary rating information."""
    raw_market_id = kv.get("market")
    try:
        market_id = int(raw_market_id) if raw_market_id is not None else None
    except ValueError:
        print("Ошибка: market должен быть целым числом.")
        return

    if market_id is None:
        print("Ошибка: reviews требует market=...")
        return

    market = state["markets_by_id"].get(market_id)
    if not market:
        print("Рынок не найден.")
        return

    market_reviews = [
        review
        for review in state["reviews"]
        if int(review.get("market_id", -1)) == market_id
    ]

    print(f"Отзывы для рынка: {market['name']} (ID: {market_id})")

    if not market_reviews:
        print("Отзывов пока нет.")
        return

    market_reviews.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    rating_stats = build_rating_stats(state["reviews"])
    stats = rating_stats.get(market_id, {"count": 0, "avg": None})

    if stats["avg"] is None:
        print("Средний рейтинг: нет отзывов")
    else:
        print(f"Средний рейтинг: {stats['avg']} ({stats['count']} отзывов)")

    for review in market_reviews:
        review_id = review.get("id")
        rating = review.get("rating")
        created_at = review.get("created_at", "-")
        login = review.get("login")

        if not login:
            user_id = review.get("user_id")
            user = next(
                (u for u in state["users"] if u.get("id") == user_id),
                None,
            )
            login = user.get("login") if user else f"user_id={user_id}"

        print(
            f"\n[{review_id}] rating={rating} | author={login} | created_at={created_at}"
        )

        text = (review.get("text") or "").strip()
        if text:
            print(f"  {text}")


def cmd_review_add(state: AppState, kv: CommandArgs) -> None:
    """Add a new review for a market from the currently logged-in user."""
    user = state["session"]["user"]
    if user is None:
        print("Ошибка: для добавления отзыва нужно войти в аккаунт.")
        return

    raw_market_id = kv.get("market")
    raw_rating = kv.get("rating")
    text = (kv.get("text") or "").strip()

    try:
        market_id = int(raw_market_id) if raw_market_id is not None else None
    except ValueError:
        print("Ошибка: market должен быть целым числом.")
        return

    try:
        rating = int(raw_rating) if raw_rating is not None else None
    except ValueError:
        print("Ошибка: rating должен быть целым числом от 1 до 5.")
        return

    if market_id is None or rating is None:
        print("Ошибка: review_add требует market=... rating=1..5")
        return

    if market_id not in state["markets_by_id"]:
        print("Рынок не найден.")
        return

    if rating < 1 or rating > 5:
        print("Ошибка: rating должен быть целым числом от 1 до 5.")
        return

    review = {
        "id": max((int(r.get("id", -1)) for r in state["reviews"]), default=-1) + 1,
        "market_id": market_id,
        "user_id": user["id"],
        "login": user["login"],
        "rating": rating,
        "text": text,
        "created_at": now_iso(),
    }

    state["reviews"].append(review)
    save_json_list(state["paths"]["reviews"], state["reviews"])
    print("Отзыв успешно добавлен.")


def cmd_review_delete(state: AppState, kv: CommandArgs) -> None:
    """Delete a review by ID if it belongs to the currently logged-in user."""
    user = state["session"]["user"]
    if user is None:
        print("Ошибка: для удаления отзыва нужно войти в аккаунт.")
        return

    raw_review_id = kv.get("id")
    try:
        review_id = int(raw_review_id) if raw_review_id is not None else None
    except ValueError:
        print("Ошибка: id должен быть целым числом.")
        return

    if review_id is None:
        print("Ошибка: review_delete требует id=...")
        return

    review_index = None
    review_to_delete = None

    for i, review in enumerate(state["reviews"]):
        if int(review.get("id", -1)) == review_id:
            review_index = i
            review_to_delete = review
            break

    if review_to_delete is None:
        print("Отзыв не найден.")
        return

    if review_to_delete.get("user_id") != user["id"]:
        print("Ошибка: можно удалять только свои отзывы.")
        return

    del state["reviews"][review_index]
    save_json_list(state["paths"]["reviews"], state["reviews"])
    print("Отзыв удалён.")


def run_repl(state: AppState) -> None:
    """Run the interactive REPL loop and dispatch commands to their handlers."""
    handlers: dict[str, Callable[[AppState, dict[str, str]], None]] = {
        "help": cmd_help,
        "logout": cmd_logout,
        "register": cmd_register,
        "login": cmd_login,
        "list": cmd_list,
        "search": cmd_search,
        "show": cmd_show,
        "reviews": cmd_reviews,
        "review_add": cmd_review_add,
        "review_delete": cmd_review_delete,
    }
    while True:
        try:
            line = input("\n> ")
        except (EOFError, KeyboardInterrupt):
            print("\nВыход.")
            return

        parsed = parse_line(line)
        if parsed is None:
            continue

        cmd, kv = parsed
        if cmd in {"exit", "quit", "q"}:
            print("Выход.")
            return

        handler = handlers.get(cmd)
        if not handler:
            print("Неизвестная команда. Введите: help")
            continue

        handler(state, kv)


def main() -> int:
    """Initialize application state, print the welcome message, and start the REPL."""
    markets_by_id = load_markets_csv(DATA_PATH)
    users = load_users(USERS_PATH)
    reviews = load_reviews(REVIEWS_PATH)

    state: AppState = {
        "paths": {
            "data": DATA_PATH,
            "users": USERS_PATH,
            "reviews": REVIEWS_PATH,
        },
        "markets_by_id": markets_by_id,
        "markets": list(markets_by_id.values()),
        "users": users,
        "reviews": reviews,
        "session": {"user": None},
        "last_result_ids": [],
    }

    print("Farmers Markets CLI")
    print("Введите команду: help  (выход: exit)")
    run_repl(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
