"""Midpoint composite chart built from two validated natal results."""
from .errors import ChartError
from .rules import aspect_candidates, aspect_entry, aspects, house_for, normalize_aspect_profile, position, separation_of
from .timeband import body_range, classify, orb_range, signed, sweep

# v2: when either birth time is unknown the composite has no angles or houses, bodies carry their possible
# range, and aspects are `stable` or `time_dependent` over both birth days (see calculate_composite_unknown).
COMPOSITE_RULE_VERSION = "composite-midpoint-v2"
COMPOSITE_BODIES = ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto",
                    "NorthNode", "SouthNode", "Lilith", "Chiron")


def midpoint(a, b):
    """Nearer (shorter-arc) midpoint; an exact 180° separation resolves toward a + 90°."""
    return (a + ((b - a + 180) % 360 - 180) / 2) % 360


def composite_cusps(cusps_a, cusps_b):
    # Each cusp is a shorter-arc midpoint, flipped by 180° when needed so houses stay in zodiac order.
    cusps = [midpoint(cusps_a[0], cusps_b[0])]
    for a, b in zip(cusps_a[1:], cusps_b[1:]):
        m = midpoint(a, b)
        options = [m, (m + 180) % 360]
        cusps.append(min(options, key=lambda value: (value - cusps[-1]) % 360))
    widths = [(cusps[(i + 1) % 12] - cusps[i]) % 360 for i in range(12)]
    if any(w <= 0 for w in widths) or abs(sum(widths) - 360) > 1e-7:
        raise ChartError("HOUSE_SYSTEM_UNAVAILABLE", "컴포지트 하우스 커스프 순서를 만들 수 없습니다.")
    return cusps


def calculate_composite_from(a, b):
    bodies_a = {body["id"]: body for body in a["bodies"]}
    bodies_b = {body["id"]: body for body in b["bodies"]}
    cusps = composite_cusps([h["longitude"] for h in sorted(a["houses"], key=lambda h: h["number"])],
                            [h["longitude"] for h in sorted(b["houses"], key=lambda h: h["number"])])
    bodies = []
    for body_id in COMPOSITE_BODIES:
        if body_id in bodies_a and body_id in bodies_b:
            lon = midpoint(bodies_a[body_id]["longitude"], bodies_b[body_id]["longitude"])
            if body_id == "SouthNode":
                north = next(item for item in bodies if item["id"] == "NorthNode")
                lon = (north["longitude"] + 180) % 360  # keep the nodal axis exact
            source = bodies_a[body_id]
            bodies.append({"id": body_id, "name": source["name"], "symbol": source["symbol"], **position(lon),
                           "house": house_for(lon, cusps), "direction": "not_applicable", "retrograde": None})
    angles_a = {angle["id"]: angle["longitude"] for angle in a["angles"]}
    angles_b = {angle["id"]: angle["longitude"] for angle in b["angles"]}
    def near(value, anchor):  # pick the midpoint side facing the matching cusp
        return value if abs((value - anchor + 180) % 360 - 180) <= 90 else (value + 180) % 360
    asc = near(midpoint(angles_a["ASC"], angles_b["ASC"]), cusps[0])
    mc = near(midpoint(angles_a["MC"], angles_b["MC"]), cusps[9])
    angles = [{"id": key, **position(lon)} for key, lon in (("ASC", asc), ("MC", mc), ("DSC", asc + 180), ("IC", mc + 180))]
    profile = a["settings"]["aspect_profile"]
    return {"bodies": bodies, "angles": angles, "houses": [{"number": i + 1, **position(lon)} for i, lon in enumerate(cusps)],
            "aspects": aspects(bodies, angles, profile)}


