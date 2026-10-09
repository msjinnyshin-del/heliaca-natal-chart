"""Admin engine inspector quick-input people, kept in the admin database (never in the repository).

Each row is one browser-profile-shaped person (name, calendar, date, time, place). These are real birth data
entered by the admin, so they live only in the admin store behind the admin login and are never logged.
"""
from datetime import date as calendar_date
import json
import math
import re

from . import store
from .places import valid_zone
from .store import StoreError

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$")
SOURCE_TEXT = ("mode", "provider", "label")


def _number(value, low, high):
    return (isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
            and low <= value <= high)


def _source(value):
    """Optional place-search provenance; only the known fields with the right types are kept."""
    if not isinstance(value, dict):
        return None
    source = {}
    for key in SOURCE_TEXT:
        text = value.get(key)
        source[key] = text[:200] if isinstance(text, str) else None
    source["reference_latitude"] = value["reference_latitude"] if _number(value.get("reference_latitude"), -90, 90) else None
    source["reference_longitude"] = value["reference_longitude"] if _number(value.get("reference_longitude"), -180, 180) else None
    zone = value.get("reference_timezone")
    source["reference_timezone"] = zone if valid_zone(zone) else None
    place_id = value.get("place_id")
    source["place_id"] = place_id if isinstance(place_id, int) and not isinstance(place_id, bool) else None
    # A search reference the place picker cannot restore is kept as plain manual coordinates.
    if source["mode"] != "geocoded" or source["place_id"] is None or None in (
            source["reference_latitude"], source["reference_longitude"], source["reference_timezone"]):
        source["mode"] = "manual"
    return source


def clean_profile(payload):
    """Validated, normalized person; raises StoreError naming the first bad field."""
    if not isinstance(payload, dict):
        raise StoreError("사람 정보가 올바르지 않습니다.")
    name = store.clean_name(payload.get("name"))
    if not name:
        raise StoreError("이름을 입력해 주세요.")
    calendar = payload.get("calendar", "gregorian")
    if calendar not in ("gregorian", "lunar"):
        raise StoreError("달력은 양력 또는 음력이어야 합니다.")
    date = payload.get("date")
    if not isinstance(date, str) or not store.DATE_RE.fullmatch(date):
        raise StoreError("생년월일은 YYYY-MM-DD 형식이어야 합니다.")
    if calendar == "gregorian":
        try:
            calendar_date.fromisoformat(date)
        except ValueError:
            raise StoreError("존재하지 않는 날짜입니다.") from None
    time_unknown = payload.get("time_unknown") is True
    time = payload.get("time")
    if not time_unknown and (not isinstance(time, str) or not TIME_RE.fullmatch(time)):
        raise StoreError("출생 시각은 HH:MM 형식이어야 합니다 (모르면 '생시 모름').")
    place = payload.get("place")
    if not isinstance(place, dict):
        raise StoreError("출생지를 입력해 주세요.")
    label = store.clean_name(place.get("label"))
    if not label:
        raise StoreError("출생지 이름을 입력해 주세요.")
    if not _number(place.get("latitude"), -90, 90) or not _number(place.get("longitude"), -180, 180):
        raise StoreError("출생지 위도는 −90~90, 경도는 −180~180 사이 숫자여야 합니다.")
    if not valid_zone(place.get("timezone")):
        raise StoreError("출생지 시간대는 IANA 이름이어야 합니다 (예: Asia/Seoul).")
    clean_place = {"label": label, "latitude": place["latitude"], "longitude": place["longitude"], "timezone": place["timezone"]}
    source = _source(place.get("source"))
    if source:
        clean_place["source"] = source
    return {"name": name, "calendar": calendar, "date": date, "lunar_leap": calendar == "lunar" and payload.get("lunar_leap") is True,
            "time_unknown": time_unknown, "time": None if time_unknown else time[:5], "place": clean_place}


def _row(row):
    item = json.loads(row["profile"])
    item.update(id=row["id"], name=row["name"], updated_at=row["updated_at"])
    return item


def list_presets():
    connection = store.connect()
    try:
        rows = connection.execute("SELECT id, name, profile, updated_at FROM admin_presets ORDER BY id").fetchall()
        return [_row(row) for row in rows]
    finally:
        connection.close()


DUPLICATE = "같은 이름의 사람이 이미 있습니다. 다른 이름을 쓰거나 기존 사람을 수정하세요."


def _write(sql, params, result=lambda cursor: cursor.rowcount):
    connection = store.connect()
    try:
        with connection:
            return result(connection.execute(sql, params))
    except store.integrity_errors():
        raise StoreError(DUPLICATE) from None
    finally:
        connection.close()


def create_preset(payload):
    profile = clean_profile(payload)
    now = store.now_iso()
    sql = "INSERT INTO admin_presets (name, profile, created_at, updated_at) VALUES (?, ?, ?, ?)"
    params = (profile["name"], json.dumps(profile, ensure_ascii=False), now, now)
    if store.is_postgres():
        preset_id = _write(sql + " RETURNING id", params, lambda cursor: cursor.fetchone()["id"])
    else:
        preset_id = _write(sql, params, lambda cursor: cursor.lastrowid)
    return {**profile, "id": preset_id, "updated_at": now}


def update_preset(preset_id, payload):
    profile = clean_profile(payload)
    return _write("UPDATE admin_presets SET name = ?, profile = ?, updated_at = ? WHERE id = ?",
                  (profile["name"], json.dumps(profile, ensure_ascii=False), store.now_iso(), int(preset_id)))


def delete_preset(preset_id):
    return _write("DELETE FROM admin_presets WHERE id = ?", (int(preset_id),))


def import_presets(items):
    """Adds the given people (e.g. the NATAL_ADMIN_PRESETS list) whose names are not registered yet."""
    taken = {item["name"] for item in list_presets()}
    added = 0
    for item in items:
        try:
            profile = clean_profile(item)
            if profile["name"] in taken:
                continue
            create_preset(profile)
        except StoreError:
            continue
        taken.add(profile["name"])
        added += 1
    return {"imported": added}
