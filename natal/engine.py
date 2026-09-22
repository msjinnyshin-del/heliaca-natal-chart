"""Validated Swiss adapter. One lock owns the complete global-state transaction."""
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import threading

import swisseph as swe

from .errors import ChartError
from .rules import aspects, house_for, lots, normalize_aspect_profile, position
from .time_input import convert_calendar, resolve_time

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "ephe"
MANIFEST_PATH = ROOT / "data" / "manifest.json"
ENGINE_LOCK = threading.RLock()
FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED
BODY_DEFS = (("Sun", "태양", "☉", swe.SUN), ("Moon", "달", "☽", swe.MOON),
             ("Mercury", "수성", "☿", swe.MERCURY), ("Venus", "금성", "♀", swe.VENUS),
             ("Mars", "화성", "♂", swe.MARS), ("Jupiter", "목성", "♃", swe.JUPITER),
             ("Saturn", "토성", "♄", swe.SATURN), ("Uranus", "천왕성", "♅", swe.URANUS),
             ("Neptune", "해왕성", "♆", swe.NEPTUNE), ("Pluto", "명왕성", "♇", swe.PLUTO))
STATION_THRESHOLDS = {"Mercury": 0.1, "Venus": 0.1, "Mars": 0.1,
                      "Jupiter": 0.01, "Saturn": 0.01, "Uranus": 0.01,
                      "Neptune": 0.01, "Pluto": 0.01, "Chiron": 0.01}


