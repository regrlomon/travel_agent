import httpx
from typing import Optional
from langsmith import traceable

AMAP_BASE = "https://restapi.amap.com/v3"


async def get_district_codes(city_names: list[str], api_key: str) -> dict[str, str]:
    """Map city names to 高德 adcodes via the district API (avoids LLM hallucinating numeric codes)."""
    result: dict[str, str] = {}
    async with httpx.AsyncClient() as client:
        for name in city_names:
            resp = await client.get(
                f"{AMAP_BASE}/config/district",
                params={"keywords": name, "subdistrict": "0", "extensions": "base", "key": api_key},
            )
            data = resp.json()
            if data.get("status") == "1" and data.get("districts"):
                result[name] = data["districts"][0]["adcode"]
    return result


async def search_pois(
    city_codes: list[str],
    keywords: str,
    api_key: str,
    types: str = "110000|120000|140000",
    page_size: int = 25,
) -> list[dict]:
    """Fetch POIs from 高德 for a list of city adcodes."""
    all_pois: list[dict] = []
    async with httpx.AsyncClient() as client:
        for code in city_codes:
            resp = await client.get(
                f"{AMAP_BASE}/place/text",
                params={
                    "keywords": keywords,
                    "city": code,
                    "types": types,
                    "output": "JSON",
                    "offset": page_size,
                    "key": api_key,
                },
            )
            data = resp.json()
            if data.get("status") == "1":
                all_pois.extend(data.get("pois", []))
    return all_pois


async def get_driving_time_batch(
    origins: list[tuple[float, float]],
    dest: tuple[float, float],
    api_key: str,
) -> list[Optional[int]]:
    """Return driving times (minutes) from multiple origins to one destination.
    Uses /v3/distance which accepts up to 100 origin points per call.
    Returns list aligned with origins; None on individual failure.
    """
    if not origins:
        return []
    origins_str = "|".join(f"{lng},{lat}" for lat, lng in origins)
    dest_str = f"{dest[1]},{dest[0]}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{AMAP_BASE}/distance",
            params={"origins": origins_str, "destination": dest_str, "type": "1", "key": api_key},
        )
        data = resp.json()
    if data.get("status") != "1":
        return [None] * len(origins)
    results = data.get("results", [])
    out: list[Optional[int]] = []
    for item in results:
        duration = item.get("duration")
        out.append(int(duration) // 60 if duration is not None else None)
    # pad in case API returns fewer results than origins
    while len(out) < len(origins):
        out.append(None)
    return out


async def get_driving_time(
    origin: tuple[float, float],
    dest: tuple[float, float],
    api_key: str,
) -> Optional[int]:
    """Return driving time in minutes, or None on failure. origin/dest are (lat, lng)."""
    o = f"{origin[1]},{origin[0]}"
    d = f"{dest[1]},{dest[0]}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{AMAP_BASE}/direction/driving",
            params={"origin": o, "destination": d, "key": api_key},
        )
        data = resp.json()
        if data.get("status") == "1":
            paths = data.get("route", {}).get("paths", [])
            if paths:
                return int(paths[0]["duration"]) // 60
    return None


async def check_transit_reachable(
    origin: tuple[float, float],
    dest: tuple[float, float],
    city_code: str,
    api_key: str,
    max_minutes: int = 120,
) -> bool:
    """Return True if dest reachable by public transit within max_minutes."""
    o = f"{origin[1]},{origin[0]}"
    d = f"{dest[1]},{dest[0]}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{AMAP_BASE}/direction/transit/integrated",
            params={"origin": o, "destination": d, "city": city_code, "key": api_key},
        )
        data = resp.json()
        if data.get("status") == "1":
            transits = data.get("route", {}).get("transits", [])
            if transits:
                return int(transits[0]["duration"]) // 60 <= max_minutes
    return False


class AmapClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def get_district_codes(self, city_names: list[str]) -> dict[str, str]:
        return await get_district_codes(city_names, api_key=self.api_key)

    @traceable(name="amap_search_pois")
    async def search_pois(self, city_codes: list[str], keywords: str = "景点") -> list[dict]:
        return await search_pois(city_codes, keywords, api_key=self.api_key)

    @traceable(name="amap_driving_time_batch")
    async def get_driving_time_batch(self, origins: list[tuple], dest: tuple) -> "list[int | None]":
        return await get_driving_time_batch(origins, dest, api_key=self.api_key)

    async def get_driving_time(self, origin: tuple, dest: tuple) -> "int | None":
        return await get_driving_time(origin, dest, api_key=self.api_key)

    async def check_transit_reachable(self, origin: tuple, dest: tuple, city_code: str, max_minutes: int = 120) -> bool:
        return await check_transit_reachable(origin, dest, city_code, api_key=self.api_key, max_minutes=max_minutes)
