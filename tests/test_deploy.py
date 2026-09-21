"""Deployment boundary: allowed hosts, proxy headers on Vercel, production secret, api/index.py, Postgres backend."""
import http.client
import importlib.util
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import server
from natal import admin_auth, store

ROOT = Path(__file__).resolve().parent.parent
PASSWORD = "correct horse battery staple"
VERCEL_HOST = "natal-test.vercel.app"


class ServerHarness(unittest.TestCase):
    handler_class = server.ChartHandler

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        # Every Vercel/host variable is cleared so the developer's shell cannot leak into the test.
        env = patch.dict(os.environ, {"NATAL_DB_PATH": os.path.join(directory.name, "t.sqlite3"),
                                      "NATAL_ADMIN_PASSWORD": PASSWORD, "NATAL_ADMIN_SECRET": "test-secret"})
        env.start()
        self.addCleanup(env.stop)
        for name in ("VERCEL", "NATAL_ALLOWED_HOSTS", "DATABASE_URL", "POSTGRES_URL", *server.VERCEL_HOST_VARS):
            os.environ.pop(name, None)
        delay = patch.object(admin_auth, "FAILURE_DELAY", 0)
        delay.start()
        self.addCleanup(delay.stop)
        admin_auth.reset_failures()
        self.addCleanup(admin_auth.reset_failures)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.handler_class)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()

        def stop():
            self.server.shutdown()
            self.server.server_close()
            thread.join(timeout=2)
        self.addCleanup(stop)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        if isinstance(body, dict):
            body = json.dumps(body)
            headers = {"Content-Type": "application/json", **(headers or {})}
        connection.request(method, path, body, headers or {})
        response = connection.getresponse()
        result = response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
        connection.close()
        return result


class AllowedHostTests(ServerHarness):
    def test_configured_host_and_origin_are_accepted(self):
        os.environ["NATAL_ALLOWED_HOSTS"] = " Natal.Example , other.example:8443"
        self.assertEqual(self.request("GET", "/api/health", headers={"Host": "natal.example"})[0], 200)
        self.assertEqual(self.request("GET", "/api/health", headers={"Host": "other.example:8443"})[0], 200)
        status, _, _ = self.request("POST", "/api/chart", {}, {"Host": "natal.example", "Origin": "http://natal.example"})
        self.assertEqual(status, 422)  # passed the host/origin gate, rejected only as invalid chart input

    def test_unlisted_host_and_foreign_origin_are_rejected(self):
        os.environ["NATAL_ALLOWED_HOSTS"] = "natal.example"
        self.assertEqual(self.request("GET", "/", headers={"Host": "attacker.example"})[0], 403)
        status, _, _ = self.request("POST", "/api/chart", {}, {"Host": "natal.example", "Origin": "http://attacker.example"})
        self.assertEqual(status, 403)

    def test_localhost_defaults_still_work(self):
        os.environ["NATAL_ALLOWED_HOSTS"] = "natal.example"
        self.assertEqual(self.request("GET", "/api/health")[0], 200)

    def test_forwarded_headers_ignored_outside_vercel(self):
        os.environ["NATAL_ALLOWED_HOSTS"] = "natal.example"
        status, _, _ = self.request("GET", "/api/health", headers={"Host": "attacker.example", "X-Forwarded-Host": "natal.example"})
        self.assertEqual(status, 403)
        status, headers, _ = self.request("POST", "/admin/login", {"password": PASSWORD},
                                          {"Origin": f"http://127.0.0.1:{self.server.server_port}", "X-Forwarded-Proto": "https"})
        self.assertEqual(status, 200)
        self.assertNotIn("Secure", headers["set-cookie"])


