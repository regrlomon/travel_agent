import httpx
from typing import Optional

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
