"""Midpoint composite chart built from two validated natal results."""
from .errors import ChartError
from .rules import aspects, house_for, position

COMPOSITE_RULE_VERSION = "composite-midpoint-v1"
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


def calculate_composite(payload):
    from .engine import calculate_chart
    if not isinstance(payload, dict) or set(payload) != {"person_a", "person_b"}:
        raise ChartError("INVALID_INPUT", "person_a와 person_b 두 출생 정보만 전달해 주세요.")
    charts = {}
    for key in ("person_a", "person_b"):
        try:
            charts[key] = calculate_chart(payload[key], require_known_time=True)
        except ChartError as error:
            details = dict(error.details or {})
            details["person"] = key
            raise ChartError(error.code, str(error), details) from None
    a, b = charts["person_a"], charts["person_b"]
    composite = calculate_composite_from(a, b)
    lat = (a["normalized"]["latitude"] + b["normalized"]["latitude"]) / 2
    lon = midpoint(a["normalized"]["longitude"] % 360, b["normalized"]["longitude"] % 360)
    lon = lon - 360 if lon > 180 else lon
    return {"status": "calculated", "calculation_status": "success", "rule_version": COMPOSITE_RULE_VERSION,
            "person_a": a, "person_b": b,
            "composite": {**composite, "sect": None,
                          "input": {"date": "Composite", "time": "", "place": "두 차트의 미드포인트"},
                          "normalized": {"latitude": lat, "longitude": lon, "offset": "", "utc": "—", "timezone": "—"},
                          "settings": {**a["settings"], "aspect_rule": COMPOSITE_RULE_VERSION},
                          "metadata": {"engine": a["metadata"]["engine"], "engine_version": a["metadata"]["engine_version"]}},
            "settings": {"method": "midpoint", "houses": "cusp midpoints (order-preserving)",
                         "note": "천체·각도·커스프는 두 네이털 황경의 짧은 호 미드포인트입니다. 역행·주야는 정의되지 않습니다."}}
