from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class POISource(BaseModel):
    platform: str
    mention_count: int
    llm_credibility: float
    has_negative_reviews: bool


class POI(BaseModel):
    poi_id: str
    name: str
    coords: tuple[float, float]
    category: str
    tags: list[str] = []
    desc: str
    amap_rating: float
    sources: list[POISource] = []
    mention_count: int
    platform_count: int
    confidence: str


class Flight(BaseModel):
    platform: str
    depart_airport: str
    arrive_airport: str
    price: int
    flight_no: str
    depart_time: datetime


class FlightPair(BaseModel):
    pair_id: str
    outbound: Flight
    return_flight: Flight
    total_price: int


class DayPlan(BaseModel):
    day: int
    pois: list[POI] = []
    transport_note: str
    estimated_travel_minutes: int


class ItineraryOption(BaseModel):
    option_id: str
    summary: str
    flights: Optional[FlightPair] = None
    days: list[DayPlan] = []
