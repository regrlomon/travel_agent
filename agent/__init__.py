import os
import re
import litellm

if api_base := os.getenv("LLM_API_BASE"):
    litellm.api_base = api_base
if api_key := os.getenv("LLM_API_KEY"):
    litellm.api_key = api_key


def extract_json(text: str) -> str:
    """Strip markdown code fences from LLM output before JSON parsing."""
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    return match.group(1) if match else text.strip()
