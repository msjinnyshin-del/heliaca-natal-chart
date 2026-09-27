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
from .rules import aspect_candidates, aspect_entry, aspects, house_for, normalize_aspect_profile, position
from .timeband import body_range, classify, path_orb_range, sweep

# v2: an unknown birth time moves the progressed instant with it (by ~1 day over the birth day). Progressed
# bodies then carry their range, solar-arc angles and houses are left out (they need the natal MC), and every
# aspect is `stable` or `time_dependent` along the shared birth-time path.
RULE_VERSION = "secondary-progression-v2"
TRACK_BODIES = ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto",
                "NorthNode", "SouthNode", "Lilith", "Chiron")
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


def _path_aspects(candidates, track_x, track_y, profile_entry):
    """Aspects judged along a shared birth-time path: x from track_x, y from track_y at the same sample."""
    output = []
    for x, y, extra, name, target, allowed in candidates:
        low, high = path_orb_range([sx[x["id"]] - sy[y["id"]] for sx, sy in zip(track_x, track_y)], target)
        stability = classify(low, high, allowed)
        if stability is None:
            continue
        entry = profile_entry(x, y, extra, name, target, allowed)
        entry.update({"stability": stability, "orb_range": [low, high], "in_orb_at_representative": entry["orb"] <= allowed})
        output.append(entry)
    return sorted(output, key=lambda item: (item["stability"] == "time_dependent", item["orb"]))


def calculate_progressions_unknown(payload, natal, target, moment):
    from .engine import ephemeris_track, unknown_day_jds
    settings = natal["settings"]
    birth_jds = unknown_day_jds(payload["natal"])
    target_jd = target["normalized"]["jd_tt"]
    if target_jd <= birth_jds[-1]:
        raise ChartError("INVALID_INPUT", "진행 기준 시점은 출생일 다음 날 이후여야 합니다(생시 미상).")
    progressed_jds = [jd + (target_jd - jd) / YEAR_DAYS for jd in birth_jds]
    natal_track = ephemeris_track(birth_jds, TRACK_BODIES, settings["node_mode"], settings["lilith_mode"])
    progressed_track = ephemeris_track(progressed_jds, TRACK_BODIES, settings["node_mode"], settings["lilith_mode"])
    # Representative: the natal noon instant, progressed like a known time.
    natal_utc = datetime_from(natal["normalized"]["utc"])
    target_utc = datetime_from(target["normalized"]["utc"])
    age_years = (target_utc - natal_utc).total_seconds() / 86400 / YEAR_DAYS
    progressed_utc = natal_utc + timedelta(days=age_years)
    place = {key: natal["input"][key] for key in ("latitude", "longitude", "timezone")}
    place["place"] = natal["input"].get("place", "")
    # Houses are dropped below; Whole Sign keeps a polar birthplace from failing on a house system it will not use.
    chart = chart_at_utc(progressed_utc, place, {**settings, "house_system": "W"}, allow_future=True)
    bodies = []
    for body in chart["bodies"]:
        if body["id"] in ("Fortune", "Spirit"):
            continue
        low, high = sweep([sample[body["id"]] for sample in progressed_track], body["longitude"])
        bodies.append({**body, "house": None, "altitude": None, "time_range": body_range(body["longitude"], low, high)})
    by_id = {body["id"]: body for body in bodies}
    natal_by_id = {body["id"]: body for body in natal["bodies"]}
    profile = normalize_aspect_profile(settings["aspect_profile"])
    internal = _path_aspects(aspect_candidates(bodies, [], profile), progressed_track, progressed_track,
                             lambda x, y, group, name, target_angle, allowed: aspect_entry(
                                 x, y, group, name, target_angle, allowed, abs((x["longitude"] - y["longitude"] + 180) % 360 - 180), profile))
    cross = [(by_id[p_id], natal_by_id[n_id], None, name, angle, ASPECT_ORB)
             for p_id in PROGRESSED if p_id in by_id for n_id in NATAL_TARGETS if n_id in natal_by_id
             for name, angle in PROGRESSED_ASPECTS]

    def cross_entry(p, n, _, name, angle, allowed):
        separation = abs((p["longitude"] - n["longitude"] + 180) % 360 - 180)
        return {"progressed": p["id"], "natal": n["id"], "a": n["id"], "b": p["id"], "name": name, "angle": angle,
                "separation": separation, "orb": abs(separation - angle), "allowed_orb": allowed, "rule_version": RULE_VERSION}
    progressed = {**chart, "bodies": bodies, "angles": [], "houses": [], "sect": None, "aspects": internal}
    progressed["normalized"] = {**chart["normalized"], "utc": iso_utc(progressed_utc)}
    return {"status": "calculated", "calculation_status": "success", "rule_version": RULE_VERSION, "time_accuracy": "unknown",
            "natal": natal, "progressed": progressed, "age_years": age_years, "solar_arc": None,
            "target": {"utc": target["normalized"]["utc"], "local": f"{target['input']['date']} {target['input']['time']}",
                       "timezone": target["normalized"]["timezone"]},
            "aspects": _path_aspects(cross, progressed_track, natal_track, cross_entry),
            "progressed_in_natal_houses": None,
            "settings": {"year_length_days": YEAR_DAYS, "key": "1일 = 평균 회귀년 1년", "angles": "not_calculated (birth time unknown)",
                         "aspect_orb": ASPECT_ORB, "excluded": ["ASC", "MC", "houses", "Fortune", "Spirit", "sect", "solar_arc"],
                         "note": "출생 시각을 몰라 진행 순간이 출생일 하루만큼 퍼집니다. 진행 천체는 그 범위를, 어스펙트는 같은 출생 시각 경로를 따라 판정했습니다. "
                                 "각도점·하우스는 네이털 MC가 필요해 계산하지 않았습니다."}}


def calculate_progressions(payload):
    from .engine import calculate_chart
    if not isinstance(payload, dict) or set(payload) != {"natal", "moment"}:
        raise ChartError("INVALID_INPUT", "natal과 moment만 전달해 주세요.")
    moment = payload["moment"]
    if not isinstance(moment, dict) or set(moment) - {"date", "time", "timezone"}:
        raise ChartError("INVALID_INPUT", "moment는 date, time, timezone만 가질 수 있습니다.")
    natal = calculate_chart(payload["natal"])
    # Only the instant and bodies of this chart are used; Whole Sign houses are defined at every latitude.
    target_input = {"fold": 0, **moment, "latitude": natal["normalized"]["latitude"], "longitude": natal["normalized"]["longitude"],
                    "place": "progression target", "house_system": "W", "node_mode": natal["settings"]["node_mode"]}
    try:
        target = calculate_chart(target_input, allow_future=True)
    except ChartError as error:
        raise ChartError(error.code, str(error), {**(error.details or {}), "person": "moment"}) from None
    if natal["normalized"]["time_accuracy"] == "unknown":
        return calculate_progressions_unknown(payload, natal, target, moment)
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

