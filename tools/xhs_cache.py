import json
import os
import sqlite3
from datetime import datetime, timedelta

_TTL = {"amap": timedelta(days=30), "xhs": timedelta(days=7)}

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS poi_cache (
    city_key   TEXT NOT NULL,
    category   TEXT NOT NULL,
    source     TEXT NOT NULL,
    cached_at  TEXT NOT NULL,
    data       TEXT NOT NULL,
    PRIMARY KEY (city_key, category, source)
)
"""


def _db_path() -> str | None:
    return os.getenv("XHS_CACHE_DB")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.execute(_CREATE_SQL)
    return conn


def get(city_key: str, category: str, source: str) -> dict | list | None:
    if not _db_path():
        return None
    row = _conn().execute(
        "SELECT cached_at, data FROM poi_cache WHERE city_key=? AND category=? AND source=?",
        (city_key, category, source),
    ).fetchone()
    if not row:
        return None
    age = datetime.now() - datetime.fromisoformat(row[0])
    if age > _TTL[source]:
        return None
    return json.loads(row[1])


def set(city_key: str, category: str, source: str, data: dict | list) -> None:
    if not _db_path():
        return
    conn = _conn()
    conn.execute(
        "INSERT OR REPLACE INTO poi_cache VALUES (?,?,?,?,?)",
        (city_key, category, source, datetime.now().isoformat(), json.dumps(data, ensure_ascii=False)),
    )
    conn.commit()
