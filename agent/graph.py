from langgraph.graph import StateGraph, END
from agent.state import TravelPlanState
import agent.nodes.parse_input   as parse_input
import agent.nodes.discover_pois as discover_pois
import agent.nodes.scrape_flights as scrape_flights
import agent.nodes.human_review  as human_review
import agent.nodes.plan_itinerary as plan_itinerary
import agent.nodes.compose_output as compose_output


def build_compiled_graph(checkpointer):
    """Build and compile the LangGraph. checkpointer lifecycle is owned by the caller."""
    g = StateGraph(TravelPlanState)
    g.add_node("parse_input",    parse_input.run)
    g.add_node("discover_pois",  discover_pois.run)
    g.add_node("scrape_flights", scrape_flights.run)
    g.add_node("human_review",   human_review.run)
    g.add_node("plan_itinerary", plan_itinerary.run)
    g.add_node("compose_output", compose_output.run)

    g.set_entry_point("parse_input")
    g.add_edge("parse_input",    "discover_pois")
    g.add_edge("parse_input",    "scrape_flights")
    g.add_edge("discover_pois",  "human_review")
    g.add_edge("scrape_flights", "human_review")
    g.add_edge("human_review",   "plan_itinerary")
    g.add_edge("plan_itinerary", "compose_output")
    g.add_edge("compose_output", END)

    return g.compile(checkpointer=checkpointer)
