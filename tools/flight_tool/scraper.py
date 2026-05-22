"""
国内机票爬虫核心逻辑 - 携程 & 同程旅行（移动版）
所有函数均为参数化，不依赖全局配置。
"""

import re
from playwright.async_api import async_playwright, Browser

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)

CITY_CODES: dict[str, str] = {
    # 一线 / 超大城市
    "北京": "BJS", "上海": "SHA", "广州": "CAN", "深圳": "SZX",
    "成都": "CTU", "杭州": "HGH", "武汉": "WUH", "西安": "XIY",
    "重庆": "CKG", "南京": "NKG", "天津": "TSN", "青岛": "TAO",
    "厦门": "XMN", "昆明": "KMG", "长沙": "CSX", "郑州": "CGO",
    "哈尔滨": "HRB", "沈阳": "SHE", "大连": "DLC", "三亚": "SYX",
    "贵阳": "KWE", "南宁": "NNG", "福州": "FOC", "海口": "HAK",
    "合肥": "HFE", "长春": "CGQ", "太原": "TYN", "济南": "TNA",
    "石家庄": "SJW", "南昌": "KHN", "兰州": "LHW", "乌鲁木齐": "URC",
    # 华东
    "温州": "WNZ", "宁波": "NGB", "无锡": "WUX", "常州": "CZX",
    "南通": "NTG", "台州": "HYN", "舟山": "HSN", "黄山": "TXN",
    # 华南
    "珠海": "ZUH", "揭阳": "SWA", "湛江": "ZHA", "梅州": "MXZ",
    "惠州": "HUZ", "北海": "BHY", "柳州": "LZH", "桂林": "KWL",
    # 华中
    "宜昌": "YIH", "赣州": "KOW",
    # 华北
    "包头": "BAV", "呼和浩特": "HET", "锦州": "JNZ",
    # 东北
    "烟台": "YNT", "威海": "WEH", "牡丹江": "MDG", "佳木斯": "JMU",
    "齐齐哈尔": "NDG", "延吉": "YNJ", "满洲里": "NZH",
    "呼伦贝尔": "HLD",
    # 西北
    "银川": "INC", "西宁": "XNN", "敦煌": "DNH", "喀什": "KHG",
    "延安": "ENY",
    # 西南 / 高原
    "拉萨": "LXA", "丽江": "LJG", "西双版纳": "JHG",
    "张家界": "DYG", "九寨沟": "JZH", "稻城": "DCY",
    "神农架": "HPG",
}

_FLIGHT_PAT = re.compile(r'([A-Z][A-Z0-9]\d{3,5}|[0-9][A-Z]\d{3,5})')
_TIME_PAT   = re.compile(r'^\d{2}:\d{2}$')
_HHMM_PAT   = re.compile(r'\d{2}:\d{2}')


def _duration_minutes(dep: str, arr: str) -> int:
    dh, dm = int(dep[:2]), int(dep[3:])
    ah, am = int(arr[:2]), int(arr[3:])
    delta = (ah * 60 + am) - (dh * 60 + dm)
    return delta if delta >= 0 else delta + 1440


def _dedup(flights: list[dict]) -> list[dict]:
    best: dict[tuple, dict] = {}
    for f in flights:
        k = (f["dep"], f.get("dep_ap", ""), f["arr"], f.get("arr_ap", ""))
        if k not in best or f["price"] < best[k]["price"]:
            best[k] = f
    return sorted(best.values(), key=lambda x: x["dep"])


# ─────────────────────────────────────────────
# 同程旅行
# ─────────────────────────────────────────────

async def _parse_card_ly(card) -> dict | None:
    try:
        times = await card.query_selector_all(".time.fwb.fmtc")
        if len(times) < 2:
            return None
        dep_t = (await times[0].inner_text()).strip()
        arr_t = (await times[1].inner_text()).strip()
        if not _TIME_PAT.match(dep_t) or not _TIME_PAT.match(arr_t):
            return None
        if _duration_minutes(dep_t, arr_t) > 300:
            return None

        ports = await card.query_selector_all(".port")
        dep_ap = (await ports[0].inner_text()).strip() if len(ports) > 0 else ""
        arr_ap = (await ports[1].inner_text()).strip() if len(ports) > 1 else ""

        price_el = await card.query_selector(".price-num")
        if not price_el:
            return None
        price_str = re.sub(r'\D', '', (await price_el.inner_text()).strip())
        if not price_str:
            return None

        m = _FLIGHT_PAT.search(await card.inner_text())
        fno = m.group(1) if m else "?"
        return {"flight": fno, "price": int(price_str),
                "dep": dep_t, "dep_ap": dep_ap, "arr": arr_t, "arr_ap": arr_ap}
    except Exception:
        return None


