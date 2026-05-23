from typing import TypedDict, Optional
from datetime import date
from models import POI, FlightPair, ItineraryOption


class TravelPlanState(TypedDict, total=False):
    # ── Raw input from API ──────────────────────────────────────────────
    raw_message: str              # user's first message, passed to collect_intent
    destination: str
    origin: str
    duration_days: int
    travelers: int
    transport_mode: str           # "self_drive" | "public_transit" | "mixed"
    difficulty_level: str         # "easy" | "medium" | "hard"
    interests: list[str]
    depart_date: Optional[str]    # ISO date string or None

    # ── Written by collect_intent ───────────────────────────────────────
    origin_airports: list[str]    # already exists in state, now written by collect_intent

    # ── Written by human_review (moved to after plan_itinerary) ─────────
    selected_option_id: str | None   # which plan the user chose ("A", "B", etc.)
    adjustment_notes: str | None     # free-text adjustments from user

    # ── Written by ① parse_input ────────────────────────────────────────
    destination_region: str
    destination_amap_cities: list[str]
    destination_airports: list[str]
    depart_dates: list[date]
    search_keywords: list[str]

    # ── Written by ② discover_pois ──────────────────────────────────────
    pois: list[POI]
    travel_time_matrix: dict[str, int]

    # ── Written by ③ scrape_flights ─────────────────────────────────────
    flight_pairs: list[FlightPair]
    selected_dates: list[date]

    # ── Written by ④ plan_itinerary ─────────────────────────────────────
    itineraries: list[ItineraryOption]

    # ── Written by human_review (old fields, kept for compose_output) ───
    user_flight_choice: str | None
    user_poi_prefs: str | None

    # ── Global ───────────────────────────────────────────────────────────
    errors: list[str]
    warnings: list[str]
    job_id: str
