# LangSmith Observability Integration

**Date:** 2026-05-23  
**Status:** Approved

## Problem

Current observability is blind: no visibility into LLM prompt/response content, token usage, node latency, or error traces. Debugging requires reading raw logs; there is no structured way to collect eval data.

## Goals

1. Full chain tracing — from API request to `done` SSE event, covering every graph node and every LLM call
2. Traces searchable by `job_id` for fast debugging
3. Successful jobs auto-collected into a LangSmith dataset for future eval/regression

## Non-Goals

- Custom eval runners (out of scope for now; dataset collection enables this later)
- Multi-provider LLM routing (only DeepSeek in use)
- Separate dev/prod projects (single project with `env:dev` / `env:prod` tags)

## Architecture

### LLM Wrapper Replacement

Replace `litellm.acompletion` with `langchain_openai.ChatOpenAI`. DeepSeek exposes an OpenAI-compatible API, so only `base_url` needs to be set.

New file `agent/llm.py` exposes a factory function:

```python
# agent/llm.py
import os
from langchain_openai import ChatOpenAI

def get_llm(temperature: float = 0.2) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("LLM_MODEL", "deepseek-chat"),
        base_url=os.getenv("LLM_API_BASE", "https://api.deepseek.com/v1"),
        api_key=os.getenv("LLM_API_KEY"),
        temperature=temperature,
    )
```

Each node replaces:
```python
# before
resp = await litellm.acompletion(model=..., messages=[...], temperature=...)
content = resp.choices[0].message.content

# after
llm = get_llm(temperature=...)
msg = await llm.ainvoke([HumanMessage(content=prompt)])
content = msg.content
```

`llm_config.yaml` is deleted. LLM configuration moves entirely into `.env`.

### Tracing — Environment Variables

LangGraph has built-in LangSmith integration that activates via env vars alone. No code instrumentation needed for node-level or LLM-level spans.

```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__xxxxxxxx
LANGCHAIN_PROJECT=travel-agent
LANGCHAIN_TAGS=env:dev          # change to env:prod in production
```

Resulting trace shape per job:

```
<job_id> (root)
├── collect_intent
│   └── ChatOpenAI (prompt / response / tokens / latency)
├── parse_input
│   └── ChatOpenAI
├── discover_pois
├── scrape_flights
├── plan_itinerary
│   ├── ChatOpenAI  (_phase1_select)
│   └── ChatOpenAI  (_phase2_generate × N plans)
└── compose_output
    └── ChatOpenAI
```

### job_id Correlation

`_build_config()` in `worker/tasks.py` injects `job_id` into LangSmith metadata so every trace is searchable by job:

```python
def _build_config(job_id: str) -> dict:
    return {
        "configurable": {"thread_id": job_id, "tools": build_tools()},
        "metadata": {"job_id": job_id},
        "tags": [os.getenv("LANGCHAIN_TAGS", "env:dev")],
    }
```

### Dataset Auto-Collection

After each successful job (no errors, `type == "done"`), `worker/tasks.py` calls the LangSmith SDK to create a dataset example:

```python
from langsmith import Client as LangSmithClient

LANGSMITH_DATASET = "travel-agent-traces"
_ls_client = LangSmithClient()

def _auto_add_to_dataset(job_id: str, initial_state: dict, result: dict):
    try:
        try:
            dataset = _ls_client.read_dataset(dataset_name=LANGSMITH_DATASET)
        except Exception:
            dataset = _ls_client.create_dataset(LANGSMITH_DATASET)

        _ls_client.create_example(
            inputs={
                "destination":   initial_state.get("destination"),
                "origin":        initial_state.get("origin"),
                "duration_days": initial_state.get("duration_days"),
                "interests":     initial_state.get("interests", []),
            },
            outputs={
                "itineraries_count": len(result.get("itineraries", [])),
                "warnings":          result.get("warnings", []),
                "errors":            result.get("errors", []),
            },
            metadata={"job_id": job_id},
            dataset_id=dataset.id,
        )
    except Exception:
        logger.warning("[job=%s] LangSmith dataset write failed, skipping", job_id)
```

Failures in dataset write are swallowed — a LangSmith outage must never affect job execution.

`_handle_result` signature changes to accept `initial_state`:

```python
def _handle_result(job_id: str, initial_state: dict, result: dict): ...
```

## File Change Summary

| File | Change |
|------|--------|
| `agent/llm.py` | New — ChatOpenAI factory |
| `agent/__init__.py` | Remove litellm init; keep `extract_json` only |
| `agent/nodes/collect_intent.py` | Switch to `get_llm()` + `ainvoke` |
| `agent/nodes/parse_input.py` | Switch to `get_llm()` + `ainvoke` |
| `agent/nodes/plan_itinerary.py` | Switch to `get_llm()` + `ainvoke` |
| `agent/nodes/compose_output.py` | Switch to `get_llm()` + `ainvoke` |
| `worker/tasks.py` | Add metadata to config; add `_auto_add_to_dataset`; thread `initial_state` through `_handle_result` |
| `requirements.txt` | Replace `litellm` with `langchain-openai` + `langsmith` |
| `.env.example` | Add 4 LangSmith env vars |
| `llm_config.yaml` | Delete |

## Dependencies

```diff
- litellm>=1.40.0
+ langchain-openai>=0.1.0
+ langsmith>=0.1.0
```

## Configuration

```bash
# New required env vars
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__xxxxxxxx
LANGCHAIN_PROJECT=travel-agent
LANGCHAIN_TAGS=env:dev
```

## Error Handling

- LangSmith tracing failures are silently ignored by the LangChain SDK — job execution is never blocked
- Dataset write failures are caught and logged as warnings — no impact on job result
- LLM call failures surface as exceptions, same behavior as before

## Testing Approach

Existing node unit tests mock the LLM. After the switch, mocks change from `litellm.acompletion` to `langchain_openai.ChatOpenAI.ainvoke`. Test logic (input/output assertions) is unchanged.

LangSmith calls in `_auto_add_to_dataset` should be mocked in `test_worker.py` to avoid real API calls during CI.