async def fetch_ly(browser: Browser, departure: str, arrival: str, date: str) -> list[dict]:
    dep_code = CITY_CODES.get(departure, departure)
    arr_code = CITY_CODES.get(arrival, arrival)
    url = (
        f"https://m.ly.com/ft/retail/book1"
        f"?date={date}&backDate=&childticket=0,0&an=1&cn=0&baby=0"
        f"&fromCity={departure}&toCity={arrival}"
        f"&fromcitycode={dep_code}&fromCode={dep_code}"
        f"&tocitycode={arr_code}&toCode={arr_code}"
        f"&acn={arrival}&dcn={departure}&cabin=0&platcode=10060"
        f"&direct=0&frompage=HOME"
    )
    ctx = await browser.new_context(
        user_agent=MOBILE_UA,
        viewport={"width": 390, "height": 844},
        locale="zh-CN",
        ignore_https_errors=True,
    )
    page = await ctx.new_page()
    raw: list[dict] = []
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(8000)

        prev_count, no_new = 0, 0
        for _ in range(15):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1800)
            n = len(await page.query_selector_all("div[data-findex][data-cindex]"))
            if n == prev_count:
                no_new += 1
                if no_new >= 3:
                    break
            else:
                no_new = 0
            prev_count = n

        for card in await page.query_selector_all("div[data-findex][data-cindex]"):
            f = await _parse_card_ly(card)
            if f:
                raw.append(f)
    finally:
        await page.close()
        await ctx.close()

    return _dedup(raw)


# ─────────────────────────────────────────────
# 携程
# ─────────────────────────────────────────────

async def _parse_card_ctrip(card) -> dict | None:
    try:
        item_contents = await card.query_selector_all('[class*="FlightListCard_item-content"]')
        ic_texts = [(await el.inner_text()).strip() for el in item_contents]
        if '共享' in ic_texts:
            return None

        time_els = await card.query_selector_all('[class*="ListCardTime_time"]')
        name_els = await card.query_selector_all('[class*="ListCardTime_Name"]')
        if len(time_els) < 2:
            time_els = []
            for div in await card.query_selector_all('div'):
                t = (await div.inner_text()).strip()
                if _TIME_PAT.match(t):
                    time_els.append(div)
                    if len(time_els) == 2:
                        break
        if len(time_els) < 2:
            return None

        dep_m = _HHMM_PAT.search((await time_els[0].inner_text()).strip())
        arr_m = _HHMM_PAT.search((await time_els[1].inner_text()).strip())
        if not dep_m or not arr_m:
            return None
        dep_t, arr_t = dep_m.group(), arr_m.group()
        if _duration_minutes(dep_t, arr_t) > 300:
            return None

        dep_ap = (await name_els[0].inner_text()).strip() if len(name_els) > 0 else ""
        arr_ap = (await name_els[1].inner_text()).strip() if len(name_els) > 1 else ""

        price_el = await card.query_selector('[class*="PriceComponent_price__"]')
        if not price_el:
            return None
        price_str = re.sub(r'\D', '', (await price_el.inner_text()).strip())
        if not price_str:
            return None

        m = _FLIGHT_PAT.search(await card.inner_text())
        fno = m.group(1) if m else "?"
        return {"flight": fno, "price": int(price_str),
                "dep": dep_t, "dep_ap": dep_ap, "arr": arr_t, "arr_ap": arr_ap}
    except Exception:
        return None


async def fetch_ctrip(browser: Browser, departure: str, arrival: str, date: str) -> list[dict]:
    dep_code = CITY_CODES.get(departure, departure)
    arr_code = CITY_CODES.get(arrival, arrival)
    url = (
        f"https://m.ctrip.com/html5/flight/pages/first"
        f"?dcity={dep_code}&dcityName={departure}"
        f"&acity={arr_code}&acityName={arrival}"
        f"&ddate={date}&channel=10002021&regionType=DOMESTIC"
    )
    ctx = await browser.new_context(
        user_agent=MOBILE_UA,
        viewport={"width": 390, "height": 844},
        locale="zh-CN",
    )
    page = await ctx.new_page()
    raw: list[dict] = []
    seen: set = set()
    try:
        await page.goto("https://m.ctrip.com/html5/flight/swift/index",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(8000)

        no_new = 0
        seen_card_ids: set = set()
        for step in range(40):
            cards = await page.query_selector_all('[data-testid^="common-card-"]')
            new_cards = 0
            for card in cards:
                tid = await card.get_attribute('data-testid')
                if tid not in seen_card_ids:
                    seen_card_ids.add(tid)
                    new_cards += 1
                    f = await _parse_card_ctrip(card)
                    if f:
                        key = (f["dep"], f.get("dep_ap", ""), f["arr"], f.get("arr_ap", ""), f["price"])
                        if key not in seen:
                            seen.add(key)
                            raw.append(f)
            if new_cards == 0:
                no_new += 1
                if no_new >= 4:
                    break
            else:
                no_new = 0
            await page.evaluate(f"window.scrollTo(0, {(step + 1) * 700})")
            await page.wait_for_timeout(900)
    finally:
        await page.close()
        await ctx.close()

    return _dedup(raw)
