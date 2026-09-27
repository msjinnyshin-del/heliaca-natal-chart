"""Solar return (`solar-return-v1`, spec §11): the instant the Sun's apparent geocentric tropical longitude
returns to its natal value, charted for a location the user chooses.

`year` names the birthday whose return is wanted; the instant can fall a day either side of the calendar
birthday (and across New Year for late-December births).
"""
import swisseph as swe

from .errors import ChartError
from .moment import chart_at_utc, iso_utc, round_to_second, utc_from_jd_tt, validate_place
import math

from .rules import aspect_candidates, aspect_entry, house_for, normalize_aspect_profile, separation_of
from .time_input import load_zone
from .timeband import body_range, classify, path_orb_range, sweep

# v2: with an unknown birth time the natal Sun is only known to within its day's motion (~1°), so the return
# instant spreads over about a day. The return chart then has no angles or houses (they change completely in
# a day); bodies carry their range over the return window and aspects are `stable` or `time_dependent`.
RULE_VERSION = "solar-return-v2"
TRACK_BODIES = ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto",
                "NorthNode", "SouthNode", "Lilith", "Chiron")
SEARCH_DAYS = 3.0  # the Sun moves ~6 deg in the window, so exactly one crossing exists
TOLERANCE_DAYS = 1e-8  # ~1 ms


def _sun(jd_tt):
    from .engine import checked_calc
    return checked_calc(jd_tt, swe.SUN)[0][0]