def validate_data():
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if swe.version != manifest["engine_version"] or version("pyswisseph") != manifest["binding_version"]:
            raise ChartError("EPHEMERIS_DATA_MISSING", "고정된 Swiss 엔진/binding 버전과 일치하지 않습니다.")
        if {item["name"] for item in manifest["files"]} != {"sepl_18.se1", "semo_18.se1", "seas_18.se1"}:
            raise ChartError("EPHEMERIS_DATA_MISSING", "필수 천체력 manifest가 올바르지 않습니다.")
        for item in manifest["files"]:
            path = DATA_DIR / item["name"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                raise ChartError("EPHEMERIS_DATA_MISSING", "천체력 파일이 손상되었거나 manifest와 다릅니다.", {"file": item["name"]})
        if any(path.name not in {item["name"] for item in manifest["files"]} for path in DATA_DIR.iterdir()
               if not path.name.startswith(".")):  # ignore OS metadata such as .DS_Store
            raise ChartError("EPHEMERIS_DATA_MISSING", "고정되지 않은 추가 천체력/보정 파일이 있습니다.")
        if os.environ.get("SE_EPHE_PATH") or os.environ.get("SWEPH_EPHE_PATH"):
            raise ChartError("EPHEMERIS_DATA_MISSING", "외부 천체력 경로 환경변수를 제거한 후 실행하세요.")
        return manifest
    except (OSError, KeyError, ValueError) as exc:
        if isinstance(exc, ChartError):
            raise
        raise ChartError("EPHEMERIS_DATA_MISSING", "필수 천체력 파일 또는 manifest를 읽을 수 없습니다.") from None


def checked_calc(jd_tt, body):
    try:
        values, returned = swe.calc(jd_tt, body, FLAGS)
    except swe.Error:
        raise ChartError("EPHEMERIS_DATA_MISSING", "Swiss 천체 위치 계산에 실패했습니다.", {"body": body}) from None
    if returned & (swe.FLG_SWIEPH | swe.FLG_MOSEPH | swe.FLG_JPLEPH) != swe.FLG_SWIEPH:
        raise ChartError("UNEXPECTED_EPHEMERIS_FALLBACK", "Swiss 파일 이외의 천체력 fallback을 거부했습니다.", {"flags": returned})
    if returned != FLAGS or len(values) != 6 or not all(math.isfinite(x) for x in values):
        raise ChartError("UNEXPECTED_EPHEMERIS_FALLBACK", "요청과 다른 계산 플래그 또는 비정상 수치입니다.", {"flags": returned})
    return values, returned


def coordinate(payload, key, limit):
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or abs(value) > limit or not math.isfinite(value):
        raise ChartError("INVALID_INPUT", f"{key}는 ±{limit} 범위의 유한한 십진수여야 합니다.")
    return float(value)


def normalize_location_source(payload, latitude, longitude, timezone_name):
    source = payload.get("location_source")
    if source is None:
        return {"mode": "manual", "provider": "user", "place_id": None,
                "label": str(payload.get("place", "")), "reference_latitude": latitude,
                "reference_longitude": longitude, "reference_timezone": timezone_name}
    required = {"mode", "provider", "place_id", "label", "reference_latitude", "reference_longitude", "reference_timezone"}
    if not isinstance(source, dict) or set(source) != required:
        raise ChartError("INVALID_INPUT", "location_source 필드 구성이 올바르지 않습니다.")
    mode, provider = source["mode"], source["provider"]
    providers = {"Open-Meteo", "GeoNames", "Open-Meteo / GeoNames", "user"}
    if mode not in {"manual", "geocoded"} or provider not in providers:
        raise ChartError("INVALID_INPUT", "location_source mode/provider가 올바르지 않습니다.")
    if (mode == "manual" and provider != "user") or (mode == "geocoded" and provider == "user"):
        raise ChartError("INVALID_INPUT", "수동 입력과 geocoding 공급자 조합이 올바르지 않습니다.")
    place_id = source["place_id"]
    if place_id is not None and (isinstance(place_id, bool) or not isinstance(place_id, int)):
        raise ChartError("INVALID_INPUT", "location_source place_id는 정수 또는 null이어야 합니다.")
    if not isinstance(source["label"], str) or not source["label"].strip() or len(source["label"]) > 300:
        raise ChartError("INVALID_INPUT", "location_source label이 올바르지 않습니다.")
    for key, limit in (("reference_latitude", 90), ("reference_longitude", 180)):
        value = source[key]
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > limit):
            raise ChartError("INVALID_INPUT", f"location_source {key}가 올바르지 않습니다.")
    reference_timezone = source["reference_timezone"]
    if reference_timezone is not None and (not isinstance(reference_timezone, str) or not reference_timezone.strip() or len(reference_timezone) > 100):
        raise ChartError("INVALID_INPUT", "location_source reference_timezone이 올바르지 않습니다.")
    if mode == "geocoded" and (source["reference_latitude"] is None or source["reference_longitude"] is None or reference_timezone is None):
        raise ChartError("INVALID_INPUT", "geocoded location_source에는 기준 좌표와 timezone이 필요합니다.")
    return dict(source)


