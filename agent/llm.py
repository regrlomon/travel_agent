import os
from langchain_openai import ChatOpenAI


def get_llm(temperature: float = 0.2) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("LLM_MODEL", "deepseek-chat"),
        base_url=os.getenv("LLM_API_BASE", "https://api.deepseek.com/v1"),
        api_key=os.getenv("LLM_API_KEY"),
        temperature=temperature,
    )
