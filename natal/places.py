"""City-name-only geocoding for the private local prototype.

Open-Meteo free endpoint is for non-commercial evaluation; commercial deployment
needs a suitable provider plan. Data attribution is returned with every result.
The external service is live/unversioned; coordinates describe a place, not a
validated historic timezone boundary or an exact street-level birth location.
"""
from collections import OrderedDict, deque
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import socket
import threading
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from zoneinfo import ZoneInfo

import tzdata

ENDPOINT = "https://geocoding-api.open-meteo.com/v1/search"
NETWORK_TIMEOUT = 4
MAX_RESPONSE_BYTES = 131_072
MAX_RESULTS = 8
CACHE_TTL = 600
MAX_CACHE_ITEMS = 128
MAX_CALLS_PER_MINUTE = 20
MAX_CONCURRENT_CALLS = 2
# Search-text aliases only; all coordinates and zones still come from the API.
# Two-character upstream searches are exact. For example, 서울 does not match
# the indexed 서울특별시, and 부산 can return small same-name localities.
KOREAN_CITY_ALIASES = {"서울": "서울특별시", "서울시": "서울특별시", "부산": "부산광역시",
                       "대구": "대구광역시", "인천": "인천광역시", "광주": "광주광역시",
                       "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시", "제주": "제주시"}
ATTRIBUTION = {"provider": "Open-Meteo", "url": "https://open-meteo.com/",
               "data_source": "GeoNames", "data_url": "https://www.geonames.org/",
               "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
               "modifications": "필수 좌표·시간대 검증, 표시 이름 조합 및 최대 8개 후보 제한"}


class PlaceSearchError(ValueError):
    def __init__(self, code, message, status=502):
        super().__init__(message)
        self.code = code
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        # A provider redirect must never expand the fixed-host network scope.
        raise HTTPError(ENDPOINT, code, "Provider redirect rejected", headers, None)


# Environment proxies are not allowed to change the recipient of city searches.
OPENER = build_opener(ProxyHandler({}), NoRedirect())


def fetch_places(query):
    parameters = urlencode({"name": query, "count": MAX_RESULTS, "language": "ko", "format": "json"})
    request = Request(ENDPOINT + "?" + parameters, headers={"Accept": "application/json", "User-Agent": "NatalLocal/1 (city lookup)"})
    try:
        with OPENER.open(request, timeout=NETWORK_TIMEOUT) as response:
            if response.status != 200 or response.headers.get("Content-Type", "").split(";", 1)[0].lower() != "application/json":
                raise PlaceSearchError("PLACE_SEARCH_INVALID_RESPONSE", "장소 검색 서비스가 올바르지 않은 응답을 반환했습니다.")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise PlaceSearchError("PLACE_SEARCH_INVALID_RESPONSE", "장소 검색 응답 크기가 허용 범위를 초과했습니다.")
        def reject_nonfinite(value):
            raise ValueError("Non-finite JSON value")
        return json.loads(raw, parse_constant=reject_nonfinite)
    except HTTPError as error:
        if error.code == 429:
            raise PlaceSearchError("PLACE_SEARCH_RATE_LIMITED", "장소 검색 서비스의 요청 한도에 도달했습니다. 잠시 후 다시 검색하세요.", 429) from None
        raise PlaceSearchError("PLACE_SEARCH_UNAVAILABLE", "장소 검색 서비스에 연결하지 못했습니다. 잠시 후 다시 시도하거나 좌표를 직접 입력하세요.") from None
    except (TimeoutError, socket.timeout):
        raise PlaceSearchError("PLACE_SEARCH_TIMEOUT", "장소 검색 연결 시간이 초과되었습니다. 다시 검색하거나 좌표를 직접 입력하세요.", 504) from None
    except URLError as error:
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            raise PlaceSearchError("PLACE_SEARCH_TIMEOUT", "장소 검색 연결 시간이 초과되었습니다. 다시 검색하거나 좌표를 직접 입력하세요.", 504) from None
        raise PlaceSearchError("PLACE_SEARCH_UNAVAILABLE", "장소 검색 서비스에 연결하지 못했습니다. 네트워크를 확인하거나 좌표를 직접 입력하세요.") from None
    except (ValueError, UnicodeError) as error:
        if isinstance(error, PlaceSearchError):
            raise
        raise PlaceSearchError("PLACE_SEARCH_INVALID_RESPONSE", "장소 검색 응답을 해석할 수 없습니다.") from None
    except OSError:
        raise PlaceSearchError("PLACE_SEARCH_UNAVAILABLE", "장소 검색 중 네트워크 오류가 발생했습니다.") from None


def valid_text(value, maximum=200):
    return isinstance(value, str) and 0 < len(value.strip()) <= maximum and not any(unicodedata.category(c).startswith("C") for c in value)


def valid_zone(value):
    if not isinstance(value, str) or len(value) > 100 or not re.fullmatch(r"[A-Za-z0-9_+.-]+(?:/[A-Za-z0-9_+.-]+)*", value):
        return False
    if any(part in (".", "..") for part in value.split("/")):
        return False
    try:
        with (Path(tzdata.__file__).parent / "zoneinfo" / value).open("rb") as file:
            ZoneInfo.from_file(file, key=value)
        return True
    except (OSError, ValueError):
        return False


