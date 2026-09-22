"""Strict civil-time resolution using packaged, pinned IANA data only."""
from datetime import date, datetime, time, timezone
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


def resolve_time(payload):
    if payload.get("calendar", "gregorian") != "gregorian":
        raise ChartError("INVALID_INPUT", "Gregorian 양력만 지원합니다.")
    if payload.get("time_accuracy", "reported") != "reported":
        raise ChartError("INVALID_INPUT", "현재 버전은 reported 시각만 지원합니다. 생시 미상·추정 시각의 범위 계산은 아직 지원하지 않습니다.")
    date_text, time_text = payload.get("date"), payload.get("time")
    if not isinstance(date_text, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_text):
        raise ChartError("INVALID_INPUT", "생년월일은 YYYY-MM-DD 형식이어야 합니다.")
    if not isinstance(time_text, str) or not re.fullmatch(r"\d{2}:\d{2}(:\d{2})?", time_text):
        raise ChartError("INVALID_INPUT", "출생 시각은 HH:MM 또는 HH:MM:SS 형식이어야 합니다. 윤초 입력은 지원하지 않습니다.")
    try:
        local_date = date.fromisoformat(date_text)
        naive = datetime.combine(local_date, time.fromisoformat(time_text))
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
    candidates = []
    for fold in (0, 1):
        local = naive.replace(tzinfo=zone, fold=fold)
        utc = local.astimezone(timezone.utc)
        if utc.astimezone(zone).replace(tzinfo=None) == naive and not any(c["utc"] == utc for c in candidates):
            candidates.append({"fold": fold, "utc": utc, "offset": format_offset(local.utcoffset())})
    if not candidates:
        raise ChartError("NONEXISTENT_LOCAL_TIME", "DST 또는 시간대 변경으로 존재하지 않는 현지 시각입니다. 입력 시각을 수정하세요.")
    chosen_fold = payload.get("fold")
    if chosen_fold is not None and (type(chosen_fold) is not int or chosen_fold not in (0, 1)):
        raise ChartError("INVALID_INPUT", "fold는 0 또는 1이어야 합니다.")
    if len(candidates) == 2 and chosen_fold is None:
        options = [{**c, "utc": c["utc"].isoformat().replace("+00:00", "Z")} for c in candidates]
        raise ChartError("AMBIGUOUS_LOCAL_TIME", "두 번 존재하는 현지 시각입니다. UTC 후보를 선택하세요.", {"candidates": options})
    chosen = next((c for c in candidates if c["fold"] == chosen_fold), candidates[0])
    if chosen["utc"] > now_utc():
        raise ChartError("UNSUPPORTED_DATE", "미래 출생 시각은 네이털 입력에서 지원하지 않습니다.")
    return chosen["utc"], chosen["offset"], zone_name, "second" if len(time_text) == 8 else "minute"
