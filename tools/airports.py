import json, os
import litellm

AIRPORT_MAP: dict[str, list[str]] = {
    "北京":  ["PEK", "PKX"],
    "上海":  ["PVG", "SHA"],
    "苏州":  ["PVG", "SHA", "NKG"],
    "无锡":  ["SHA", "NKG"],
    "南京":  ["NKG"],
    "杭州":  ["HGH"],
    "广州":  ["CAN"],
    "深圳":  ["SZX"],
    "成都":  ["CTU", "TFU"],
    "重庆":  ["CKG"],
    "武汉":  ["WUH"],
    "西安":  ["XIY"],
    "昆明":  ["KMG"],
    "拉萨":  ["LXA"],
    "稻城":  ["DCY"],
    "康定":  ["KGT"],
    "丽江":  ["LJG"],
    "三亚":  ["SYX"],
    "厦门":  ["XMN"],
    "青岛":  ["TAO"],
    "天津":  ["TSN"],
    "哈尔滨": ["HRB"],
    "长沙":  ["CSX"],
    "沈阳":  ["SHE"],
    "大连":  ["DLC"],
    "济南":  ["TNA"],
    "郑州":  ["CGO"],
    "合肥":  ["HFE"],
    "南昌":  ["KHN"],
    "福州":  ["FOC"],
    "贵阳":  ["KWE"],
    "南宁":  ["NNG"],
    "呼和浩特": ["HET"],
    "银川":  ["INC"],
    "西宁":  ["XNN"],
    "兰州":  ["LHW"],
    "乌鲁木齐": ["URC"],
}


class AirportsClient:
    def _static_lookup(self, city: str) -> list[str]:
        for key, airports in AIRPORT_MAP.items():
            if key in city or city in key:
                return airports
        return []

    async def lookup(self, city: str) -> list[str]:
        result = self._static_lookup(city)
        if result:
            return result
        return await self._llm_lookup(city)

    async def _llm_lookup(self, city: str) -> list[str]:
        prompt = (
            f'What are the IATA airport codes for traveling from/to "{city}" in China? '
            f'If no direct airport, list the nearest major airport(s). '
            f'Return only a JSON array of codes, no markdown. Example: ["PVG","SHA"]'
        )
        resp = await litellm.acompletion(
            model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        return json.loads(resp.choices[0].message.content)