def find_return(natal_longitude, seed_jd_tt):
    def offset(jd):
        return (_sun(jd) - natal_longitude + 180) % 360 - 180

    lo, hi = seed_jd_tt - SEARCH_DAYS, seed_jd_tt + SEARCH_DAYS
    if not offset(lo) < 0 < offset(hi):
        raise ChartError("CALCULATION_FAILED", "태양 귀환 시각을 탐색 구간에서 찾지 못했습니다.")
    while hi - lo > TOLERANCE_DAYS:
        mid = (lo + hi) / 2
        if offset(mid) < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def calculate_solar_return(payload):
    from .engine import calculate_chart, engine_session
    if not isinstance(payload, dict) or set(payload) != {"natal", "year", "location"}:
        raise ChartError("INVALID_INPUT", "natal, year, location(귀환 차트를 볼 장소)을 모두 전달해 주세요.")
    year, location = payload["year"], validate_place(payload["location"], "location")
    if type(year) is not int:
        raise ChartError("INVALID_INPUT", "year는 정수여야 합니다.")
    natal = calculate_chart(payload["natal"])
    unknown = natal["normalized"]["time_accuracy"] == "unknown"
    birth_year = int(natal["normalized"]["solar_date"][:4])
    if year <= birth_year:
        raise ChartError("INVALID_INPUT", "솔라 리턴 연도는 출생 연도 다음 해부터 선택할 수 있습니다.")
    if year > 2100:
        raise ChartError("UNSUPPORTED_DATE", "솔라 리턴은 2100년까지 지원합니다.")
    natal_sun = next(b for b in natal["bodies"] if b["id"] == "Sun")["longitude"]
    with engine_session():
        # Seed: the natal instant moved by whole mean tropical years; the root is within a day of it.
        seed = natal["normalized"]["jd_tt"] + (year - birth_year) * 365.24219
        exact_tt = find_return(natal_sun, seed)
        residual = abs((_sun(exact_tt) - natal_sun + 180) % 360 - 180) * 3600
        exact_utc = utc_from_jd_tt(exact_tt)
        window = None
        if unknown:
            from .engine import ephemeris_track, unknown_day_jds
            day = unknown_day_jds(payload["natal"])
            suns = ephemeris_track([day[0], day[-1]], ["Sun"])
            edges = [find_return(sun["Sun"], jd + (year - birth_year) * 365.24219) for sun, jd in zip(suns, (day[0], day[-1]))]
    try:
        # Unknown time drops the return houses, so Whole Sign keeps a polar location from failing on them.
        cast = {**natal["settings"], "house_system": "W"} if unknown else natal["settings"]
        chart = chart_at_utc(exact_utc, location, cast, allow_future=True)
    except ChartError as error:
        if error.code == "UNSUPPORTED_DATE":  # e.g. a late-December 2100 return that lands in 2101 locally
            raise ChartError("UNSUPPORTED_DATE", "이 연도의 귀환 순간이 지원 범위(2100년) 밖에 있습니다.") from None
        raise
    if unknown:
        # The Sun's return is monotonic in the birth instant, so the window's samples trace every possible return.
        steps = max(1, math.ceil((edges[1] - edges[0]) * 144))
        window_jds = [edges[0] + (edges[1] - edges[0]) * k / steps for k in range(steps + 1)]
        track = ephemeris_track(window_jds, TRACK_BODIES, natal["settings"]["node_mode"], natal["settings"]["lilith_mode"])
        bodies = []
        for body in chart["bodies"]:
            if body["id"] in ("Fortune", "Spirit"):
                continue
            low, high = sweep([sample[body["id"]] for sample in track], body["longitude"])
            bodies.append({**body, "house": None, "time_range": body_range(body["longitude"], low, high)})
        profile = normalize_aspect_profile(natal["settings"]["aspect_profile"])
        chart_aspects = []
        for x, y, group, name, target, allowed in aspect_candidates(bodies, [], profile):
            low, high = path_orb_range([sample[x["id"]] - sample[y["id"]] for sample in track], target)
            stability = classify(low, high, allowed)
            if stability is None:
                continue
            separation = separation_of(x["longitude"], y["longitude"])
            entry = aspect_entry(x, y, group, name, target, allowed, separation, profile)
            entry.update({"stability": stability, "orb_range": [low, high], "in_orb_at_representative": abs(separation - target) <= allowed})
            chart_aspects.append(entry)
        chart_aspects.sort(key=lambda item: (item["stability"] == "time_dependent", item["orb"]))
        chart = {**chart, "bodies": bodies, "angles": [], "houses": [], "sect": None, "aspects": chart_aspects}
        zone = load_zone(location["timezone"])
        window = {edge: {"utc": iso_utc(moment), "local": round_to_second(moment).astimezone(zone).replace(tzinfo=None).isoformat(timespec="seconds")}
                  for edge, moment in (("earliest", utc_from_jd_tt(edges[0])), ("latest", utc_from_jd_tt(edges[1])))}
    natal_cusps = [h["longitude"] for h in sorted(natal["houses"], key=lambda h: h["number"])]
    # Same instant as the chart (rounded to the second), so the wall time and its offset always agree.
    local = round_to_second(exact_utc).astimezone(load_zone(location["timezone"]))
    return {"status": "calculated", "calculation_status": "success", "rule_version": RULE_VERSION,
            "year": year, "natal": natal, "return": chart, "time_accuracy": natal["normalized"]["time_accuracy"], "return_window": window,
            "exact": {"utc": iso_utc(exact_utc), "jd_tt": exact_tt, "local": local.replace(tzinfo=None).isoformat(timespec="seconds"),
                      "offset": chart["normalized"]["offset"], "timezone": location["timezone"],
                      "sun_longitude": natal_sun, "residual_arcsec": residual,
                      "chart_rounding_note": "귀환 차트는 가장 가까운 초로 반올림한 현지 시각으로 계산했습니다."},
            "return_in_natal_houses": None if unknown else [{"body": b["id"], "house": house_for(b["longitude"], natal_cusps)}
                                                            for b in chart["bodies"] if b["id"] not in ("Fortune", "Spirit", "SouthNode")],
            "settings": {"definition": "태양의 겉보기 지구중심 tropical 황경(진춘분점, 광행차·장동 포함)이 네이털 값과 같아지는 순간",
                         "location": "사용자가 선택한 장소의 하우스·각도로 귀환 차트를 계산합니다(출생지와 다를 수 있음).",
                         "search": "기념일 ±3일 이분 탐색, 허용오차 약 1ms"}}
