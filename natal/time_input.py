"""Strict civil-time resolution using packaged, pinned IANA data only."""
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import tzdata

from .errors import ChartError


def now_utc():
    return datetime.now(timezone.utc)


def format_offset(delta):
    seconds = int(delta.total_seconds())
    sign = "+" if seconds >= 0 else "-"
    hours, remainder = divmod(abs(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{sign}{hours:02d}:{minutes:02d}" + (f":{seconds:02d}" if seconds else "")


def convert_calendar(payload):
    """Return (payload with a Gregorian date, conversion record or None).

    Lunar dates use the Korean (KASI-based) calendar, whose month starts follow
    Korean time; they can differ by a day from the Chinese calendar.
    """
    calendar = payload.get("calendar", "gregorian")
    if calendar == "gregorian":
        if payload.get("lunar_leap") not in (None, False):
            raise ChartError("INVALID_INPUT", "윤달은 음력 입력에서만 선택할 수 있습니다.")
        return payload, None
    if calendar != "lunar":
        raise ChartError("INVALID_INPUT", "양력(gregorian) 또는 음력(lunar)만 지원합니다.")
    date_text, leap = payload.get("date"), payload.get("lunar_leap", False)
    if type(leap) is not bool:
        raise ChartError("INVALID_INPUT", "윤달 여부는 true 또는 false여야 합니다.")
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", date_text) if isinstance(date_text, str) else None
    if not match:
        raise ChartError("INVALID_INPUT", "음력 생년월일은 YYYY-MM-DD 형식이어야 합니다.")
    year, month, day = (int(part) for part in match.groups())
    if not 1900 <= year <= 2050:
        raise ChartError("UNSUPPORTED_DATE", "음력은 1900–2050년만 변환할 수 있습니다.")
    from korean_lunar_calendar import KoreanLunarCalendar
    converter = KoreanLunarCalendar()  # stateful: one instance per request
    if not converter.setLunarDate(year, month, day, leap):
        raise ChartError("INVALID_INPUT", "존재하지 않는 음력 날짜입니다. 월·일과 윤달 여부를 확인하세요.")
    solar = converter.SolarIsoFormat()
    record = {"calendar": "lunar", "lunar_date": date_text, "lunar_leap": leap, "solar_date": solar,
              "converter": "korean-lunar-calendar 0.4.0 (Korean/KASI lunar calendar)"}
    return {**payload, "calendar": "gregorian", "date": solar, "lunar_leap": None}, record


TIME_ACCURACIES = ("reported", "unknown")


def time_accuracy(payload):
    accuracy = payload.get("time_accuracy", "reported")
    if accuracy == "approximate":
        raise ChartError("INVALID_INPUT", "추정 시각(오차 구간) 계산은 아직 지원하지 않습니다. 정확한 시각을 입력하거나 생시 미상을 선택하세요.")
    if accuracy not in TIME_ACCURACIES:
        raise ChartError("INVALID_INPUT", "time_accuracy는 reported 또는 unknown이어야 합니다.")
    return accuracy


def _local_date_and_zone(payload):
    if payload.get("calendar", "gregorian") != "gregorian":
        raise ChartError("INVALID_INPUT", "Gregorian 양력만 지원합니다.")
    date_text = payload.get("date")
    if not isinstance(date_text, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_text):
        raise ChartError("INVALID_INPUT", "생년월일은 YYYY-MM-DD 형식이어야 합니다.")
    try:
        local_date = date.fromisoformat(date_text)
    except ValueError:
        raise ChartError("INVALID_INPUT", "유효하지 않은 날짜 또는 시각입니다. 윤초 입력은 지원하지 않습니다.") from None
    if local_date.year < 1900:
        raise ChartError("UNSUPPORTED_DATE", "1900년 이전 또는 미래 출생일은 지원하지 않습니다.")
    if tzdata.__version__ != "2025.2" or tzdata.IANA_VERSION != "2025b":
        raise ChartError("TIMEZONE_NEEDS_REVIEW", "고정된 tzdata 2025.2 (IANA 2025b)가 필요합니다.")
    zone_name = payload.get("timezone")
    if not isinstance(zone_name, str) or not zone_name or any(part in ("", ".", "..") for part in zone_name.split("/")) or "\\" in zone_name:
        raise ChartError("INVALID_INPUT", "유효한 IANA 시간대를 입력하세요.")
    path = Path(tzdata.__file__).parent / "zoneinfo" / zone_name
    try:
        with path.open("rb") as file:
            zone = ZoneInfo.from_file(file, key=zone_name)
    except (OSError, ValueError):
        raise ChartError("INVALID_INPUT", "알 수 없는 IANA 시간대입니다.") from None
    return local_date, zone_name, zone


def _candidates(naive, zone):
    candidates = []
    for fold in (0, 1):
        local = naive.replace(tzinfo=zone, fold=fold)
        utc = local.astimezone(timezone.utc)
        if utc.astimezone(zone).replace(tzinfo=None) == naive and not any(c["utc"] == utc for c in candidates):
            candidates.append({"fold": fold, "utc": utc, "offset": format_offset(local.utcoffset())})
    return candidates


def _first_instant(naive, zone):
    """First UTC instant whose local wall time is at or after `naive`.

    Existing times give their earliest occurrence. A skipped time gives the transition instant, found by
    bisection because fold mappings of a gap can land on either side of it (e.g. a 23:30 -> 00:30 jump).
    """
    candidates = _candidates(naive, zone)
    if candidates:
        return min(c["utc"] for c in candidates)
    lo, hi = sorted(int(naive.replace(tzinfo=zone, fold=fold).timestamp()) for fold in (0, 1))
    lo -= 86400  # whole seconds: offsets and transitions are second-aligned
    local_at = lambda seconds: datetime.fromtimestamp(seconds, timezone.utc).astimezone(zone).replace(tzinfo=None)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if local_at(mid) >= naive:
            hi = mid
        else:
            lo = mid
    return datetime.fromtimestamp(hi, timezone.utc)


def _day_start(local_date, zone):
    return _first_instant(datetime.combine(local_date, time()), zone)


def resolve_unknown_day(payload):
    """Unknown birth time: the whole local date [start, end) plus local noon as the stated representative."""
    if payload.get("time") is not None:
        raise ChartError("INVALID_INPUT", "생시 미상(unknown)에서는 시각을 함께 보내지 마세요.")
    if payload.get("fold") is not None:
        raise ChartError("INVALID_INPUT", "생시 미상(unknown)에서는 fold를 지정할 수 없습니다.")
    local_date, zone_name, zone = _local_date_and_zone(payload)
    start, end = _day_start(local_date, zone), _day_start(local_date + timedelta(days=1), zone)
    if end <= start:
        raise ChartError("NONEXISTENT_LOCAL_TIME", "시간대 변경으로 이 현지 날짜는 존재하지 않습니다. 날짜와 시간대를 확인하세요.")
    if end > now_utc():
        raise ChartError("UNSUPPORTED_DATE", "생시 미상은 하루 전체가 지난 날짜만 계산할 수 있습니다.")
    noon = datetime.combine(local_date, time(12))
    candidates = _candidates(noon, zone)
    notes = []
    if not candidates:
        utc = _first_instant(noon, zone)
        notes.append("이 날짜의 현지 정오가 시간대 변경으로 존재하지 않아, 변경 직후 시각을 대표 시각으로 사용했습니다.")
    else:
        utc = candidates[0]["utc"]
        if len(candidates) == 2:
            notes.append("이 날짜의 현지 정오가 두 번 존재해 첫 번째(fold 0)를 대표 시각으로 사용했습니다.")
    local = utc.astimezone(zone)
    return {"utc": utc, "offset": format_offset(local.utcoffset()), "zone": zone_name, "zoneinfo": zone,
            "representative_local_time": local.strftime("%H:%M:%S"), "start": start, "end": end, "notes": notes}


def resolve_time(payload, allow_future=False):
    if payload.get("calendar", "gregorian") != "gregorian":
        raise ChartError("INVALID_INPUT", "Gregorian 양력만 지원합니다.")
    if time_accuracy(payload) != "reported":
        raise ChartError("INVALID_INPUT", "이 계산은 알려진 출생 시각(reported)이 필요합니다.")
    date_text, time_text = payload.get("date"), payload.get("time")
    if not isinstance(date_text, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_text):
        raise ChartError("INVALID_INPUT", "생년월일은 YYYY-MM-DD 형식이어야 합니다.")
    if not isinstance(time_text, str) or not re.fullmatch(r"\d{2}:\d{2}(:\d{2})?", time_text):
        raise ChartError("INVALID_INPUT", "출생 시각은 HH:MM 또는 HH:MM:SS 형식이어야 합니다. 윤초 입력은 지원하지 않습니다.")
    try:
        naive = datetime.combine(date.fromisoformat(date_text), time.fromisoformat(time_text))
    except ValueError:
        raise ChartError("INVALID_INPUT", "유효하지 않은 날짜 또는 시각입니다. 윤초 입력은 지원하지 않습니다.") from None
    local_date, zone_name, zone = _local_date_and_zone(payload)
    candidates = _candidates(naive, zone)
    if not candidates:
        raise ChartError("NONEXISTENT_LOCAL_TIME", "DST 또는 시간대 변경으로 존재하지 않는 현지 시각입니다. 입력 시각을 수정하세요.")
    chosen_fold = payload.get("fold")
    if chosen_fold is not None and (type(chosen_fold) is not int or chosen_fold not in (0, 1)):
        raise ChartError("INVALID_INPUT", "fold는 0 또는 1이어야 합니다.")
    if len(candidates) == 2 and chosen_fold is None:
        options = [{**c, "utc": c["utc"].isoformat().replace("+00:00", "Z")} for c in candidates]
        raise ChartError("AMBIGUOUS_LOCAL_TIME", "두 번 존재하는 현지 시각입니다. UTC 후보를 선택하세요.", {"candidates": options})
    chosen = next((c for c in candidates if c["fold"] == chosen_fold), candidates[0])
    if allow_future and local_date.year > 2100:
        raise ChartError("UNSUPPORTED_DATE", "트랜짓 시점은 2100년까지 지원합니다.")
    if not allow_future and chosen["utc"] > now_utc():
        raise ChartError("UNSUPPORTED_DATE", "미래 출생 시각은 네이털 입력에서 지원하지 않습니다.")
    return chosen["utc"], chosen["offset"], zone_name, "second" if len(time_text) == 8 else "minute"