def calculate_composite_unknown(a, b, track_a, track_b):
    """Composite for at least one unknown birth time.

    With no midpoint flip, a composite body moves by (δA + δB)/2 and the two birth times are independent,
    so every range below is an exact interval sum. A body whose A–B separation can cross 180° within the
    ranges flips its midpoint by 180°; it is marked `midpoint_ambiguous` and left out of aspects.
    """
    bodies_a = {body["id"]: body for body in a["bodies"]}
    bodies_b = {body["id"]: body for body in b["bodies"]}

    def offsets(track, body_id, noon):
        return sweep([sample[body_id] for sample in track], noon) if track else (0.0, 0.0)

    bodies, spread = [], {}
    for body_id in COMPOSITE_BODIES:
        if body_id not in bodies_a or body_id not in bodies_b or body_id == "SouthNode":
            continue
        xa, xb = bodies_a[body_id]["longitude"], bodies_b[body_id]["longitude"]
        la, ha = offsets(track_a, body_id, xa)
        lb, hb = offsets(track_b, body_id, xb)
        gap = signed(xb - xa)
        ambiguous = not (-180 < gap + lb - ha and gap + hb - la < 180)
        lon = midpoint(xa, xb)
        spread[body_id] = ((la + lb) / 2, (ha + hb) / 2)
        source = bodies_a[body_id]
        bodies.append({"id": body_id, "name": source["name"], "symbol": source["symbol"], **position(lon),
                       "house": None, "direction": "not_applicable", "retrograde": None, "midpoint_ambiguous": ambiguous,
                       "time_range": body_range(lon, *spread[body_id])})
    north = next((item for item in bodies if item["id"] == "NorthNode"), None)
    if north and "SouthNode" in bodies_a:
        lon = (north["longitude"] + 180) % 360  # keep the nodal axis exact
        spread["SouthNode"] = spread["NorthNode"]
        bodies.append({**north, "id": "SouthNode", "name": bodies_a["SouthNode"]["name"], "symbol": bodies_a["SouthNode"]["symbol"],
                       **position(lon), "time_range": body_range(lon, *spread["NorthNode"])})

    profile = normalize_aspect_profile(a["settings"]["aspect_profile"])
    usable = [body for body in bodies if not body["midpoint_ambiguous"]]
    output = []
    for x, y, group, name, target, allowed in aspect_candidates(usable, [], profile):
        # composite X − Y moves by ((δXa − δYa) + (δXb − δYb)) / 2, each person's part over their own day
        da = sweep([signed(s[x["id"]] - s[y["id"]]) for s in track_a], signed(bodies_a[x["id"]]["longitude"] - bodies_a[y["id"]]["longitude"])) if track_a else (0.0, 0.0)
        db = sweep([signed(s[x["id"]] - s[y["id"]]) for s in track_b], signed(bodies_b[x["id"]]["longitude"] - bodies_b[y["id"]]["longitude"])) if track_b else (0.0, 0.0)
        low, high = orb_range(signed(x["longitude"] - y["longitude"]), (da[0] + db[0]) / 2, (da[1] + db[1]) / 2, target)
        stability = classify(low, high, allowed)
        if stability is None:
            continue
        separation = separation_of(x["longitude"], y["longitude"])
        entry = aspect_entry(x, y, group, name, target, allowed, separation, profile)
        entry.update({"stability": stability, "orb_range": [low, high], "in_orb_at_representative": abs(separation - target) <= allowed})
        output.append(entry)
    output.sort(key=lambda item: (item["stability"] == "time_dependent", item["orb"]))
    return {"bodies": bodies, "angles": [], "houses": [], "aspects": output}


def calculate_composite(payload):
    from .engine import calculate_chart
    if not isinstance(payload, dict) or set(payload) != {"person_a", "person_b"}:
        raise ChartError("INVALID_INPUT", "person_a와 person_b 두 출생 정보만 전달해 주세요.")
    from .engine import unknown_day_track
    charts, tracks = {}, {}
    for key in ("person_a", "person_b"):
        try:
            charts[key] = calculate_chart(payload[key])
            unknown = charts[key]["normalized"]["time_accuracy"] == "unknown"
            tracks[key] = unknown_day_track(payload[key], [b for b in COMPOSITE_BODIES if b != "SouthNode"]) if unknown else None
        except ChartError as error:
            details = dict(error.details or {})
            details["person"] = key
            raise ChartError(error.code, str(error), details) from None
    a, b = charts["person_a"], charts["person_b"]
    # Midpoints of differently defined points (house systems, node or Lilith variants, orb rules) mean nothing.
    mismatched = [key for key in ("house_system", "node_mode", "lilith_mode", "aspect_profile") if a["settings"][key] != b["settings"][key]]
    if mismatched:
        raise ChartError("INVALID_INPUT", "컴포지트는 두 차트의 하우스·노드·릴리스·어스펙트 설정이 같아야 합니다.", {"fields": mismatched})
    blind = tracks["person_a"] is not None or tracks["person_b"] is not None
    composite = calculate_composite_unknown(a, b, tracks["person_a"], tracks["person_b"]) if blind else calculate_composite_from(a, b)
    lat = (a["normalized"]["latitude"] + b["normalized"]["latitude"]) / 2
    lon = midpoint(a["normalized"]["longitude"] % 360, b["normalized"]["longitude"] % 360)
    lon = lon - 360 if lon > 180 else lon
    return {"status": "calculated", "calculation_status": "success", "rule_version": COMPOSITE_RULE_VERSION,
            "person_a": a, "person_b": b, "time_accuracy": {key: charts[key]["normalized"]["time_accuracy"] for key in charts},
            "composite": {**composite, "sect": None,
                          "input": {"date": "Composite", "time": "", "place": "두 차트의 미드포인트"},
                          "normalized": {"latitude": lat, "longitude": lon, "offset": "", "utc": "—", "timezone": "—"},
                          "settings": {**a["settings"], "aspect_rule": COMPOSITE_RULE_VERSION},
                          "metadata": {"engine": a["metadata"]["engine"], "engine_version": a["metadata"]["engine_version"]}},
            "settings": {"method": "midpoint", "houses": "not_calculated (birth time unknown)" if blind else "cusp midpoints (order-preserving)",
                         "note": ("천체는 두 네이털 황경의 짧은 호 미드포인트이며, 생시 미상인 사람이 있어 각도점·하우스는 계산하지 않았습니다. "
                                  "천체 범위와 어스펙트 안정성은 두 출생일 전체로 판정했습니다. 역행·주야는 정의되지 않습니다.") if blind else
                                 "천체·각도·커스프는 두 네이털 황경의 짧은 호 미드포인트입니다. 역행·주야는 정의되지 않습니다."}}
