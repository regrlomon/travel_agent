import asyncio
import random
import re
from datetime import date, datetime
from playwright.async_api import async_playwright
from models import Flight

PLATFORMS = {
    "ctrip": {
        "calendar_url": "https://flights.ctrip.com/international/search/oneway-{origin}-{dest}",
        "calendar_selector": ".flight-calendar-day",
        "detail_url": "https://flights.ctrip.com/international/search/oneway-{origin}-{dest}?depdate={date}",
        "row_selector": ".flight-item",
    },
    "qunar": {
        "calendar_url": "https://flight.qunar.com/site/oneway.htm?searchDepartureAirport={origin}&searchArrivalAirport={dest}",
        "calendar_selector": ".price-calendar-cell",
        "detail_url": "https://flight.qunar.com/site/oneway.htm?searchDepartureAirport={origin}&searchArrivalAirport={dest}&searchDepartTime={date}",
        "row_selector": ".flight-item-wrap",
    },
}


async def scrape_price_calendar(origin: str, dest: str, platform: str) -> dict[date, int]:
    """Scrape price calendar page. Returns {date: lowest_price}."""
    cfg = PLATFORMS.get(platform, PLATFORMS["ctrip"])
    url = cfg["calendar_url"].format(origin=origin, dest=dest)
    prices: dict[date, int] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=30_000)
        await asyncio.sleep(random.uniform(1.0, 2.0))
        try:
            await page.wait_for_selector(cfg["calendar_selector"], timeout=10_000)
            cells = await page.query_selector_all(cfg["calendar_selector"])
            for cell in cells:
                d_str = await cell.get_attribute("data-date")
                p_str = await cell.get_attribute("data-price")
                if d_str and p_str:
                    try:
                        prices[date.fromisoformat(d_str)] = int(p_str)
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass
        await browser.close()
    return prices


async def scrape_flight_details(origin: str, dest: str, depart_date: date, platform: str) -> list[Flight]:
    """Scrape detailed flight list for a specific date. Returns list of Flight objects."""
    cfg = PLATFORMS.get(platform, PLATFORMS["ctrip"])
    url = cfg["detail_url"].format(origin=origin, dest=dest, date=depart_date.isoformat())
    flights: list[Flight] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=30_000)
        await asyncio.sleep(random.uniform(1.0, 2.5))
        try:
            await page.wait_for_selector(cfg["row_selector"], timeout=10_000)
            rows = await page.query_selector_all(cfg["row_selector"])
            for row in rows[:10]:
                text = await row.inner_text()
                price_match = re.search(r"[¥￥](\d+)", text)
                flight_match = re.search(r"([A-Z]{2}\d{4})", text)
                time_match = re.search(r"(\d{2}:\d{2})", text)
                if price_match and flight_match and time_match:
                    depart_time = datetime.combine(depart_date, datetime.strptime(time_match.group(1), "%H:%M").time())
                    flights.append(Flight(
                        platform=platform,
                        depart_airport=origin,
                        arrive_airport=dest,
                        price=int(price_match.group(1)),
                        flight_no=flight_match.group(1),
                        depart_time=depart_time,
                    ))
        except Exception:
            pass
        await browser.close()
    return flights
