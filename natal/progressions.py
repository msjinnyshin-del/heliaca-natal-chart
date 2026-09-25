"""Secondary progressions (`secondary-progression-v1`, spec §11).

Key: one day after birth stands for one mean tropical year of life (365.24219 days). Bodies are the ephemeris
at the progressed instant. Angles use solar arc in longitude: MC advances by the progressed Sun's arc, and
ASC/cusps follow from that MC at the birth latitude with the progressed date's true obliquity. Lots and sect
are not progressed.
"""
from datetime import datetime, timedelta
import math

import swisseph as swe

from .errors import ChartError
from .moment import iso_utc, chart_at_utc
from .rules import aspects, house_for, position

RULE_VERSION = "secondary-progression-v1"
YEAR_DAYS = 365.24219
ASPECT_ORB = 1.0
PROGRESSED_ASPECTS = (("Conjunction", 0), ("Sextile", 60), ("Square", 90), ("Trine", 120), ("Opposition", 180))
PROGRESSED = ("Sun", "Moon", "Mercury", "Venus", "Mars", "ASC", "MC")
NATAL_TARGETS = ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto", "ASC", "MC")


def datetime_from(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def solar_arc_angles(natal, progressed_sun, jd_tt, house_system):
    from .engine import checked_cusps, engine_session
    natal_points = {item["id"]: item["longitude"] for item in (*natal["bodies"], *natal["angles"])}
    arc = (progressed_sun - natal_points["Sun"]) % 360
    mc = (natal_points["MC"] + arc) % 360
    with engine_session():
        eps = swe.calc(jd_tt, swe.ECL_NUT, 0)[0][0]
        armc = math.degrees(math.atan2(math.sin(math.radians(mc)) * math.cos(math.radians(eps)), math.cos(math.radians(mc)))) % 360
        try:
            cusps, ascmc = swe.houses_armc(armc, natal["normalized"]["latitude"], eps, house_system.encode("ascii"))
        except swe.Error:
            raise ChartError("HOUSE_SYSTEM_UNAVAILABLE", "진행된 각도에서 하우스를 계산할 수 없습니다. 다른 하우스 시스템을 선택하세요.") from None
    checked_cusps(cusps, ascmc)
    angles = [{"id": key, **position(lon)} for key, lon in
              (("ASC", ascmc[0]), ("MC", ascmc[1]), ("DSC", ascmc[0] + 180), ("IC", ascmc[1] + 180))]
    return arc, angles, list(cusps)


def progressed_aspects(progressed, natal):
    moving = {item["id"]: item for item in (*progressed["bodies"], *progressed["angles"])}
    fixed = {item["id"]: item for item in (*natal["bodies"], *natal["angles"])}
    output = []
    for p_id in PROGRESSED:
        for n_id in NATAL_TARGETS:
            p, n = moving.get(p_id), fixed.get(n_id)
            if p is None or n is None:
                continue
            separation = abs((p["longitude"] - n["longitude"] + 180) % 360 - 180)
            for name, target in PROGRESSED_ASPECTS:
                orb = abs(separation - target)
                if orb <= ASPECT_ORB:  # a = natal (inner wheel), b = progressed (outer)
                    output.append({"progressed": p_id, "natal": n_id, "a": n_id, "b": p_id, "name": name, "angle": target,
                                   "separation": separation, "orb": orb, "allowed_orb": ASPECT_ORB, "rule_version": RULE_VERSION})
    return sorted(output, key=lambda item: item["orb"])


def calculate_progressions(payload):
    from .engine import calculate_chart
    if not isinstance(payload, dict) or set(payload) != {"natal", "moment"}:
        raise ChartError("INVALID_INPUT", "natal과 moment만 전달해 주세요.")
    moment = payload["moment"]
    if not isinstance(moment, dict) or set(moment) - {"date", "time", "timezone"}:
        raise ChartError("INVALID_INPUT", "moment는 date, time, timezone만 가질 수 있습니다.")
    natal = calculate_chart(payload["natal"], require_known_time=True)
    target_input = {"fold": 0, **moment, "latitude": natal["normalized"]["latitude"], "longitude": natal["normalized"]["longitude"],
                    "place": "progression target", "house_system": natal["settings"]["house_system"], "node_mode": natal["settings"]["node_mode"]}
    try:
        target = calculate_chart(target_input, allow_future=True)
    except ChartError as error:
        raise ChartError(error.code, str(error), {**(error.details or {}), "person": "moment"}) from None
    natal_utc = datetime_from(natal["normalized"]["utc"])
    target_utc = datetime_from(target["normalized"]["utc"])
    elapsed = (target_utc - natal_utc).total_seconds()
    if elapsed <= 0:
        raise ChartError("INVALID_INPUT", "진행 기준 시점은 출생 이후여야 합니다.")
    age_years = elapsed / 86400 / YEAR_DAYS
    progressed_utc = natal_utc + timedelta(days=age_years)
    place = {key: natal["input"][key] for key in ("latitude", "longitude", "timezone")}
    place["place"] = natal["input"].get("place", "")
    # The progressed instant always precedes the (≤2100) target, but may still be after "now" for a recent birth.
    chart = chart_at_utc(progressed_utc, place, natal["settings"], allow_future=True)
    sun = next(b for b in chart["bodies"] if b["id"] == "Sun")["longitude"]
    arc, angles, cusps = solar_arc_angles(natal, sun, chart["normalized"]["jd_tt"], natal["settings"]["house_system"])
    # altitude only served sect at the real instant; it means nothing for a progressed chart.
    bodies = [{**b, "house": house_for(b["longitude"], cusps), "altitude": None}
              for b in chart["bodies"] if b["id"] not in ("Fortune", "Spirit")]
    progressed = {**chart, "bodies": bodies, "angles": angles, "sect": None,
                  "houses": [{"number": i + 1, **position(lon)} for i, lon in enumerate(cusps)],
                  "aspects": aspects(bodies, angles, natal["settings"]["aspect_profile"])}
    progressed["normalized"] = {**chart["normalized"], "utc": iso_utc(progressed_utc)}
    natal_cusps = [h["longitude"] for h in sorted(natal["houses"], key=lambda h: h["number"])]
    return {"status": "calculated", "calculation_status": "success", "rule_version": RULE_VERSION,
            "natal": natal, "progressed": progressed, "age_years": age_years, "solar_arc": arc,
            "target": {"utc": target["normalized"]["utc"], "local": f"{target['input']['date']} {target['input']['time']}",
                       "timezone": target["normalized"]["timezone"]},
            "aspects": progressed_aspects(progressed, natal),
            "progressed_in_natal_houses": [{"body": b["id"], "house": house_for(b["longitude"], natal_cusps)}
                                           for b in (*bodies, *angles) if b["id"] not in ("SouthNode", "DSC", "IC")],
            "settings": {"year_length_days": YEAR_DAYS, "key": "1일 = 평균 회귀년 1년", "angles": "solar-arc-longitude",
                         "obliquity": "진행 시점의 진황도경사", "aspect_orb": ASPECT_ORB,
                         "excluded": ["Fortune", "Spirit", "sect"],
                         "note": "진행 천체는 출생 후 (나이×1일) 시점의 실제 천체력이며, 각도점은 태양 호(solar arc)만큼 MC를 옮겨 출생 위도에서 계산합니다."}}

