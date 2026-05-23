"""Reconstruct Pydantic models after LangGraph/Redis checkpoint deserialization."""
from models import FlightPair, ItineraryOption


def rebuild_itineraries(raw: list) -> list[ItineraryOption]:
    return [ItineraryOption.model_validate(i) if isinstance(i, dict) else i for i in raw]


def rebuild_flight_pairs(raw: list) -> list[FlightPair]:
    return [FlightPair.model_validate(i) if isinstance(i, dict) else i for i in raw]
