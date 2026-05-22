from typing import TypedDict, Optional
from datetime import date
from models import POI, FlightPair, ItineraryOption


class TravelPlanState(TypedDict, total=False):
    # ── Raw input from API ──────────────────────────────────────────────
    destination: str
    origin: str
    duration_days: int
    travelers: int
    transport_mode: str           # "self_drive" | "public_transit" | "mixed"
    difficulty_level: str         # "easy" | "medium" | "hard"
    interests: list[str]
    depart_date: Optional[str]    # ISO date string or None

    # ── Written by ① parse_input ────────────────────────────────────────
    destination_region: str
    destination_amap_cities: list[str]
    origin_airports: list[str]
    destination_airports: list[str]
    depart_dates: list[date]
    search_keywords: list[str]

    # ── Written by ② discover_pois ──────────────────────────────────────
    pois: list[POI]
    travel_time_matrix: dict[tuple[str, str], int]

    # ── Written by ③ scrape_flights ─────────────────────────────────────
    flight_pairs: list[FlightPair]
    selected_dates: list[date]

    # ── Written by ④ plan_itinerary ─────────────────────────────────────
    itineraries: list[ItineraryOption]

    # ── Written by human_review (HITL #2) ────────────────────────────────
    user_flight_choice: str | None   # pair_id or natural-language description from user
    user_poi_prefs: str | None       # natural-language prefs injected into plan_itinerary prompt

    # ── Global ───────────────────────────────────────────────────────────
    errors: list[str]
    warnings: list[str]
    job_id: str
