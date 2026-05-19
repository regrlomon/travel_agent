import asyncio
import random
from playwright.async_api import async_playwright

XHS_SEARCH_URL = "https://www.xiaohongshu.com/search_result?keyword={keyword}&source=web_explore_feed"
NOTE_SELECTOR = ".note-item .content"


async def scrape_xhs_notes(keywords: list[str], max_notes_per_keyword: int = 10) -> list[dict]:
    """Scrape Xiaohongshu search results for each keyword. Returns list of {keyword, content}."""
    results: list[dict] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        for keyword in keywords:
            url = XHS_SEARCH_URL.format(keyword=keyword)
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            await asyncio.sleep(random.uniform(1.0, 3.0))   # anti-bot delay
            try:
                await page.wait_for_selector(NOTE_SELECTOR, timeout=10_000)
                elements = await page.query_selector_all(NOTE_SELECTOR)
                for el in elements[:max_notes_per_keyword]:
                    text = await el.inner_text()
                    results.append({"keyword": keyword, "content": text.strip()})
            except Exception:
                pass   # selector not found; XHS may have blocked — degrade gracefully
        await browser.close()
    return results
