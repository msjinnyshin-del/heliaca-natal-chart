"""Synastry: inter-chart aspects and house overlays between two validated natal results."""
from .errors import ChartError
from .rules import PLANETS, house_for

SYNASTRY_RULE_VERSION = "synastry-v2"
# Inter-chart orbs are conventionally tighter than natal ones; luminaries get +1°.
SYNASTRY_ASPECTS = (("Conjunction", 0, 6), ("Sextile", 60, 4), ("Square", 90, 5), ("Trine", 120, 5),
                    ("Quincunx", 150, 2), ("Opposition", 180, 6))
# Display ranking only (never classification): aspect x body weights x orb tightness.
ASPECT_WEIGHT = {"Conjunction": 1.0, "Opposition": 0.9, "Square": 0.85, "Trine": 0.8, "Sextile": 0.6, "Quincunx": 0.7}
BODY_WEIGHT = {"Sun": 1.0, "Moon": 1.0, "Venus": 0.9, "Mars": 0.9, "ASC": 0.9, "Mercury": 0.8, "MC": 0.7,
               "Jupiter": 0.7, "Saturn": 0.7, "Chiron": 0.5, "NorthNode": 0.5, "Uranus": 0.4, "Neptune": 0.4, "Pluto": 0.4}
STRONG_THRESHOLD = 0.45
PERSONAL = ("Sun", "Moon", "Mercury", "Venus", "Mars")
HOUSE_RANK = {1: 0, 4: 0, 7: 0, 10: 0, 5: 1, 8: 1}
POINT_ORB = 2.0
POINTS = ("Chiron", "NorthNode")
ANGLES = ("ASC", "MC")
OVERLAY_BODIES = PLANETS + POINTS


def _points(chart):
    bodies = {body["id"]: body for body in chart["bodies"]}
    angles = {angle["id"]: angle for angle in chart["angles"]}
    items = [(bodies[item], "planet") for item in PLANETS if item in bodies]
    items += [(bodies[item], "point") for item in POINTS if item in bodies]
    items += [(angles[item], "angle") for item in ANGLES if item in angles]
    return items


def inter_aspects(chart_a, chart_b):
    output = []
    for a, kind_a in _points(chart_a):
        for b, kind_b in _points(chart_b):
            if kind_a == "angle" and kind_b == "angle":
                continue
            separation = abs((a["longitude"] - b["longitude"] + 180) % 360 - 180)
            for name, target, base_orb in SYNASTRY_ASPECTS:
                if kind_a == "planet" and kind_b == "planet":
                    allowed = base_orb + (1 if {a["id"], b["id"]} & {"Sun", "Moon"} else 0)
                else:
                    allowed = min(base_orb, POINT_ORB)
                orb = abs(separation - target)
                if orb <= allowed:
                    strength = ASPECT_WEIGHT[name] * (BODY_WEIGHT[a["id"]] * BODY_WEIGHT[b["id"]]) ** 0.5 * (1 - 0.6 * orb / allowed)
                    output.append({"a": a["id"], "b": b["id"], "name": name, "angle": target, "separation": separation,
                                   "orb": orb, "allowed_orb": allowed, "strength": round(strength, 4),
                                   "strong": strength >= STRONG_THRESHOLD, "rule_version": SYNASTRY_RULE_VERSION})
    return sorted(output, key=lambda item: (-item["strength"], item["orb"]))


def house_overlays(owner, host):
    """Where `owner`'s bodies fall in `host`'s houses (same cusp rule as natal)."""
    cusps = [house["longitude"] for house in sorted(host["houses"], key=lambda house: house["number"])]
    if len(cusps) != 12:
        raise ChartError("HOUSE_SYSTEM_UNAVAILABLE", "하우스 오버레이에 필요한 12개 cusp가 없습니다.")
    points = {item["id"]: item for item in (*owner["bodies"], *owner["angles"])}
    output = []
    for body_id in OVERLAY_BODIES + ("ASC",):
        if body_id in points:
            house = house_for(points[body_id]["longitude"], cusps)
            output.append({"body": body_id, "longitude": points[body_id]["longitude"], "house": house,
                           "strong": body_id in PERSONAL + ("ASC",)})
    # Personal points first, then angular > succedent 5/8 > other houses.
    return sorted(output, key=lambda item: (not item["strong"], HOUSE_RANK.get(item["house"], 2), item["house"]))


def calculate_synastry(payload):
    from .engine import calculate_chart
    if not isinstance(payload, dict) or set(payload) != {"person_a", "person_b"}:
        raise ChartError("INVALID_INPUT", "person_a와 person_b 두 출생 정보만 전달해 주세요.")
    charts = {}
    for key in ("person_a", "person_b"):
        try:
            charts[key] = calculate_chart(payload[key], require_known_time=True)
        except ChartError as error:
            details = dict(getattr(error, "details", None) or {})
            details["person"] = key
            raise ChartError(error.code, str(error), details) from None
    a, b = charts["person_a"], charts["person_b"]
    return {"status": "calculated", "calculation_status": "success", "rule_version": SYNASTRY_RULE_VERSION,
            "person_a": a, "person_b": b, "aspects": inter_aspects(a, b),
            "overlays": {"a_in_b": house_overlays(a, b), "b_in_a": house_overlays(b, a)},
            "settings": {"strong_threshold": STRONG_THRESHOLD, "orbs": {name: orb for name, _, orb in SYNASTRY_ASPECTS}, "luminary_bonus": 1, "point_orb": POINT_ORB,
                         "points": list(PLANETS + POINTS + ANGLES)}}
