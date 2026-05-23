from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class POISource:
    platform: str               # "xiaohongshu" | "mafengwo" | "qyer"
    mention_count: int
    llm_credibility: float      # 0-1; low = ad-like content
    has_negative_reviews: bool  # True = more trustworthy


@dataclass
class POI:
    poi_id: str
    name: str
    coords: tuple[float, float]     # (lat, lng)
    category: str
    tags: list[str]                 # LLM-inferred from description, e.g. ["旅拍", "徒步"]
    desc: str
    amap_rating: float
    sources: list[POISource]
    mention_count: int              # total across all platforms
    platform_count: int
    confidence: str                 # "high" | "medium" | "low"


@dataclass
class Flight:
    platform: str
    depart_airport: str
    arrive_airport: str
    price: int                      # CNY, one-way per person
    flight_no: str
    depart_time: datetime


@dataclass
class FlightPair:
    pair_id: str                    # UUID
    outbound: Flight
    return_flight: Flight
    total_price: int                # outbound + return per person; actual cost = total_price × travelers


@dataclass
class DayPlan:
    day: int
    pois: list[POI]
    transport_note: str             # grounded in 高德 API data; LLM only formats wording
    estimated_travel_minutes: int


@dataclass
class ItineraryOption:
    option_id: str
    summary: str
    flights: Optional[FlightPair]
    days: list[DayPlan]
