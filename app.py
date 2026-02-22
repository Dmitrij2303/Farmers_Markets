import csv
from pathlib import Path
from typing import Any
import json


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "farmers_markets.csv"
USERS_PATH = BASE_DIR / "users.json"
REVIEWS_PATH = BASE_DIR / "reviews.json"


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


def run_repl(state: dict[str, Any]) -> None:
    HELP = """
    Доступные команды (формат: key=value):

    help
    exit

    Авторизация:
    register email=... login=... password=... first=... last=...
    login login=... password=...
    logout
    """
    while True:
        try:
            line = input("\n> ")
        except (EOFError, KeyboardInterrupt):
            print("\nВыход.")
            return


def main() -> int:
    markets_by_id = load_markets_csv(DATA_PATH)
    users = load_users(USERS_PATH)
    reviews = load_reviews(REVIEWS_PATH)

    state: dict[str, Any] = {
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
