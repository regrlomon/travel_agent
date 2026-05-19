# agent/graph.py
from langgraph.graph import StateGraph, END
from agent.state import TravelPlanState
import agent.nodes.parse_input as parse_input
import agent.nodes.discover_pois as discover_pois
import agent.nodes.scrape_flights as scrape_flights
import agent.nodes.plan_itinerary as plan_itinerary
import agent.nodes.compose_output as compose_output


def build_graph():
    g = StateGraph(TravelPlanState)

    g.add_node("parse_input", parse_input.run)
    g.add_node("discover_pois", discover_pois.run)
    g.add_node("scrape_flights", scrape_flights.run)
    g.add_node("plan_itinerary", plan_itinerary.run)
    g.add_node("compose_output", compose_output.run)

    g.set_entry_point("parse_input")

    # parse_input fans out to discover_pois and scrape_flights in parallel
    g.add_edge("parse_input", "discover_pois")
    g.add_edge("parse_input", "scrape_flights")

    # both converge into plan_itinerary
    g.add_edge("discover_pois", "plan_itinerary")
    g.add_edge("scrape_flights", "plan_itinerary")

    g.add_edge("plan_itinerary", "compose_output")
    g.add_edge("compose_output", END)

    return g.compile()