def normalize_response(payload):
    if tzdata.__version__ != "2025.2" or tzdata.IANA_VERSION != "2025b":
        raise PlaceSearchError("PLACE_SEARCH_UNAVAILABLE", "고정된 시간대 데이터가 필요합니다. 설치 상태를 확인하세요.")
    if not isinstance(payload, dict) or payload.get("error") or not isinstance(payload.get("results", []), list):
        raise PlaceSearchError("PLACE_SEARCH_INVALID_RESPONSE", "장소 검색 서비스의 결과 형식이 올바르지 않습니다.")
    rows = payload.get("results", [])
    if len(rows) > 100:
        raise PlaceSearchError("PLACE_SEARCH_INVALID_RESPONSE", "장소 검색 서비스가 너무 많은 후보를 반환했습니다.")
    results, seen, excluded = [], set(), 0
    for row in rows:
        valid = isinstance(row, dict)
        if valid:
            valid = (type(row.get("id")) is int and row["id"] > 0 and valid_text(row.get("name"))
                     and valid_text(row.get("country")) and isinstance(row.get("country_code"), str)
                     and re.fullmatch(r"[A-Z]{2}", row["country_code"]) is not None
                     and (row.get("admin1", "") == "" or valid_text(row.get("admin1")))
                     and valid_zone(row.get("timezone")))
        if valid:
            for key, limit in (("latitude", 90), ("longitude", 180)):
                value = row.get(key)
                if type(value) not in (int, float) or abs(value) > limit or not math.isfinite(value):
                    valid = False
                    break
        if not valid:
            excluded += 1
            continue
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        item = {key: row.get(key, "") for key in ("id", "name", "admin1", "country", "country_code", "latitude", "longitude", "timezone")}
        item["label"] = ", ".join(dict.fromkeys(item[key].strip() for key in ("name", "admin1", "country") if item[key].strip()))
        item["provider"] = "Open-Meteo / GeoNames"
        item["provider_version"] = "live API v1; dataset version not supplied"
        item["timezone_validation"] = "IANA 2025b identifier; historical geographic boundary not independently verified"
        results.append(item)
    if rows and not results:
        raise PlaceSearchError("PLACE_SEARCH_INVALID_RESPONSE", "검색 후보에 유효한 좌표·시간대가 없습니다. 다른 도시명으로 검색하거나 직접 입력하세요.")
    warnings = [f"좌표·시간대 등 필수 정보가 유효하지 않은 후보 {excluded}개를 제외했습니다."] if excluded else []
    return {"results": results[:MAX_RESULTS], "attribution": deepcopy(ATTRIBUTION), "warnings": warnings}


class PlaceSearch:
    def __init__(self, fetch=None, clock=None):
        self.fetch = fetch or fetch_places
        self.clock = clock or time.monotonic
        self.cache = OrderedDict()
        self.calls = deque()
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(MAX_CONCURRENT_CALLS)

    def search(self, query):
        if not isinstance(query, str) or any(unicodedata.category(c).startswith("C") for c in query):
            raise PlaceSearchError("INVALID_PLACE_QUERY", "도시명을 2–100자로 입력하세요.", 422)
        query = unicodedata.normalize("NFC", query).strip()
        if not 2 <= len(query) <= 100:
            raise PlaceSearchError("INVALID_PLACE_QUERY", "도시명을 2–100자로 입력하세요.", 422)
        key = query.casefold()
        with self.lock:
            now = self.clock()
            for old in [k for k, (expiry, _) in self.cache.items() if expiry <= now]:
                del self.cache[old]
            if key in self.cache:
                self.cache.move_to_end(key)
                return deepcopy(self.cache[key][1])
            while self.calls and self.calls[0] <= now - 60:
                self.calls.popleft()
            if len(self.calls) >= MAX_CALLS_PER_MINUTE or not self.slots.acquire(blocking=False):
                raise PlaceSearchError("PLACE_SEARCH_RATE_LIMITED", "검색 요청이 많습니다. 잠시 후 다시 검색하세요.", 429)
            self.calls.append(now)
        try:
            location, separator, qualifier = query.partition(",")
            alias = KOREAN_CITY_ALIASES.get(location.strip())
            provider_query = alias + separator + qualifier if alias else query
            result = normalize_response(self.fetch(provider_query))
            if alias:
                result["warnings"].append(f"‘{location.strip()}’을 공식 도시명 ‘{alias}’로 확장해 검색했습니다.")
        finally:
            self.slots.release()
        with self.lock:
            self.cache[key] = (self.clock() + CACHE_TTL, deepcopy(result))
            self.cache.move_to_end(key)
            while len(self.cache) > MAX_CACHE_ITEMS:
                self.cache.popitem(last=False)
        return result


_SEARCH = PlaceSearch()


def search_places(query):
    return _SEARCH.search(query)
