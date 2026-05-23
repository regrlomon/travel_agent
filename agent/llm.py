import os
from langchain_anthropic import ChatAnthropic


def get_llm(temperature: float = 0.2) -> ChatAnthropic:
    return ChatAnthropic(
        model=os.getenv("LLM_MODEL", "claude-sonnet-4-6"),
        base_url=os.getenv("LLM_API_BASE"),
        api_key=os.getenv("LLM_API_KEY"),
        temperature=temperature,
    )