class VercelTests(ServerHarness):
    def setUp(self):
        super().setUp()
        os.environ.update({"VERCEL": "1", "NATAL_ALLOWED_HOSTS": "natal.example", "VERCEL_URL": VERCEL_HOST})

    def proxied(self, host=VERCEL_HOST, proto="https"):
        return {"Host": "internal.lambda", "X-Forwarded-Host": host, "X-Forwarded-Proto": proto}

    def login(self, headers):
        # Admin on Vercel needs DATABASE_URL; pretend it is set while the store itself is unreachable,
        # so login throttling falls back to memory and nothing touches a real database.
        with patch.object(store, "database_url", return_value="postgresql://unused"), \
             patch.object(store, "connect", side_effect=OSError("no database in this test")):
            return self.request("POST", "/admin/login", {"password": PASSWORD}, headers)

    def test_vercel_host_and_localhost_defaults(self):
        self.assertEqual(self.request("GET", "/api/health", headers=self.proxied())[0], 200)
        self.assertEqual(self.request("GET", "/api/health", headers=self.proxied("natal.example"))[0], 200)
        self.assertEqual(self.request("GET", "/api/health", headers=self.proxied("attacker.example"))[0], 403)
        # Loopback names are not public hosts on Vercel.
        self.assertEqual(self.request("GET", "/api/health")[0], 403)

    def test_session_cookie_is_secure_behind_https_proxy(self):
        status, headers, _ = self.login({**self.proxied(), "Origin": f"https://{VERCEL_HOST}"})
        self.assertEqual(status, 200)
        cookie = headers["set-cookie"]
        for part in ("HttpOnly", "SameSite=Strict", "Secure"):
            self.assertIn(part, cookie)

    def test_http_origin_rejected_when_proxy_says_https(self):
        status, headers, _ = self.login({**self.proxied(), "Origin": f"http://{VERCEL_HOST}"})
        self.assertEqual(status, 403)
        self.assertNotIn("set-cookie", headers)

    def test_admin_requires_configured_secret_in_production(self):
        del os.environ["NATAL_ADMIN_SECRET"]
        with patch.object(store, "database_url", return_value="postgresql://unused"):
            for path in ("/api/admin/stats", "/admin/login"):
                with self.subTest(path=path):
                    status, _, body = self.request("GET", path, headers=self.proxied())
                    self.assertEqual(status, 503)
            status, _, body = self.request("GET", "/api/admin/stats", headers=self.proxied())
            self.assertEqual(json.loads(body)["error"]["code"], "ADMIN_SECRET_REQUIRED")

    def test_admin_requires_database_url_in_production(self):
        status, _, body = self.request("GET", "/api/admin/stats", headers=self.proxied())
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body)["error"]["code"], "DATABASE_REQUIRED")


def load_vercel_entrypoint():
    spec = importlib.util.spec_from_file_location("vercel_api_index", ROOT / "api" / "index.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VercelEntrypointTests(ServerHarness):
    handler_class = load_vercel_entrypoint().handler

    def test_entrypoint_serves_page_and_chart(self):
        self.assertTrue(issubclass(self.handler_class, server.ChartHandler))
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["content-type"])
        self.assertEqual(self.request("GET", "/api/health")[0], 200)
        payload = {"date": "1985-07-14", "time": "21:45:00", "timezone": "America/New_York", "latitude": 40.7128,
                   "longitude": -74.006, "place": "reference", "house_system": "P", "node_mode": "true", "time_accuracy": "reported"}
        status, _, raw = self.request("POST", "/api/chart", payload)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["normalized"]["utc"], "1985-07-15T01:45:00Z")

    def test_vercel_config_bundles_runtime_files(self):
        config = json.loads((ROOT / "vercel.json").read_text())
        self.assertEqual(config["rewrites"], [{"source": "/(.*)", "destination": "/api/index"}])
        include = config["functions"]["api/index.py"]["includeFiles"]
        for part in ("natal/**", "web/**", "data/ephe/**", "data/manifest.json", "server.py"):
            self.assertIn(part, include)
        requirements = (ROOT / "requirements.txt").read_text()
        self.assertNotIn("playwright", requirements)
        self.assertIn("psycopg[binary]==", requirements)


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "TEST_DATABASE_URL not set: Postgres backend test skipped")
class PostgresBackendTests(unittest.TestCase):
    """Runs the real store/utm/login code against Postgres. Use a throwaway database: tables are truncated."""

    TABLES = ("utm_clicks", "utm_links", "utm_campaigns", "submissions", "login_attempts")

    @classmethod
    def setUpClass(cls):
        import psycopg
        url = os.environ["TEST_DATABASE_URL"]
        with psycopg.connect(url, autocommit=True, prepare_threshold=None) as connection:
            schema = (ROOT / "db" / "schema.sql").read_text()
            connection.execute(schema)
            connection.execute(schema)  # idempotent

    def setUp(self):
        import psycopg
        env = patch.dict(os.environ, {"DATABASE_URL": os.environ["TEST_DATABASE_URL"], "NATAL_ADMIN_SECRET": "pg-test"})
        env.start()
        self.addCleanup(env.stop)
        with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as connection:
            connection.execute(f"TRUNCATE {', '.join(self.TABLES)} RESTART IDENTITY")

    def test_submissions_stats_users_and_delete(self):
        from natal import utm  # noqa: F401  (import check under Postgres)
        visitor = "visitorAAAAAAAAAAAAAA"
        result = {"bodies": [{"id": "Sun", "sign_index": 5}, {"id": "Moon", "sign_index": 0}],
                  "angles": [{"id": "ASC", "sign_index": 0}], "metadata": {"input_fingerprint": "fp"}}
        with patch.object(store, "now_iso", return_value="2026-09-20T10:00:00Z"):
            first = store.record_submission({"place": "서울"}, {"visitor_id": visitor, "name": "가상인물", "consent": True,
                                                              "utm": {"utm_source": "instagram"}}, result=result)
            store.record_submission({"place": "서울"}, {"visitor_id": visitor, "name": "Tester"}, error_code="INVALID_INPUT")
            store.record_submission({}, {}, error_code="INVALID_INPUT")
        self.assertIsInstance(first, int)
        totals = store.stats("2026-09-20", "2026-09-20")["totals"]
        self.assertEqual(totals, {"submissions": 3, "success": 1, "failed": 2, "unique_visitors": 1, "unique_names": 2})
        users = store.users(q="VISITORaaa")  # case-insensitive like SQLite
        self.assertEqual(users["users"][0]["names"], ["Tester", "가상인물"])
        self.assertEqual(users["anonymous_submissions"], 1)
        listing = store.list_submissions(q="서", status="failed")
        self.assertEqual(listing["total"], 1)
        item = store.get_submission(first)
        self.assertEqual((item["raw_input"], item["consent"], item["sun_sign"]), ({"place": "서울"}, 1, "처녀"))
        self.assertEqual(store.delete_visitor(visitor), 2)
        self.assertEqual(store.delete_submission(first), 0)

    def test_utm_links_clicks_and_stats(self):
        from natal import utm
        utm.create_campaign({"key": "fall", "label_ko": "가을"})
        with self.assertRaises(store.StoreError):
            utm.create_campaign({"key": "fall", "label_ko": "중복"})
        created = utm.create_links({"target_path": "/", "channel_keys": ["instagram", "kakao"], "campaign_key": "fall"})["links"]
        self.assertEqual([link["existed"] for link in created], [False, False])
        again = utm.create_links({"target_path": "/", "channel_keys": ["instagram"], "campaign_key": "fall"})["links"][0]
        self.assertEqual((again["existed"], again["code"]), (True, created[0]["code"]))
        code = created[0]["code"]
        self.assertEqual(utm.resolve_link(code)["utm_source"], "instagram")
        utm.record_click(code, True, None, "kakaotalk-inapp")
        utm.record_click(code, False, "preview-bot", "facebook")
        store.record_submission({}, {"short_code": code, "utm": {"utm_source": "instagram"}}, error_code="X")
        stats = utm.utm_stats()
        self.assertEqual((stats["totals"]["clicks"], stats["totals"]["bot_clicks"], stats["totals"]["submissions"]), (1, 1, 1))
        self.assertEqual(utm.list_links(q=code[:3])["links"][0]["clicks"], 1)
        self.assertEqual(utm.set_archived(code, True), 1)
        self.assertIsNone(utm.resolve_link(code))
        self.assertEqual(utm.update_channel("instagram", {"is_active": False}), 1)
        self.assertEqual(utm.list_channels()["channels"][-1]["key"], "instagram")

    def test_login_rate_limit_is_shared_in_database(self):
        for _ in range(admin_auth.RATE_MAX_FAILURES):
            admin_auth.note_failure("203.0.113.9")
        with admin_auth._FAILURE_LOCK:
            admin_auth._FAILURES.clear()  # a fresh serverless instance has no memory of earlier failures
        self.assertTrue(admin_auth.rate_limited("203.0.113.9"))
        self.assertFalse(admin_auth.rate_limited("203.0.113.10"))
        admin_auth.reset_failures("203.0.113.9")
        self.assertFalse(admin_auth.rate_limited("203.0.113.9"))


