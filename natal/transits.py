"""Transits: the sky at a chosen moment laid over a validated natal chart."""
import math

from .errors import ChartError
from .rules import house_for
from .timeband import classify, orb_range, signed as wrap, sweep

# v2: a natal chart without a birth time has no angles or houses; each natal body is judged over its whole
# birth day and an aspect is `stable` (in orb whatever the birth time) or `time_dependent`.
TRANSIT_RULE_VERSION = "transit-v2"
# Transit orbs are tight: an aspect is "in effect" only near exactness.
TRANSIT_ASPECTS = (("Conjunction", 0, 3), ("Sextile", 60, 2), ("Square", 90, 3), ("Trine", 120, 3),
                   ("Quincunx", 150, 1), ("Opposition", 180, 3))
TRANSITING = ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto", "Chiron", "NorthNode")
NATAL_TARGETS = TRANSITING
NATAL_ANGLES = ("ASC", "MC")
SLOW = {"Jupiter", "Saturn", "Uranus", "Neptune", "Pluto", "Chiron", "NorthNode"}


def _motion(difference, speed, target):
    """applying / separating for a transit at `difference` (transit − natal) moving at `speed`; natal points are fixed."""
    separation = abs(wrap(difference))
    rate = (1 if wrap(difference) >= 0 else -1) * speed * (1 if separation >= target else -1)
    return "applying" if rate < 0 else "separating" if rate > 0 else "stationary"


def _motion_over(signed_noon, low_n, high_n, speed, target):
    """Motion across every natal position of an unknown birth day; `time_dependent` when it changes."""
    start, end = signed_noon - high_n, signed_noon - low_n
    points = [start, end]
    for kink in (0.0, 180.0, target, -target):  # motion can only flip where the separation or the orb turns
        k = kink + 360 * math.ceil((start - kink) / 360)
        while k <= end:
            points.extend(p for p in (k - 1e-6, k + 1e-6) if start <= p <= end)
            k += 360
    motions = {_motion(point, speed, target) for point in points}
    return motions.pop() if len(motions) == 1 else "time_dependent"


def transit_aspects(natal, sky, natal_track=None):
    natal_points = {item["id"]: item for item in (*natal["bodies"], *natal["angles"])}
    moving = {item["id"]: item for item in sky["bodies"]}
    output = []
    for t_id in TRANSITING:
        t = moving.get(t_id)
        if t is None:
            continue
        for n_id in NATAL_TARGETS + NATAL_ANGLES:
            n = natal_points.get(n_id)
            if n is None:
                continue
            signed = (t["longitude"] - n["longitude"] + 180) % 360 - 180
            separation = abs(signed)
            low_n, high_n = sweep([sample[n_id] for sample in natal_track], n["longitude"]) if natal_track and n_id in natal_track[0] else (0.0, 0.0)
            for name, target, orb_limit in TRANSIT_ASPECTS:
                orb = abs(separation - target)
                timing = {}
                if natal_track:
                    # transit − natal runs over [signed − high_n, signed − low_n] as the birth time varies
                    low, high = orb_range(signed, -high_n, -low_n, target)
                    stability = classify(low, high, orb_limit)
                    if stability is None:
                        continue
                    timing = {"stability": stability, "orb_range": [low, high], "in_orb_at_representative": orb <= orb_limit}
                elif orb > orb_limit:
                    continue
                # Natal points are fixed; the orb shrinks when the transit moves toward exactness.
                speed = t.get("speed") or 0.0
                motion = _motion_over(signed, low_n, high_n, speed, target) if natal_track else _motion(signed, speed, target)
                output.append({"a": n_id, "b": t_id, "natal": n_id, "transit": t_id, "name": name, "angle": target,
                               "separation": separation, "orb": orb, "allowed_orb": orb_limit, "motion": motion,
                               "slow": t_id in SLOW, "retrograde": t.get("direction") == "R",
                               "rule_version": TRANSIT_RULE_VERSION, **timing})
    return sorted(output, key=lambda item: (item.get("stability") == "time_dependent", not item["slow"], item["orb"]))


def calculate_transits(payload):
    from .engine import calculate_chart
    if not isinstance(payload, dict) or set(payload) != {"natal", "moment"}:
        raise ChartError("INVALID_INPUT", "natal과 moment만 전달해 주세요.")
    moment = payload["moment"]
    if not isinstance(moment, dict) or set(moment) - {"date", "time", "timezone"}:
        raise ChartError("INVALID_INPUT", "moment는 date, time, timezone만 가질 수 있습니다.")
    from .engine import unknown_day_track
    natal = calculate_chart(payload["natal"])
    unknown = natal["normalized"]["time_accuracy"] == "unknown"
    natal_track = unknown_day_track(payload["natal"], NATAL_TARGETS) if unknown else None
    # Ambiguous DST moments resolve to the earlier offset (fold 0); a transit moment is not a birth record.
    # Only the instant and bodies of this chart are used; Whole Sign houses are defined at every latitude.
    sky_input = {"fold": 0, **moment, "latitude": natal["normalized"]["latitude"], "longitude": natal["normalized"]["longitude"],
                 "place": "transit", "house_system": "W", "node_mode": natal["settings"]["node_mode"]}
    try:
        sky = calculate_chart(sky_input, allow_future=True)
    except ChartError as error:
        details = dict(error.details or {})
        details["person"] = "moment"
        raise ChartError(error.code, f"트랜짓 시점: {error}", details) from None
    in_houses = None  # natal houses need a birth time
    if not unknown:
        cusps = [house["longitude"] for house in sorted(natal["houses"], key=lambda house: house["number"])]
        in_houses = [{"body": body["id"], "house": house_for(body["longitude"], cusps)}
                     for body in sky["bodies"] if body["id"] in TRANSITING]
    return {"status": "calculated", "calculation_status": "success", "rule_version": TRANSIT_RULE_VERSION,
            "natal": natal, "transit": sky, "aspects": transit_aspects(natal, sky, natal_track), "transit_houses": in_houses,
            "time_accuracy": natal["normalized"]["time_accuracy"],
            "settings": {"orbs": {name: orb for name, _, orb in TRANSIT_ASPECTS},
                         "note": "트랜짓 황경은 지구 중심 좌표이며 관측 위치와 무관합니다. 접근/분리는 해당 시점의 속도로 판정합니다."}}
