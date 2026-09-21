"""Location search boundaries; only city names may reach the fixed provider."""
import importlib
import http.client
import json
import threading
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
import unittest


class PlacesExistence(unittest.TestCase):
    def test_search_adapter_is_present(self):
        try:
            module = importlib.import_module("natal.places")
        except ModuleNotFoundError:
            module = None
        self.assertTrue(callable(getattr(module, "search_places", None)), "검증된 도시 검색 adapter가 필요합니다")


SEOUL = {"id": 1835848, "name": "서울", "admin1": "서울특별시", "country": "대한민국", "country_code": "KR", "latitude": 37.566, "longitude": 126.978, "timezone": "Asia/Seoul"}


class PlaceSearchTests(unittest.TestCase):
    def setUp(self):
        from natal import places
        self.places = places

    def client(self, payload=None):
        fetch = Mock(return_value={"results": [SEOUL]} if payload is None else payload)
        return self.places.PlaceSearch(fetch=fetch), fetch

    def assert_error(self, function, code):
        with self.assertRaises(self.places.PlaceSearchError) as result:
            function()
        self.assertEqual(result.exception.code, code)
        return result.exception

    def test_korean_english_results_keep_disambiguation_and_provenance(self):
        other = {**SEOUL, "id": 4409896, "name": "Springfield", "admin1": "Missouri", "country": "United States", "country_code": "US", "timezone": "America/Chicago", "latitude": 37.21, "longitude": -93.29}
        third = {**other, "id": 4250542, "admin1": "Illinois", "latitude": 39.8, "longitude": -89.64}
        client, fetch = self.client({"results": [SEOUL, other, third]})
        result = client.search(" 서울 ")
        fetch.assert_called_once_with("서울특별시")
        self.assertEqual(result["results"][0]["timezone"], "Asia/Seoul")
        self.assertNotEqual(result["results"][1]["label"], result["results"][2]["label"])
        self.assertEqual(result["attribution"]["data_source"], "GeoNames")
        self.assertIn("provider", result["results"][0])
        self.assertIn("서울특별시", result["warnings"][0])
        client.search("Seoul")
        self.assertEqual(fetch.call_args.args, ("Seoul",))

    def test_only_valid_queries_reach_provider(self):
        client, fetch = self.client()
        for query in (None, [], "", "a", "a" * 101, "Seoul\nname", "서울\x00", "  "):
            with self.subTest(query=query):
                self.assert_error(lambda: client.search(query), "INVALID_PLACE_QUERY")
        fetch.assert_not_called()
        client.search("La")
        client.search("a" * 100)
        self.assertEqual(fetch.call_count, 2)

    def test_bad_fields_and_unknown_timezones_are_excluded(self):
        variants = [{"timezone": None}, {"timezone": "Madeup/Zone"}, {"timezone": "../UTC"},
                    {"latitude": True}, {"latitude": 91}, {"longitude": float("nan")},
                    {"longitude": 10**400}, {"id": "1835848"}, {"name": []}, {"country_code": "KOR"}]
        client, _ = self.client({"results": [SEOUL] + [{**SEOUL, **change} for change in variants]})
        result = client.search("서울")
        self.assertEqual(len(result["results"]), 1)
        self.assertTrue(result["warnings"])

    def test_empty_results_distinct_from_provider_failure(self):
        for payload in ({}, {"results": []}):
            client, _ = self.client(payload)
            self.assertEqual(client.search("Notaplace")["results"], [])
        for payload in ([], {"error": True, "reason": "secret upstream detail"}, {"results": None}, {"results": [{**SEOUL, "timezone": None}]}):
            client, _ = self.client(payload)
            self.assert_error(lambda: client.search("서울"), "PLACE_SEARCH_INVALID_RESPONSE")

    def test_pinned_timezone_database_version_is_required(self):
        client, _ = self.client()
        with patch.object(self.places.tzdata, "__version__", "wrong"):
            self.assert_error(lambda: client.search("서울"), "PLACE_SEARCH_UNAVAILABLE")

    def test_cache_is_bounded_expires_and_returns_copies(self):
        now = [0.0]
        fetch = Mock(return_value={"results": [SEOUL]})
        client = self.places.PlaceSearch(fetch=fetch, clock=lambda: now[0])
        first = client.search("서울")
        first["results"][0]["name"] = "tampered"
        self.assertEqual(client.search("서울")["results"][0]["name"], "서울")
        self.assertEqual(fetch.call_count, 1)
        now[0] += self.places.CACHE_TTL + 1
        client.search("서울")
        self.assertEqual(fetch.call_count, 2)
        with patch.object(self.places, "CACHE_TTL", 100_000):
            for i in range(self.places.MAX_CACHE_ITEMS + 3):
                now[0] += 61
                client.search(f"city {i}")
        self.assertLessEqual(len(client.cache), self.places.MAX_CACHE_ITEMS)
        self.assertNotIn("city 0", client.cache)

    def test_alias_preserves_explicit_country_qualifier_and_no_coordinates_are_hardcoded(self):
        client, fetch = self.client({"results": [{**SEOUL, "latitude": 37.555}]})
        result = client.search("서울, 대한민국")
        fetch.assert_called_once_with("서울특별시, 대한민국")
        self.assertEqual(result["results"][0]["latitude"], 37.555)
        self.assertTrue(result["warnings"])

    def test_rate_limit_counts_failed_calls_and_does_not_cache_errors(self):
        now = [0.0]
        fetch = Mock(side_effect=self.places.PlaceSearchError("PLACE_SEARCH_UNAVAILABLE", "실패", 502))
        client = self.places.PlaceSearch(fetch=fetch, clock=lambda: now[0])
        for _ in range(self.places.MAX_CALLS_PER_MINUTE):
            self.assert_error(lambda: client.search("서울"), "PLACE_SEARCH_UNAVAILABLE")
        self.assert_error(lambda: client.search("서울"), "PLACE_SEARCH_RATE_LIMITED")
        self.assertEqual(fetch.call_count, self.places.MAX_CALLS_PER_MINUTE)
        now[0] = 61
        self.assert_error(lambda: client.search("서울"), "PLACE_SEARCH_UNAVAILABLE")

    def test_network_concurrency_is_bounded(self):
        client, fetch = self.client()
        for _ in range(self.places.MAX_CONCURRENT_CALLS):
            client.slots.acquire()
        try:
            self.assert_error(lambda: client.search("서울"), "PLACE_SEARCH_RATE_LIMITED")
            fetch.assert_not_called()
        finally:
            for _ in range(self.places.MAX_CONCURRENT_CALLS):
                client.slots.release()