class DatabaseUrlTests(unittest.TestCase):
    def test_database_url_wins_then_postgres_url_fallback_and_url_is_untouched(self):
        pooled = "postgresql://u:p@ep-x-pooler.region.aws.neon.tech/db?sslmode=require"
        with patch.dict(os.environ, {"DATABASE_URL": pooled, "POSTGRES_URL": "postgresql://other/db"}):
            self.assertEqual(store.database_url(), pooled)
        with patch.dict(os.environ, {"POSTGRES_URL": pooled}):
            os.environ.pop("DATABASE_URL", None)
            self.assertEqual(store.database_url(), pooled)
        with patch.dict(os.environ, {}):
            os.environ.pop("DATABASE_URL", None)
            os.environ.pop("POSTGRES_URL", None)
            self.assertIsNone(store.database_url())


class SqliteSharedRateLimitTests(unittest.TestCase):
    def test_rate_limit_survives_process_memory_loss(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        with patch.dict(os.environ, {"NATAL_DB_PATH": os.path.join(directory.name, "r.sqlite3")}):
            os.environ.pop("DATABASE_URL", None)
            os.environ.pop("POSTGRES_URL", None)
            admin_auth.reset_failures()
            for _ in range(admin_auth.RATE_MAX_FAILURES):
                admin_auth.note_failure("198.51.100.7")
            with admin_auth._FAILURE_LOCK:
                admin_auth._FAILURES.clear()
            self.assertTrue(admin_auth.rate_limited("198.51.100.7"))
            self.assertFalse(admin_auth.rate_limited("198.51.100.7", now=10**12))
            admin_auth.reset_failures()


class SqlTranslationTests(unittest.TestCase):
    def test_placeholders_like_and_percent(self):
        sql = "SELECT '?' AS q, x FROM t WHERE a = ? AND b LIKE ? ESCAPE '\\' AND c = '5%'"
        self.assertEqual(store._to_pyformat(sql),
                         "SELECT '?' AS q, x FROM t WHERE a = %s AND b ILIKE %s ESCAPE '\\' AND c = '5%%'")


if __name__ == "__main__":
    unittest.main()
