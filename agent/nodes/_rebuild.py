"""Shared helpers to reconstruct dataclasses after LangGraph/Redis checkpoint deserialization."""
import dataclasses
from datetime import datetime
from models import Flight, FlightPair, DayPlan, POI, ItineraryOption


def _to_dict(obj) -> dict:
    if isinstance(obj, dict):
        return obj
    try:
        return dataclasses.asdict(obj)
    except TypeError:
        return obj


def rebuild_flight(f) -> Flight:
    f = _to_dict(f)
    dt = f["depart_time"]
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    return Flight(
        platform=f.get("platform", ""),
        depart_airport=f.get("depart_airport", ""),
        arrive_airport=f.get("arrive_airport", ""),
        price=f.get("price", 0),
        flight_no=f.get("flight_no", ""),
        depart_time=dt,
    )


def rebuild_flight_pair(fd) -> FlightPair:
    fd = _to_dict(fd)
    return FlightPair(
        pair_id=fd.get("pair_id", ""),
        outbound=rebuild_flight(fd["outbound"]),
        return_flight=rebuild_flight(fd["return_flight"]),
        total_price=fd.get("total_price", 0),
    )


def rebuild_itineraries(raw: list) -> list[ItineraryOption]:
    result = []
    for item in raw:
        item = _to_dict(item)
        if not isinstance(item, dict):
            result.append(item)
            continue

        fp = None
        fd = item.get("flights")
        if fd:
            fp = rebuild_flight_pair(fd)

        days = []
        for d in item.get("days", []):
            d = _to_dict(d)
            if not isinstance(d, dict):
                days.append(d)
                continue
            pois = [
                POI(
                    poi_id=p.get("poi_id", ""),
                    name=p.get("name", ""),
                    coords=tuple(p.get("coords", [0.0, 0.0])),
                    category=p.get("category", ""),
                    tags=p.get("tags", []),
                    desc=p.get("desc", ""),
                    amap_rating=p.get("amap_rating", 0.0),
                    sources=p.get("sources", []),
                    mention_count=p.get("mention_count", 0),
                    platform_count=p.get("platform_count", 0),
                    confidence=p.get("confidence", "low"),
                ) if isinstance(_to_dict(p), dict) else p
                for p in d.get("pois", [])
            ]
            days.append(DayPlan(
                day=d.get("day", 0),
                pois=pois,
                transport_note=d.get("transport_note", ""),
                estimated_travel_minutes=d.get("estimated_travel_minutes", 0),
            ))

        result.append(ItineraryOption(
            option_id=item.get("option_id", ""),
            summary=item.get("summary", ""),
            flights=fp,
            days=days,
        ))
    return result


def rebuild_flight_pairs(raw: list) -> list[FlightPair]:
    result = []
    for item in raw:
        item = _to_dict(item)
        if not isinstance(item, dict):
            result.append(item)
            continue
        result.append(rebuild_flight_pair(item))
    return result