class FetchTests(unittest.TestCase):
    def setUp(self):
        from natal import places
        self.places = places

    def response(self, raw=None, status=200, content_type="application/json"):
        response = Mock()
        response.status = status
        response.headers = {"Content-Type": content_type}
        response.read.return_value = raw if raw is not None else json.dumps({"results": [SEOUL]}).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def test_fixed_https_url_encoded_query_and_bounded_read(self):
        response = self.response()
        with patch.object(self.places.OPENER, "open", return_value=response) as opened:
            self.places.fetch_places("서울 &url=http://127.0.0.1")
        request = opened.call_args.args[0]
        parsed = urlsplit(request.full_url)
        self.assertEqual((parsed.scheme, parsed.netloc, parsed.path), ("https", "geocoding-api.open-meteo.com", "/v1/search"))
        self.assertEqual(parse_qs(parsed.query), {"name": ["서울 &url=http://127.0.0.1"], "count": ["8"], "language": ["ko"], "format": ["json"]})
        self.assertEqual(opened.call_args.kwargs["timeout"], self.places.NETWORK_TIMEOUT)
        response.read.assert_called_once_with(self.places.MAX_RESPONSE_BYTES + 1)
        self.assertIsNone(request.data)

    def test_redirect_and_provider_errors_are_never_empty_success(self):
        from urllib.request import Request
        with self.assertRaises(HTTPError):
            self.places.NoRedirect().redirect_request(Request(self.places.ENDPOINT), None, 302, "redirect", {}, "http://127.0.0.1/")
        for failure, code in ((TimeoutError(), "PLACE_SEARCH_TIMEOUT"), (URLError("secret.internal"), "PLACE_SEARCH_UNAVAILABLE"),
                              (HTTPError(self.places.ENDPOINT, 429, "quota", {}, None), "PLACE_SEARCH_RATE_LIMITED")):
            with patch.object(self.places.OPENER, "open", side_effect=failure), self.assertRaises(self.places.PlaceSearchError) as result:
                self.places.fetch_places("Seoul")
            self.assertEqual(result.exception.code, code)
            self.assertNotIn("secret.internal", str(result.exception))

    def test_oversized_nonjson_and_bad_json_fail(self):
        responses = [self.response(b"x" * (self.places.MAX_RESPONSE_BYTES + 1)), self.response(b"no json"),
                     self.response(b"{}", content_type="text/html"), self.response(b'{"results":[NaN]}')]
        for response in responses:
            with patch.object(self.places.OPENER, "open", return_value=response), self.assertRaises(self.places.PlaceSearchError):
                self.places.fetch_places("Seoul")


class PlacesHTTPTests(unittest.TestCase):
    def setUp(self):
        import server
        self.server = server.make_server(0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def get(self, path, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request("GET", path, headers=headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), json.loads(response.read())
        connection.close()
        return result

    def test_search_http_contract_and_no_other_personal_parameters(self):
        from natal.places import PlaceSearch
        result = PlaceSearch(fetch=lambda _: {"results": [SEOUL]}).search("서울")
        with patch("natal.places.search_places", return_value=result) as search:
            status, headers, body = self.get("/api/places?q=Seoul")
            self.assertEqual(status, 200)
            self.assertEqual(body["results"][0]["id"], 1835848)
            self.assertEqual(headers["Cache-Control"], "no-store")
            search.assert_called_once_with("Seoul")
            for path in ("/api/places", "/api/places?q=a&q=b", "/api/places?q=Seoul&date=2000-01-01", "/api/places?q=Seoul&name=Tester", "/api/places?q=%ff%ff"):
                self.assertEqual(self.get(path)[0], 422)
            self.assertEqual(search.call_count, 1)

    def test_search_errors_and_foreign_origin(self):
        from natal.places import PlaceSearchError
        with patch("natal.places.search_places", side_effect=PlaceSearchError("PLACE_SEARCH_TIMEOUT", "연결 시간 초과", 504)) as search:
            status, _, body = self.get("/api/places?q=Seoul")
            self.assertEqual(status, 504)
            self.assertEqual(body["error"]["code"], "PLACE_SEARCH_TIMEOUT")
            self.assertEqual(self.get("/api/places?q=Seoul", {"Origin": "https://attacker.example"})[0], 403)
            self.assertEqual(search.call_count, 1)


if __name__ == "__main__":
    unittest.main()
