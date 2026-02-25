import csv
from pathlib import Path
from typing import Any, Callable
import json
import shlex
import os
import hashlib
from datetime import datetime, timezone

AppState = dict[str, Any]

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "farmers_markets.csv"
USERS_PATH = BASE_DIR / "users.json"
REVIEWS_PATH = BASE_DIR / "reviews.json"
HELP = """
Доступные команды (формат: key=value):

help
exit

Авторизация:
register email=... login=... password=... first=... last=...
login login=... password=...
logout

Рынки:
list [page=N] [size=N] [sort=name|city|state|rating|distance] [order=asc|desc] [center=lat,lon]

search [city=...] [state=...] [zip=...] [name=...] [radius=N] [center=lat,lon]
        [page=N] [size=N] [sort=name|city|state|rating|distance] [order=asc|desc]

Детали:
show id=12345

Отзывы:
reviews market=12345
review_add market=12345 rating=1..5 [text="..."]
review_delete id=...

Примечания:
- sort=distance требует center=lat,lon (иначе ошибка).
- radius работает только если задан center=lat,lon.
"""


def load_reviews(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]\n", encoding="utf-8")
        return []

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("reviews.json должен содержать JSON-массив (список отзывов).")

    return data


def load_users(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]\n", encoding="utf-8")
        return []

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(
            "users.json должен содержать JSON-массив (список пользователей)."
        )
    return data


def norm(s: str) -> str:
    return " ".join((s or "").strip().casefold().split())


def parse_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_market(row: dict[str, str]) -> dict[str, Any]:
    return {
        "id": int(row["FMID"]),
        "name": row["MarketName"].strip(),
        "city": row["city"].strip(),
        "state": row["State"].strip(),
        "zip": row["zip"].strip(),
        "lat": parse_float(row.get("y")),
        "lon": parse_float(row.get("x")),
        "city_norm": row["city"].strip().casefold(),
        "state_norm": row["State"].strip().casefold(),
        "name_norm": row["MarketName"].strip().casefold(),
        "raw": row,
    }


def load_markets_csv(path: Path) -> dict[int, dict]:
    markets: dict[int, dict] = {}

    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            try:
                market = normalize_market(row)
                markets[market["id"]] = market
            except Exception:
                continue

    return markets


def parse_line(line: str) -> tuple[str, dict[str, str]] | None:
    line = line.strip()
    if not line:
        return None

    parts = shlex.split(line)

    cmd = parts[0].lower()

    kwargs: dict[str, str] = {}

    for t in parts[1:]:
        if "=" in t:
            k, v = t.split("=", 1)
            kwargs[k.strip().lower()] = v.strip()

    return cmd, kwargs


def cmd_help(state: AppState, kv: dict[str, str]) -> None:
    print(HELP)


def cmd_logout(state: AppState, kv: dict[str, str]) -> None:
    state["session"]["user"] = None
    print("Вы вышли из аккаунта.")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    iters = 200_000
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters)
    return f"pbkdf2_sha256${iters}${salt.hex()}${dk.hex()}"


def now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def save_json_list(path: Path, data: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def cmd_register(state: AppState, kv: dict[str, str]) -> None:
    email = (kv.get("email") or "").strip()
    login = (kv.get("login") or "").strip()
    password = kv.get("password") or ""
    first = (kv.get("first") or "").strip()
    last = (kv.get("last") or "").strip()

    if not email or not login or not password:
        print("Ошибка: register требует email=... login=... password=...")
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

    new_id = max((int(u["id"]) for u in state["users"]), default=-1) + 1

    user = {
        "id": new_id,
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


def run_repl(state: AppState) -> None:
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
