import json, os
import litellm
from tools.flight_tool.scraper import CITY_CODES

# city name → city-level IATA (与 flight scraper 保持一致)
AIRPORT_MAP: dict[str, str] = {
    "北京": "BJS", "上海": "SHA", "苏州": "SHA", "无锡": "SHA",
    "南京": "NKG", "杭州": "HGH", "广州": "CAN", "深圳": "SZX",
    "成都": "CTU", "重庆": "CKG", "武汉": "WUH", "西安": "XIY",
    "昆明": "KMG", "拉萨": "LXA", "稻城": "DCY", "康定": "KGT",
    "丽江": "LJG", "三亚": "SYX", "厦门": "XMN", "青岛": "TAO",
    "天津": "TSN", "哈尔滨": "HRB", "长沙": "CSX", "沈阳": "SHE",
    "大连": "DLC", "济南": "TNA", "郑州": "CGO", "合肥": "HFE",
    "南昌": "KHN", "福州": "FOC", "贵阳": "KWE", "南宁": "NNG",
    "呼和浩特": "HET", "银川": "INC", "西宁": "XNN", "兰州": "LHW",
    "乌鲁木齐": "URC",
}


class AirportsClient:
    def _static_lookup(self, city: str) -> list[str]:
        for key, code in AIRPORT_MAP.items():
            if key in city or city in key:
                return [code]
        # 再查 CITY_CODES（已覆盖更多城市）
        for name, code in CITY_CODES.items():
            if name in city or city in name:
                return [code]
        return []

    async def lookup(self, city: str) -> list[str]:
        result = self._static_lookup(city)
        if result:
            return result
        return await self._llm_lookup(city)

    async def _llm_lookup(self, city: str) -> list[str]:
        prompt = (
            f'What is the city-level IATA code for "{city}" in China used in flight search systems? '
            f'For example: 北京→BJS, 上海→SHA, 成都→CTU. '
            f'Return only a JSON array with one code, no markdown. Example: ["CTU"]'
        )
        resp = await litellm.acompletion(
            model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        return json.loads(resp.choices[0].message.content)
