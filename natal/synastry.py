"""Synastry: inter-chart aspects and house overlays between two validated natal results.

A person with an unknown birth time (spec §11) contributes no angles or houses. Their bodies are judged over
the whole local birth day: an inter-aspect is `stable` when it stays in orb all day and `time_dependent` when
it holds only for part of the day; overlays list every house the body passes through during the day.
"""
from .errors import ChartError
from .rules import PLANETS, house_for, separation_of
from .timeband import orb_range, sweep

SYNASTRY_RULE_VERSION = "synastry-v3"
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


def _sweep(track, body_id, noon):
    """(low, high) offsets from the representative longitude over the day; (0, 0) for a known time."""
    return (0.0, 0.0) if track is None else sweep([sample[body_id] for sample in track], noon)


def inter_aspects(chart_a, chart_b, track_a=None, track_b=None):
    timed = track_a is not None or track_b is not None
    output = []
    for a, kind_a in _points(chart_a):
        for b, kind_b in _points(chart_b):
            if kind_a == "angle" and kind_b == "angle":
                continue
            separation = separation_of(a["longitude"], b["longitude"])
            a_low, a_high = _sweep(track_a if kind_a != "angle" else None, a["id"], a["longitude"])
            b_low, b_high = _sweep(track_b if kind_b != "angle" else None, b["id"], b["longitude"])
            for name, target, base_orb in SYNASTRY_ASPECTS:
                if kind_a == "planet" and kind_b == "planet":
                    allowed = base_orb + (1 if {a["id"], b["id"]} & {"Sun", "Moon"} else 0)
                else:
                    allowed = min(base_orb, POINT_ORB)
                orb = abs(separation - target)
                entry = {"a": a["id"], "b": b["id"], "name": name, "angle": target, "separation": separation,
                         "orb": orb, "allowed_orb": allowed, "rule_version": SYNASTRY_RULE_VERSION}
                if timed:
                    low, high = orb_range(a["longitude"] - b["longitude"], a_low - b_high, a_high - b_low, target)
                    if low > allowed:
                        continue
                    stable = high <= allowed
                    entry.update({"stability": "stable" if stable else "time_dependent", "orb_range": [low, high],
                                  "in_orb_at_representative": orb <= allowed})
                elif orb > allowed:
                    continue
                else:
                    stable = True
                strength = ASPECT_WEIGHT[name] * (BODY_WEIGHT[a["id"]] * BODY_WEIGHT[b["id"]]) ** 0.5 * (1 - 0.6 * min(orb, allowed) / allowed)
                # A relation that depends on the unknown birth time is never ranked as a strong, settled finding.
                entry.update({"strength": round(strength, 4), "strong": stable and strength >= STRONG_THRESHOLD})
                output.append(entry)
    return sorted(output, key=lambda item: (item.get("stability") == "time_dependent", -item["strength"], item["orb"]))


def houses_swept(longitudes, cusps):
    """Houses entered, in order, along a sampled path (every cusp crossed between samples counts)."""
    seen = []

    def add(house):
        if house not in seen:
            seen.append(house)
    add(house_for(longitudes[0], cusps))
    for x, y in zip(longitudes, longitudes[1:]):
        step = (y - x + 180) % 360 - 180
        crossings = []
        for index, cusp in enumerate(cusps):
            # Half-open houses: moving forward, landing on a cusp enters its house; moving backward,
            # leaving a cusp enters the previous house and landing on one does not.
            travelled = (cusp - x) % 360 if step >= 0 else (x - cusp) % 360
            if (0 < travelled <= abs(step)) if step >= 0 else (0 <= travelled < abs(step)):
                crossings.append((travelled, index + 1 if step >= 0 else (index or 12)))
        for _, house in sorted(crossings):  # in the order the path meets them
            add(house)
        add(house_for(y, cusps))
    return seen


def house_overlays(owner, host, owner_track=None):
    """Where `owner`'s bodies fall in `host`'s houses (same cusp rule as natal); None when host has no birth time."""
    if not host["houses"]:
        return None
    cusps = [house["longitude"] for house in sorted(host["houses"], key=lambda house: house["number"])]
    if len(cusps) != 12:
        raise ChartError("HOUSE_SYSTEM_UNAVAILABLE", "하우스 오버레이에 필요한 12개 cusp가 없습니다.")
    points = {item["id"]: item for item in (*owner["bodies"], *owner["angles"])}
    output = []
    for body_id in OVERLAY_BODIES + ("ASC",):
        if body_id in points:
            house = house_for(points[body_id]["longitude"], cusps)
            item = {"body": body_id, "longitude": points[body_id]["longitude"], "house": house,
                    "strong": body_id in PERSONAL + ("ASC",)}
            if owner_track is not None:
                item["houses"] = houses_swept([sample[body_id] for sample in owner_track], cusps)
                item["stability"] = "stable" if len(item["houses"]) == 1 else "time_dependent"
            output.append(item)
    # Personal points first, then angular > succedent 5/8 > other houses.
    return sorted(output, key=lambda item: (not item["strong"], HOUSE_RANK.get(item["house"], 2), item["house"]))


def calculate_synastry(payload):
    from .engine import calculate_chart
    if not isinstance(payload, dict) or set(payload) != {"person_a", "person_b"}:
        raise ChartError("INVALID_INPUT", "person_a와 person_b 두 출생 정보만 전달해 주세요.")
    from .engine import unknown_day_track
    charts, tracks = {}, {}
    for key in ("person_a", "person_b"):
        try:
            charts[key] = calculate_chart(payload[key])
            unknown = charts[key]["normalized"]["time_accuracy"] == "unknown"
            tracks[key] = unknown_day_track(payload[key], OVERLAY_BODIES) if unknown else None
        except ChartError as error:
            details = dict(getattr(error, "details", None) or {})
            details["person"] = key
            raise ChartError(error.code, str(error), details) from None
    a, b = charts["person_a"], charts["person_b"]
    return {"status": "calculated", "calculation_status": "success", "rule_version": SYNASTRY_RULE_VERSION,
            "person_a": a, "person_b": b, "aspects": inter_aspects(a, b, tracks["person_a"], tracks["person_b"]),
            "overlays": {"a_in_b": house_overlays(a, b, tracks["person_a"]), "b_in_a": house_overlays(b, a, tracks["person_b"])},
            "time_accuracy": {key: charts[key]["normalized"]["time_accuracy"] for key in charts},
            "settings": {"strong_threshold": STRONG_THRESHOLD, "orbs": {name: orb for name, _, orb in SYNASTRY_ASPECTS}, "luminary_bonus": 1, "point_orb": POINT_ORB,
                         "points": list(PLANETS + POINTS + ANGLES)}}
