"""Transits: the sky at a chosen moment laid over a validated natal chart."""
from .errors import ChartError
from .rules import house_for

TRANSIT_RULE_VERSION = "transit-v1"
# Transit orbs are tight: an aspect is "in effect" only near exactness.
TRANSIT_ASPECTS = (("Conjunction", 0, 3), ("Sextile", 60, 2), ("Square", 90, 3), ("Trine", 120, 3),
                   ("Quincunx", 150, 1), ("Opposition", 180, 3))
TRANSITING = ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto", "Chiron", "NorthNode")
NATAL_TARGETS = TRANSITING
NATAL_ANGLES = ("ASC", "MC")
SLOW = {"Jupiter", "Saturn", "Uranus", "Neptune", "Pluto", "Chiron", "NorthNode"}


def transit_aspects(natal, sky):
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
            for name, target, orb_limit in TRANSIT_ASPECTS:
                orb = abs(separation - target)
                if orb > orb_limit:
                    continue
                # Natal points are fixed; the orb shrinks when the transit moves toward exactness.
                speed = t.get("speed") or 0.0
                rate = (1 if signed >= 0 else -1) * speed * (1 if separation >= target else -1)
                motion = "applying" if rate < 0 else "separating" if rate > 0 else "stationary"
                output.append({"a": n_id, "b": t_id, "natal": n_id, "transit": t_id, "name": name, "angle": target,
                               "separation": separation, "orb": orb, "allowed_orb": orb_limit, "motion": motion,
                               "slow": t_id in SLOW, "retrograde": t.get("direction") == "R",
                               "rule_version": TRANSIT_RULE_VERSION})
    return sorted(output, key=lambda item: (not item["slow"], item["orb"]))


def calculate_transits(payload):
    from .engine import calculate_chart
    if not isinstance(payload, dict) or set(payload) != {"natal", "moment"}:
        raise ChartError("INVALID_INPUT", "natal과 moment만 전달해 주세요.")
    moment = payload["moment"]
    if not isinstance(moment, dict) or set(moment) - {"date", "time", "timezone"}:
        raise ChartError("INVALID_INPUT", "moment는 date, time, timezone만 가질 수 있습니다.")
    natal = calculate_chart(payload["natal"])
    # Ambiguous DST moments resolve to the earlier offset (fold 0); a transit moment is not a birth record.
    sky_input = {"fold": 0, **moment, "latitude": natal["normalized"]["latitude"], "longitude": natal["normalized"]["longitude"],
                 "place": "transit", "house_system": natal["settings"]["house_system"], "node_mode": natal["settings"]["node_mode"]}
    try:
        sky = calculate_chart(sky_input, allow_future=True)
    except ChartError as error:
        details = dict(error.details or {})
        details["person"] = "moment"
        raise ChartError(error.code, f"트랜짓 시점: {error}", details) from None
    cusps = [house["longitude"] for house in sorted(natal["houses"], key=lambda house: house["number"])]
    in_houses = [{"body": body["id"], "house": house_for(body["longitude"], cusps)}
                 for body in sky["bodies"] if body["id"] in TRANSITING]
    return {"status": "calculated", "calculation_status": "success", "rule_version": TRANSIT_RULE_VERSION,
            "natal": natal, "transit": sky, "aspects": transit_aspects(natal, sky), "transit_houses": in_houses,
            "settings": {"orbs": {name: orb for name, _, orb in TRANSIT_ASPECTS},
                         "note": "트랜짓 황경은 지구 중심 좌표이며 관측 위치와 무관합니다. 접근/분리는 해당 시점의 속도로 판정합니다."}}
