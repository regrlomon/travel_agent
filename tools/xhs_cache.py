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


def get(city_key: str, category: str, source: str) -> dict | list | None:
    if not _db_path():
        return None
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute(_CREATE_SQL)
        row = conn.execute(
            "SELECT cached_at, data FROM poi_cache WHERE city_key=? AND category=? AND source=?",
            (city_key, category, source),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    age = datetime.now() - datetime.fromisoformat(row[0])
    if age > _TTL.get(source, timedelta(days=7)):
        return None
    return json.loads(row[1])


def set(city_key: str, category: str, source: str, data: dict | list) -> None:
    if not _db_path():
        return
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute(_CREATE_SQL)
        conn.execute(
            "INSERT OR REPLACE INTO poi_cache VALUES (?,?,?,?,?)",
            (city_key, category, source, datetime.now().isoformat(), json.dumps(data, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        conn.close()
