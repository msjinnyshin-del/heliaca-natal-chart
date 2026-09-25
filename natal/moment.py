"""Cast a full chart for an exact UTC instant at a given place (used by solar returns and progressions).

The engine takes civil input, so the instant is expressed as the place's local wall time with the matching
DST fold. Seconds are rounded to the nearest whole second; callers report the exact instant separately.
"""
from datetime import datetime, timedelta, timezone
import math

import swisseph as swe

from .errors import ChartError
from .time_input import load_zone

PLACE_KEYS = {"latitude", "longitude", "timezone", "place", "location_source"}
CHART_SETTING_KEYS = ("house_system", "node_mode", "lilith_mode", "aspect_profile")


def validate_place(place, label):
    if not isinstance(place, dict) or set(place) - PLACE_KEYS or not {"latitude", "longitude", "timezone"} <= set(place):
        raise ChartError("INVALID_INPUT", f"{label}는 latitude, longitude, timezone(선택: place, location_source)만 가질 수 있습니다.")
    if "place" in place and (not isinstance(place["place"], str) or len(place["place"]) > 300):
        raise ChartError("INVALID_INPUT", f"{label}의 place는 300자 이하 문자열이어야 합니다.")
    for key, limit in (("latitude", 90), ("longitude", 180)):
        value = place[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > limit:
            raise ChartError("INVALID_INPUT", f"{label}의 {key}는 ±{limit} 범위의 수여야 합니다.")
    load_zone(place["timezone"])
    return place


def utc_from_jd_tt(jd_tt):
    year, month, day, hour, minute, seconds = swe.jdet_to_utc(jd_tt, swe.GREG_CAL)
    # Inside a leap second Swiss returns 60.x; Python datetimes cannot hold it, so it rolls into the next
    # minute (the instant is still within one second of the true UTC label).
    whole = min(int(seconds), 59)
    return datetime(year, month, day, hour, minute, whole, tzinfo=timezone.utc) + timedelta(seconds=seconds - whole)


def round_to_second(moment):
    return (moment + timedelta(microseconds=500_000)).replace(microsecond=0)


def iso_utc(moment, digits=3):
    return moment.isoformat(timespec="milliseconds" if digits == 3 else "seconds").replace("+00:00", "Z")


def chart_at_utc(moment, place, natal_settings, allow_future=False):
    from .engine import calculate_chart
    local = round_to_second(moment).astimezone(load_zone(place["timezone"]))
    payload = {"date": local.strftime("%Y-%m-%d"), "time": local.strftime("%H:%M:%S"), "fold": local.fold,
               "timezone": place["timezone"], "latitude": place["latitude"], "longitude": place["longitude"],
               "place": place.get("place", ""), "time_accuracy": "reported",
               **{key: natal_settings[key] for key in CHART_SETTING_KEYS}}
    if "location_source" in place:
        payload["location_source"] = place["location_source"]
    return calculate_chart(payload, allow_future=allow_future)
