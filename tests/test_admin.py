"""Admin auth, CSRF, submission recording and admin API over the real loopback HTTP server."""
import http.client
import json
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import ANY, patch

import server
from natal import admin_auth, store

PASSWORD = "correct horse battery staple"
VISITOR = "visitorAAAAAAAAAAAAAA"
CHART = {"date": "1985-07-14", "time": "21:45:00", "timezone": "America/New_York", "latitude": 40.7128,
         "longitude": -74.006, "place": "New York", "house_system": "P", "node_mode": "true", "time_accuracy": "reported"}


class AdminTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db = os.path.join(directory.name, "admin.sqlite3")
        env = patch.dict(os.environ, {"NATAL_DB_PATH": self.db, "NATAL_ADMIN_PASSWORD": PASSWORD, "NATAL_ADMIN_SECRET": "test-secret"})
        env.start()
        self.addCleanup(env.stop)
        delay = patch.object(admin_auth, "FAILURE_DELAY", 0)
        delay.start()
        self.addCleanup(delay.stop)
        admin_auth.reset_failures()
        self.addCleanup(admin_auth.reset_failures)
        self.server = server.make_server(0)
        self.port = self.server.server_port
        self.origin = f"http://127.0.0.1:{self.port}"
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()

        def stop():
            self.server.shutdown()
            self.server.server_close()
            thread.join(timeout=2)
        self.addCleanup(stop)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port)
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
            headers = {"Content-Type": "application/json", **(headers or {})}
        connection.request(method, path, body, headers or {})
        response = connection.getresponse()
        result = response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
        connection.close()
        return result

    def login(self):
        status, headers, _ = self.request("POST", "/admin/login", {"password": PASSWORD}, {"Origin": self.origin})
        self.assertEqual(status, 200)
        return headers["set-cookie"].split(";", 1)[0]

    def admin(self, method, path, cookie, body=None, origin=True):
        headers = {"Cookie": cookie}
        if origin:
            headers["Origin"] = self.origin
        status, headers, raw = self.request(method, path, body, headers)
        return status, headers, json.loads(raw) if raw else None

    def chart(self, payload=None, client=None):
        body = dict(payload or CHART)
        if client is not None:
            body["client"] = client
        return self.request("POST", "/api/chart", body)

    # ---- auth ---------------------------------------------------------------

    def test_admin_disabled_without_password(self):
        with patch.dict(os.environ, {"NATAL_ADMIN_PASSWORD": ""}):
            for path in ("/admin/", "/admin/login", "/api/admin/stats"):
                with self.subTest(path=path):
                    self.assertEqual(self.request("GET", path)[0], 503)
            status, _, _ = self.request("POST", "/admin/login", {"password": ""}, {"Origin": self.origin})
            self.assertEqual(status, 503)

    def test_unauthenticated_access_is_blocked(self):
        for path in ("/api/admin/stats", "/api/admin/users", "/api/admin/submissions", "/api/admin/submissions/1", "/api/admin/submissions/1/chart"):
            with self.subTest(path=path):
                status, headers, _ = self.request("GET", path)
                self.assertEqual(status, 401)
                self.assertEqual(headers["cache-control"], "no-store")
                self.assertIn("noindex", headers["x-robots-tag"])
        for path in ("/admin", "/admin/", "/admin/admin.js", "/admin/index.html"):
            with self.subTest(path=path):
                status, headers, _ = self.request("GET", path)
                self.assertEqual(status, 303)
                self.assertEqual(headers["location"], "/admin/login")
        status, _, _ = self.request("DELETE", "/api/admin/submissions/1", headers={"Origin": self.origin})
        self.assertEqual(status, 401)

    def test_login_page_is_public_and_noindex(self):
        status, headers, body = self.request("GET", "/admin/login")
        self.assertEqual(status, 200)
        self.assertIn(b"login-form", body)
        self.assertIn("noindex", headers["x-robots-tag"])
        self.assertIn("script-src 'self'", headers["content-security-policy"])

    def test_bad_password_and_rate_limit(self):
        for _ in range(admin_auth.RATE_MAX_FAILURES):
            status, headers, _ = self.request("POST", "/admin/login", {"password": "wrong"}, {"Origin": self.origin})
            self.assertEqual(status, 401)
            self.assertNotIn("set-cookie", headers)
        status, _, _ = self.request("POST", "/admin/login", {"password": PASSWORD}, {"Origin": self.origin})
        self.assertEqual(status, 429)

    def test_failed_login_is_delayed(self):
        with patch.object(admin_auth, "FAILURE_DELAY", 0.3):
            started = time.monotonic()
            self.request("POST", "/admin/login", {"password": "wrong"}, {"Origin": self.origin})
            self.assertGreaterEqual(time.monotonic() - started, 0.3)

    def test_form_login_sets_strict_httponly_cookie(self):
        status, headers, _ = self.request("POST", "/admin/login", f"password={PASSWORD.replace(' ', '+')}",
                                          {"Content-Type": "application/x-www-form-urlencoded", "Origin": self.origin})
        self.assertEqual(status, 303)
        self.assertEqual(headers["location"], "/admin/")
        cookie = headers["set-cookie"]
        for part in ("HttpOnly", "SameSite=Strict", "Path=/", "Max-Age=43200"):
            self.assertIn(part, cookie)
        status, _, body = self.request("GET", "/admin/", headers={"Cookie": cookie.split(";", 1)[0]})
        self.assertEqual(status, 200)
        self.assertIn(b"admin.js", body)

    def test_login_requires_same_origin(self):
        for headers in ({}, {"Origin": "https://attacker.example"}):
            with self.subTest(headers=headers):
                status, response_headers, _ = self.request("POST", "/admin/login", {"password": PASSWORD}, headers)
                self.assertEqual(status, 403)
                self.assertNotIn("set-cookie", response_headers)

    def test_tampered_and_expired_cookies_rejected(self):
        cookie = self.login()
        name, token = cookie.split("=", 1)
        exp, signature = token.split(".", 1)
        forged_future = f"{int(exp) + 10_000}.{signature}"
        flipped = f"{exp}.{signature[:-1]}{'0' if signature[-1] != '0' else '1'}"
        past = int(time.time()) - 10
        expired = f"{past}.{admin_auth.sign(past)}"
        for bad in (forged_future, flipped, expired, "garbage", f"{exp}.", ".abc"):
            with self.subTest(token=bad):
                status, _, _ = self.admin("GET", "/api/admin/stats", f"{name}={bad}")
                self.assertEqual(status, 401)
        self.assertEqual(self.admin("GET", "/api/admin/stats", cookie)[0], 200)

    def test_secret_rotation_invalidates_sessions(self):
        cookie = self.login()
        with patch.dict(os.environ, {"NATAL_ADMIN_SECRET": "rotated"}):
            self.assertEqual(self.admin("GET", "/api/admin/stats", cookie)[0], 401)

    def test_delete_requires_same_origin(self):
        cookie = self.login()
        self.chart(client={"visitor_id": VISITOR})
        row_id = store.list_submissions()["submissions"][0]["id"]
        status, _, body = self.admin("DELETE", f"/api/admin/submissions/{row_id}", cookie, origin=False)
        self.assertEqual((status, body["error"]["code"]), (403, "CSRF_REJECTED"))
        status, _, _ = self.request("DELETE", f"/api/admin/submissions/{row_id}", headers={"Cookie": cookie, "Origin": "https://attacker.example"})
        self.assertEqual(status, 403)
        self.assertIsNotNone(store.get_submission(row_id))

    def test_logout_clears_cookie(self):
        cookie = self.login()
        status, headers, _ = self.request("POST", "/admin/logout", "x=1", {"Cookie": cookie, "Origin": self.origin,
                                                                             "Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(status, 303)
        self.assertIn("Max-Age=0", headers["set-cookie"])

    # ---- recording ------------------------------------------------------------

    def test_success_is_recorded_and_client_never_reaches_result(self):
        client = {"visitor_id": VISITOR, "name": "가상인물", "store_consent": True, "utm": {"utm_source": "threads", "utm_campaign": "launch"}, "short_code": "abc234"}
        status, _, raw_with = self.chart(client=client)
        self.assertEqual(status, 200)
        status, _, raw_without = self.chart()
        with_client, without_client = json.loads(raw_with), json.loads(raw_without)
        self.assertNotIn("client", with_client["input"])
        self.assertNotIn(b"visitorAAAA", raw_with)
        self.assertEqual(with_client, without_client)  # deterministic, no run metadata
        rows = store.list_submissions()["submissions"]
        self.assertEqual(len(rows), 2)
        item = store.get_submission(rows[-1]["id"])
        self.assertEqual(item["raw_input"], CHART)
        self.assertEqual((item["visitor_id"], item["display_name"], item["status"], item["consent"]), (VISITOR, "가상인물", "success", store.CONSENT_OPT_IN))
        self.assertEqual((item["utm_source"], item["utm_campaign"], item["short_code"]), ("threads", "launch", "abc234"))
        self.assertEqual(item["summary"]["fingerprint"], with_client["metadata"]["input_fingerprint"])
        self.assertEqual((item["sun_sign"], item["moon_sign"]), ("게", "쌍둥이"))

    def test_chart_error_is_recorded(self):
        status, _, _ = self.chart({**CHART, "latitude": 91}, {"visitor_id": VISITOR})
        self.assertEqual(status, 422)
        row = store.list_submissions()["submissions"][0]
        self.assertEqual((row["status"], row["error_code"], row["visitor_id"]), ("INVALID_INPUT", "INVALID_INPUT", VISITOR))

    def test_invalid_client_does_not_break_chart(self):
        status, _, _ = self.chart(client={"visitor_id": "<bad>", "utm": {"utm_source": "a\"b<c>"}, "name": 5})
        self.assertEqual(status, 200)
        row = store.list_submissions()["submissions"][0]
        self.assertEqual((row["visitor_id"], row["utm_source"], row["display_name"]), (None, None, None))

    def test_storage_failure_does_not_break_chart(self):
        with patch.object(store, "record_submission", side_effect=RuntimeError("disk full")):
            status, _, raw = self.chart(client={"visitor_id": VISITOR})
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(raw)["houses"]), 12)
        with patch.dict(os.environ, {"NATAL_DB_PATH": os.path.join(self.db, "missing-dir", "x.sqlite3")}):
            status, _, _ = self.chart()
        self.assertEqual(status, 200)

    def test_chart_without_consent_stores_no_birth_input(self):
        status, _, _ = self.chart(client={"visitor_id": VISITOR, "name": "가상인물", "utm": {"utm_source": "threads"}})
        self.assertEqual(status, 200)
        item = store.get_submission(store.list_submissions()["submissions"][0]["id"])
        self.assertEqual((item["raw_input"], item["display_name"], item["place"], item["consent"]), (None, None, None, 0))
        self.assertEqual((item["visitor_id"], item["sun_sign"], item["utm_source"]), (VISITOR, "게", "threads"))
        cookie = self.login()
        status, _, body = self.admin("GET", f"/api/admin/submissions/{item['id']}/chart", cookie)
        self.assertEqual((status, body["error"]["code"]), (409, "RAW_INPUT_NOT_STORED"))

    def test_visitor_can_delete_own_records(self):
        self.chart(client={"visitor_id": VISITOR, "store_consent": True})
        self.chart(client={"visitor_id": VISITOR})
        self.chart(client={"visitor_id": "visitorBBBBBBBBBBBBBB", "store_consent": True})
        status, _, raw = self.request("POST", "/api/my-data/delete", {"visitor_id": VISITOR}, {"Origin": self.origin})
        self.assertEqual((status, json.loads(raw)), (200, {"deleted": 2}))
        self.assertEqual([r["visitor_id"] for r in store.list_submissions()["submissions"]], ["visitorBBBBBBBBBBBBBB"])
        status, _, raw = self.request("POST", "/api/my-data/delete", {"visitor_id": VISITOR}, {"Origin": self.origin})
        self.assertEqual((status, json.loads(raw)), (200, {"deleted": 0}))
        for body in ({"visitor_id": "%"}, {"visitor_id": None}, {}, {"visitor_id": ["x" * 20]}):
            with self.subTest(body=body):
                status, _, raw = self.request("POST", "/api/my-data/delete", body, {"Origin": self.origin})
                self.assertEqual((status, json.loads(raw)["error"]["code"]), (400, "INVALID_VISITOR"))
        status, _, _ = self.request("POST", "/api/my-data/delete", {"visitor_id": "visitorBBBBBBBBBBBBBB"},
                                    {"Origin": "https://attacker.example"})
        self.assertEqual(status, 403)
        self.assertEqual(store.list_submissions()["total"], 1)

    # ---- admin API ------------------------------------------------------------

    def test_stats_users_submissions_detail_chart_and_delete(self):
        cookie = self.login()
        self.chart(client={"visitor_id": VISITOR, "name": "A", "store_consent": True})
        self.chart(client={"visitor_id": VISITOR, "name": "B", "store_consent": True})
        self.chart({**CHART, "latitude": 91}, {"visitor_id": "visitorBBBBBBBBBBBBBB", "store_consent": True})
        status, _, stats = self.admin("GET", "/api/admin/stats", cookie)
        self.assertEqual(status, 200)
        self.assertEqual(stats["totals"], {"submissions": 3, "success": 2, "failed": 1, "unique_visitors": 2, "unique_names": 2})
        _, _, users = self.admin("GET", "/api/admin/users", cookie)
        by_id = {u["visitor_id"]: u for u in users["users"]}
        self.assertEqual((by_id[VISITOR]["count"], by_id[VISITOR]["latest_name"], by_id[VISITOR]["names"]), (2, "B", ["A", "B"]))
        _, _, listing = self.admin("GET", f"/api/admin/submissions?visitor_id={VISITOR}&limit=10", cookie)
        self.assertEqual(listing["total"], 2)
        row_id = listing["submissions"][0]["id"]
        _, _, detail = self.admin("GET", f"/api/admin/submissions/{row_id}", cookie)
        self.assertEqual(detail["raw_input"], CHART)
        status, _, chart = self.admin("GET", f"/api/admin/submissions/{row_id}/chart", cookie)
        self.assertEqual(status, 200)
        moon = next(b for b in chart["bodies"] if b["id"] == "Moon")
        self.assertAlmostEqual(moon["longitude"], 77.94899, places=4)
        failed_id = self.admin("GET", "/api/admin/submissions?status=failed", cookie)[2]["submissions"][0]["id"]
        status, _, body = self.admin("GET", f"/api/admin/submissions/{failed_id}/chart", cookie)
        self.assertEqual((status, body["error"]["code"]), (422, "INVALID_INPUT"))
        self.assertEqual(self.admin("DELETE", f"/api/admin/submissions/{row_id}", cookie)[2], {"deleted": 1})
        self.assertEqual(self.admin("GET", f"/api/admin/submissions/{row_id}", cookie)[0], 404)
        self.assertEqual(self.admin("DELETE", f"/api/admin/users/{VISITOR}", cookie)[2], {"deleted": 1})
        self.assertEqual(self.admin("DELETE", f"/api/admin/users/{VISITOR}", cookie)[0], 404)
        self.assertEqual(self.admin("GET", "/api/admin/stats", cookie)[2]["totals"]["submissions"], 1)

    def test_admin_query_validation(self):
        cookie = self.login()
        for path in ("/api/admin/stats?from=bad", "/api/admin/submissions?visitor_id=x", "/api/admin/submissions?limit=abc",
                     "/api/admin/stats?unknown=1", "/api/admin/users?q=a&q=b"):
            with self.subTest(path=path):
                self.assertEqual(self.admin("GET", path, cookie)[0], 422)
        self.assertEqual(self.admin("DELETE", "/api/admin/users/%25", cookie)[0], 422)
        self.assertEqual(self.admin("GET", "/api/admin/nope", cookie)[0], 404)

    def test_admin_files_not_served_by_public_static_route(self):
        # web/admin must only be reachable through the gated admin router.
        status, _, _ = self.request("GET", "/admin/admin.js")
        self.assertEqual(status, 303)
        status, _, _ = self.request("GET", "/admin/../admin/admin.js")
        self.assertIn(status, (303, 404))

    # ---- engine inspector -------------------------------------------------------

    def test_engine_inspector_files_require_login(self):
        for path in ("/admin/engine-check.html", "/admin/engine-check.js", "/admin/engine-bundle.js"):
            with self.subTest(path=path):
                status, headers, _ = self.request("GET", path)
                self.assertEqual(status, 303)
                self.assertEqual(headers["location"], "/admin/login")
        cookie = self.login()
        status, headers, body = self.request("GET", "/admin/engine-check.html", headers={"Cookie": cookie})
        self.assertEqual(status, 200)
        self.assertIn(b"engine-check.js", body)
        self.assertIn("noindex", headers["x-robots-tag"])
        status, _, body = self.request("GET", "/admin/engine-check.js", headers={"Cookie": cookie})
        self.assertEqual(status, 200)
        self.assertIn(b"/api/admin/engine/", body)

    def test_engine_inspector_runs_every_tool_without_recording(self):
        cookie = self.login()
        other = {**CHART, "date": "1990-05-15", "time": "08:30:00", "timezone": "Asia/Seoul", "latitude": 37.5665, "longitude": 126.978, "place": "Seoul"}
        moment = {"date": "2026-10-03", "time": "12:00", "timezone": "Asia/Seoul"}
        cases = {
            "chart": (CHART, "bodies"),
            "synastry": ({"person_a": CHART, "person_b": other}, "overlays"),
            "composite": ({"person_a": CHART, "person_b": other}, "composite"),
            "transits": ({"natal": CHART, "moment": moment}, "transit"),
            "solar-return": ({"natal": CHART, "year": 2026, "location": {"latitude": 37.5665, "longitude": 126.978, "timezone": "Asia/Seoul", "place": "Seoul"}}, "exact"),
            "progressions": ({"natal": CHART, "moment": moment}, "progressed"),
        }
        for tool, (payload, key) in cases.items():
            with self.subTest(tool=tool):
                status, _, data = self.admin("POST", f"/api/admin/engine/{tool}", cookie, payload)
                self.assertEqual(status, 200, data)
                self.assertEqual(data["status"], "calculated")
                self.assertIn(key, data)
        status, _, data = self.admin("GET", "/api/admin/submissions", cookie)
        self.assertEqual(status, 200)
        self.assertEqual(data["total"], 0)

    def test_engine_inspector_presets_crud(self):
        person = {"name": "가상A", "calendar": "gregorian", "date": "1990-05-15", "time": "08:30", "time_unknown": False,
                  "place": {"label": "Seoul", "latitude": 37.5665, "longitude": 126.978, "timezone": "Asia/Seoul",
                            "source": {"mode": "manual", "provider": "user", "place_id": None, "label": "Seoul", "extra": "x"}}}
        path = "/api/admin/engine/presets"
        self.assertEqual(self.request("GET", path)[0], 401)
        self.assertEqual(self.request("POST", path, person, {"Origin": self.origin})[0], 401)
        cookie = self.login()
        self.assertEqual(self.admin("POST", path, cookie, person, origin=False)[0], 403)
        self.assertEqual(self.admin("GET", path, cookie)[2], {"presets": [], "env_presets": []})

        status, _, created = self.admin("POST", path, cookie, person)
        self.assertEqual(status, 201)
        self.assertNotIn("extra", created["place"]["source"])
        self.assertEqual(self.admin("POST", path, cookie, person)[0], 422)  # same name twice
        unknown = {**person, "name": "가상B", "time_unknown": True, "time": "99:99"}
        status, _, other = self.admin("POST", path, cookie, unknown)
        self.assertEqual((status, other["time"]), (201, None))
        listed = self.admin("GET", path, cookie)[2]["presets"]
        self.assertEqual([(p["id"], p["name"]) for p in listed], [(created["id"], "가상A"), (other["id"], "가상B")])

        edited = {**person, "date": "1991-01-02", "time": "23:59"}
        self.assertEqual(self.admin("POST", f"{path}/{created['id']}", cookie, edited), (200, ANY, {"updated": 1}))
        self.assertEqual(self.admin("POST", f"{path}/{created['id']}", cookie, {**edited, "name": "가상B"})[0], 422)
        self.assertEqual(self.admin("POST", f"{path}/9999", cookie, edited)[0], 404)
        self.assertEqual(self.admin("POST", f"{path}/%C2%B2", cookie, edited)[0], 404)
        self.assertEqual(self.admin("DELETE", f"{path}/{'9' * 30}", cookie)[0], 404)
        self.assertEqual(self.admin("GET", path, cookie)[2]["presets"][0]["date"], "1991-01-02")

        self.assertEqual(self.admin("DELETE", f"{path}/{created['id']}", cookie, origin=False)[0], 403)
        self.assertEqual(self.admin("DELETE", f"{path}/{created['id']}", cookie)[2], {"deleted": 1})
        self.assertEqual(self.admin("DELETE", f"{path}/{created['id']}", cookie)[0], 404)
        self.assertEqual([p["name"] for p in self.admin("GET", path, cookie)[2]["presets"]], ["가상B"])

    def test_engine_inspector_preset_validation(self):
        cookie = self.login()
        base = {"name": "가상", "calendar": "gregorian", "date": "1990-05-15", "time": "08:30",
                "place": {"label": "Seoul", "latitude": 37.5665, "longitude": 126.978, "timezone": "Asia/Seoul"}}
        bad = [{**base, "name": "  "}, {**base, "calendar": "julian"}, {**base, "date": "1990/05/15"}, {**base, "time": "24:00"},
               {**base, "time": None}, {**base, "place": None}, {**base, "place": {**base["place"], "latitude": 91}},
               {**base, "place": {**base["place"], "longitude": True}}, {**base, "place": {**base["place"], "timezone": "Mars/Base"}},
               {**base, "place": {**base["place"], "label": ""}}, {**base, "date": "1990-02-31"}, ["not", "an", "object"]]
        for body in bad:
            with self.subTest(body=body):
                status, _, data = self.admin("POST", "/api/admin/engine/presets", cookie, body)
                self.assertIn(status, (400, 422))
                self.assertIsNotNone(data["error"]["message"])
        self.assertEqual(self.admin("GET", "/api/admin/engine/presets", cookie)[2]["presets"], [])

    def test_engine_inspector_imports_environment_presets_once(self):
        people = [{"name": "A", "calendar": "gregorian", "date": "1990-05-15", "time": "08:30", "time_unknown": False,
                   "place": {"label": "Seoul", "latitude": 37.5665, "longitude": 126.978, "timezone": "Asia/Seoul"}},
                  {"name": "broken"}, "junk"]
        path = "/api/admin/engine/presets"
        cookie = self.login()
        with patch.dict(os.environ, {server.PRESETS_VAR: json.dumps(people)}):
            data = self.admin("GET", path, cookie)[2]
            self.assertEqual(([p["name"] for p in data["env_presets"]], data["presets"]), (["A"], []))
            self.assertEqual(self.admin("POST", f"{path}/import", cookie)[2], {"imported": 1})
            self.assertEqual(self.admin("POST", f"{path}/import", cookie)[2], {"imported": 0})
            data = self.admin("GET", path, cookie)[2]
            self.assertEqual(([p["name"] for p in data["presets"]], data["env_presets"]), (["A"], []))
        with patch.dict(os.environ, {server.PRESETS_VAR: "not json"}):
            self.assertEqual(self.admin("GET", path, cookie)[2]["env_presets"], [])
        # Only the presets route skips the body: a UTM channel keyed "import" still updates normally.
        self.assertEqual(self.admin("POST", "/api/admin/utm/channels", cookie,
                                    {"key": "import", "label_ko": "가져옴", "utm_source": "imp", "utm_medium": "social"})[0], 201)
        self.assertEqual(self.admin("POST", "/api/admin/utm/channels/import", cookie, {"label_ko": "수정"}), (200, ANY, {"updated": 1}))

    def test_engine_inspector_errors(self):
        cookie = self.login()
        self.assertEqual(self.admin("POST", "/api/admin/engine/chart", cookie, CHART, origin=False)[0], 403)
        self.assertEqual(self.admin("POST", "/api/admin/engine/nope", cookie, CHART)[0], 404)
        self.assertEqual(self.request("POST", "/api/admin/engine/chart", CHART, {"Origin": self.origin})[0], 401)
        status, _, data = self.admin("POST", "/api/admin/engine/chart", cookie, {**CHART, "house_system": "ZZ"})
        self.assertEqual(status, 422)
        self.assertEqual(data["error"]["code"], "INVALID_INPUT")
        status, _, data = self.admin("POST", "/api/admin/engine/synastry", cookie, {"person_a": CHART, "person_b": {**CHART, "time_accuracy": "unknown", "time": None}})
        self.assertIn(status, (200, 422))


if __name__ == "__main__":
    unittest.main()
