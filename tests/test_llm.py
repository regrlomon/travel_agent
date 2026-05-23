import pytest


def test_get_llm_respects_temperature(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")
    monkeypatch.setenv("LLM_API_BASE", "https://api.deepseek.com/v1")
    from agent.llm import get_llm
    llm = get_llm(temperature=0.7)
    assert llm.temperature == 0.7


def test_get_llm_default_temperature(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    from agent.llm import get_llm
    llm = get_llm()
    assert llm.temperature == 0.2
