# agent/nodes/human_review.py
# Placeholder — full implementation in Task 7
from agent.state import TravelPlanState
from langchain_core.runnables import RunnableConfig


async def run(state: TravelPlanState, config: RunnableConfig) -> dict:
    return {"user_flight_choice": None, "user_poi_prefs": None}