def calculate_chart(payload, allow_future=False):
    """allow_future is an internal switch for transit moments; it is never read from the request payload."""
    if not isinstance(payload, dict):
        raise ChartError("INVALID_INPUT", "입력은 JSON 객체여야 합니다.")
    latitude, longitude = coordinate(payload, "latitude", 90), coordinate(payload, "longitude", 180)
    house_system, node_mode = payload.get("house_system", "P"), payload.get("node_mode", "true")
    if house_system not in ("P", "W", "E", "K", "O") or node_mode not in ("true", "mean"):
        raise ChartError("INVALID_INPUT", "지원하지 않는 하우스 또는 Node 설정입니다.")
    aspect_profile = normalize_aspect_profile(payload.get("aspect_profile"))
    solar_payload, calendar_conversion = convert_calendar(payload)
    utc, offset, zone, resolution = resolve_time(solar_payload, allow_future=allow_future)
    location_source = normalize_location_source(payload, latitude, longitude, zone)
    with ENGINE_LOCK:
        manifest = validate_data()
        # close clears previous open-file state; every request fixes mutable globals.
        swe.close()
        swe.set_ephe_path(str(DATA_DIR))
        swe.set_tid_acc(swe.TIDAL_AUTOMATIC)
        swe.set_delta_t_userdef(swe.DELTAT_AUTOMATIC)
        try:
            jd_tt, jd_ut1 = swe.utc_to_jd(utc.year, utc.month, utc.day, utc.hour, utc.minute, utc.second, swe.GREG_CAL)
            cusps, ascmc = swe.houses_ex(jd_ut1, latitude, longitude, house_system.encode("ascii"), 0)
        except swe.Error:
            raise ChartError("HOUSE_SYSTEM_UNAVAILABLE", "선택한 위치에서 하우스 계산에 실패했습니다. 다른 하우스 시스템을 선택하세요.") from None
        if len(cusps) != 12 or not all(math.isfinite(x) for x in (*cusps, *ascmc, jd_tt, jd_ut1)):
            raise ChartError("HOUSE_SYSTEM_UNAVAILABLE", "하우스 계산이 비정상 수치를 반환했습니다.")
        widths = [(cusps[(i + 1) % 12] - cusps[i]) % 360 for i in range(12)]
        if any(w <= 0 for w in widths) or abs(sum(widths) - 360) > 1e-7:
            raise ChartError("HOUSE_SYSTEM_UNAVAILABLE", "유효하지 않은 하우스 커스프 순서입니다.")
        obliquity = swe.calc(jd_tt, swe.ECL_NUT, 0)[0][0]
        bodies = []
        definitions = BODY_DEFS + (("NorthNode", "북노드", "☊", swe.TRUE_NODE if node_mode == "true" else swe.MEAN_NODE),
                                   ("Lilith", "평균 릴리스", "⚸", swe.MEAN_APOG), ("Chiron", "키론", "⚷", swe.CHIRON))
        def make_body(body_id, name, symbol, values, returned):
            lon, lat, distance, speed = values[:4]
            equatorial = swe.cotrans((lon, lat, distance), -obliquity)
            altitude = swe.azalt(jd_ut1, swe.EQU2HOR, (longitude, latitude, 0), 0, 15, equatorial)[1]
            if not all(math.isfinite(v) for v in (*equatorial, altitude)):
                raise ChartError("UNEXPECTED_EPHEMERIS_FALLBACK", "지평/적도 좌표 변환에 실패했습니다.")
            threshold = STATION_THRESHOLDS.get(body_id)
            direction = "S" if threshold is not None and abs(speed) < threshold else "R" if speed < 0 else "D" if speed > 0 else "undetermined"
            return {"id": body_id, "name": name, "symbol": symbol, **position(lon), "latitude": lat,
                    "speed": speed, "retrograde": speed < 0 if speed != 0 else None,
                    "direction": direction, "near_station": direction == "S", "station_threshold": threshold,
                    "house": house_for(lon, cusps), "declination": equatorial[1], "altitude": altitude,
                    "antiscia": (180 - lon) % 360, "flags": returned}
        for body_id, name, symbol, number in definitions:
            values, returned = checked_calc(jd_tt, number)
            bodies.append(make_body(body_id, name, symbol, values, returned))
            if body_id == "NorthNode":
                south = ((values[0] + 180) % 360, -values[1], values[2], values[3], -values[4], values[5])
                bodies.append(make_body("SouthNode", "남노드", "☋", south, returned))
        angles = [{"id": key, **position(lon)} for key, lon in (("ASC", ascmc[0]), ("MC", ascmc[1]), ("DSC", ascmc[0] + 180), ("IC", ascmc[1] + 180))]
        sect, fortune, spirit = lots(ascmc[0], bodies[0]["longitude"], bodies[1]["longitude"], bodies[0]["altitude"])
        for key, name, symbol, lon in (("Fortune", "포르투나", "⊗", fortune), ("Spirit", "스피릿", "◇", spirit)):
            bodies.append({"id": key, "name": name, "symbol": symbol, **position(lon), "house": house_for(lon, cusps),
                           "latitude": None, "speed": None, "retrograde": None, "direction": "not_applicable", "declination": None,
                           "altitude": None, "antiscia": (180 - lon) % 360, "flags": None})
        used_data = []
        for index, filename in enumerate(("sepl_18.se1", "semo_18.se1", "seas_18.se1")):
            path, start, end, denum = swe.get_current_file_data(index)
            if Path(path).resolve() != (DATA_DIR / filename).resolve() or not start <= jd_tt <= end:
                raise ChartError("UNEXPECTED_EPHEMERIS_FALLBACK", "실제 사용 천체력 파일/범위가 manifest와 다릅니다.")
            item = next(item for item in manifest["files"] if item["name"] == filename)
            used_data.append({**item, "start_jd": start, "end_jd": end, "denum": denum})
    # Preserve only contract fields; an optional name is never needed by the engine.
    original = {key: payload[key] for key in ("date", "time", "timezone", "latitude", "longitude", "place", "house_system", "node_mode", "time_accuracy", "fold", "calendar", "lunar_leap") if key in payload}
    original["aspect_profile"] = aspect_profile
    original["location_source"] = location_source
    settings = {"house_system": house_system, "node_mode": node_mode, "lilith_mode": "mean", "zodiac": "tropical", "rounding": "nearest_second",
                "house_assignment": "longitude-cusp-half-open-v1", "sect_rule": "geocentric-geometric-sun-center-altitude>=0",
                "aspect_rule": "major-v2", "aspect_profile": aspect_profile}
    fingerprint = hashlib.sha256(json.dumps({"utc": utc.isoformat(), "latitude": latitude, "longitude": longitude, "settings": settings,
                                             "location_source": location_source, "manifest": manifest}, sort_keys=True).encode()).hexdigest()
    return {"status": "calculated", "calculation_status": "success", "input": original,
            "normalized": {"utc": utc.isoformat().replace("+00:00", "Z"), "offset": offset, "timezone": zone, "latitude": latitude, "longitude": longitude,
                           "jd_tt": jd_tt, "jd_ut1": jd_ut1, "time_resolution": resolution, "time_accuracy": "reported",
                           "solar_date": solar_payload["date"], "calendar_conversion": calendar_conversion},
            "settings": settings, "bodies": bodies, "angles": angles,
            "houses": [{"number": i + 1, **position(lon)} for i, lon in enumerate(cusps)], "aspects": aspects(bodies, angles, aspect_profile), "sect": sect,
            "metadata": {"engine": manifest["engine"], "engine_version": swe.version, "binding_version": version("pyswisseph"), "tzdb": manifest["tzdb"],
                         "profile": "reference-tropical-v1", "requested_flags": FLAGS, "data": used_data, "input_fingerprint": fingerprint,
                         "time_policy": manifest["time_policy"], "delta_t_seconds": (jd_tt - jd_ut1) * 86400,
                         "geocoding": {**location_source, "note": ("geocoding 공급자의 도시 중심 후보이며 좌표-시간대 경계를 검증한 결과가 아닙니다."
                                                                   if location_source["mode"] == "geocoded" else
                                                                   "사용자가 직접 제공한 좌표와 IANA timezone이며 지리적 경계를 자동 검증하지 않았습니다.")},
                         "near_station_policy": "표시 임계값 기반 near-station이며 정확한 정지 시각 탐색 결과가 아닙니다.",
                         "not_evaluated": ["dignities", "patterns", "applying/separating", "interpretation", "unknown/approximate time"]},
            "warnings": ["좌표와 IANA 시간대의 지리적 일치는 사용자가 확인해야 합니다.", "최근접 초 표시값과 원시 사인/하우스 판정은 구분됩니다.",
                         "S는 속도 임계값 기반 근정지 표시이며 정확한 station 시각을 계산했다는 뜻이 아닙니다.",
                         "스피릿은 정의한 Lot of Spirit이며 참조 이미지의 다이아몬드 기호와 동일하다고 확정하지 않습니다."]
                        + ([f"1970년 이전 출생: IANA 역사 시간대 기록의 UTC{offset}를 적용했습니다. 당시 서머타임·표준시 변경이 출생 기록과 다를 수 있으니 확인하세요."]
                           if solar_payload["date"] < "1970" else [])}
