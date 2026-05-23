import re


def extract_json(text: str) -> str:
    """Strip markdown code fences from LLM output before JSON parsing."""
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    return match.group(1) if match else text.strip()
