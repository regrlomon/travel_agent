import pytest
import importlib


def _reload_cache(monkeypatch, db_path=None):
    if db_path:
        monkeypatch.setenv("XHS_CACHE_DB", db_path)
    else:
        monkeypatch.delenv("XHS_CACHE_DB", raising=False)
    import tools.xhs_cache as m
    importlib.reload(m)
    return m


def test_get_returns_none_when_not_configured(monkeypatch):
    cache = _reload_cache(monkeypatch)
    assert cache.get("310100", "景点", "xhs") is None


def test_set_is_noop_when_not_configured(monkeypatch):
    cache = _reload_cache(monkeypatch)
    cache.set("310100", "景点", "xhs", {"外滩": {"mention_count": 5, "has_negative": False}})


def test_cache_roundtrip(tmp_path, monkeypatch):
    cache = _reload_cache(monkeypatch, str(tmp_path / "cache.db"))
    data = {"外滩": {"mention_count": 10, "has_negative": False}}
    cache.set("310100", "景点", "xhs", data)
    assert cache.get("310100", "景点", "xhs") == data


def test_cache_miss_returns_none(tmp_path, monkeypatch):
    cache = _reload_cache(monkeypatch, str(tmp_path / "cache.db"))
    assert cache.get("310100", "美食", "xhs") is None


def test_cache_expired_returns_none(tmp_path, monkeypatch):
    from datetime import datetime, timedelta
    cache = _reload_cache(monkeypatch, str(tmp_path / "cache.db"))
    data = {"外滩": {"mention_count": 5, "has_negative": False}}
    cache.set("310100", "景点", "xhs", data)
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "cache.db"))
    old_ts = (datetime.now() - timedelta(days=31)).isoformat()
    conn.execute("UPDATE poi_cache SET cached_at = ? WHERE city_key = '310100'", (old_ts,))
    conn.commit()
    assert cache.get("310100", "景点", "xhs") is None


def test_amap_ttl_is_30_days(tmp_path, monkeypatch):
    from datetime import datetime, timedelta
    cache = _reload_cache(monkeypatch, str(tmp_path / "cache.db"))
    data = [{"name": "外滩"}]
    cache.set("310100", "景点", "amap", data)
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "cache.db"))
    old_ts = (datetime.now() - timedelta(days=29)).isoformat()
    conn.execute("UPDATE poi_cache SET cached_at = ? WHERE city_key = '310100'", (old_ts,))
    conn.commit()
    assert cache.get("310100", "景点", "amap") == data


def test_insert_or_replace_overwrites(tmp_path, monkeypatch):
    cache = _reload_cache(monkeypatch, str(tmp_path / "cache.db"))
    cache.set("310100", "景点", "xhs", {"外滩": {"mention_count": 5, "has_negative": False}})
    cache.set("310100", "景点", "xhs", {"外滩": {"mention_count": 99, "has_negative": True}})
    result = cache.get("310100", "景点", "xhs")
    assert result["外滩"]["mention_count"] == 99
