"""UTM builder: migration, codes, target validation, short-link redirect, admin API and attribution."""
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from natal import store, utm
from test_admin import CHART, AdminTests

HUMAN_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 KAKAOTALK 10.4.0"


class UtmStoreTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = os.path.join(directory.name, "admin.sqlite3")
        env = patch.dict(os.environ, {"NATAL_DB_PATH": self.path})
        env.start()
        self.addCleanup(env.stop)

    def campaign(self, key="fall"):
        utm.create_campaign({"key": key, "label_ko": "가을"})

    def test_upgrade_from_user_version_1_keeps_rows_and_seeds_channels(self):
        connection = sqlite3.connect(self.path)
        connection.executescript(store.MIGRATIONS[1])
        connection.execute("PRAGMA user_version = 1")
        connection.execute("INSERT INTO submissions (created_at, raw_input, status, short_code) VALUES ('2026-01-01T00:00:00Z', '{}', 'success', 'abcdef')")
        connection.commit()
        connection.close()
        channels = utm.list_channels()["channels"]
        self.assertGreaterEqual(len(channels), 5)
        self.assertIn("instagram", {c["key"] for c in channels})
        connection = sqlite3.connect(self.path)
        self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], store.SCHEMA_VERSION)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM submissions").fetchone()[0], 1)
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"utm_channels", "utm_campaigns", "utm_links", "utm_clicks"} <= tables)
        columns = {r[1] for r in connection.execute("PRAGMA table_info(utm_clicks)")}
        self.assertFalse({"ip", "user_agent", "ua"} & columns)
        connection.close()

    def test_code_alphabet_and_shape(self):
        for ch in "lo01":
            self.assertNotIn(ch, utm.ALPHABET)
        codes = {utm.make_code() for _ in range(300)}
        self.assertGreater(len(codes), 290)
        self.assertTrue(all(utm.is_code_shaped(c) for c in codes))
        for bad in ("abc", "abcdefg", "abcde1", "ABCDEF", "abcdeo", "abcd/e", None, 123456):
            self.assertFalse(utm.is_code_shaped(bad), bad)

    def test_target_path_validation(self):
        for good in ("/", "/about", "/a/b-c_d.e~f/"):
            self.assertEqual(utm.normalize_target_path(good), good)
        for bad in ("https://evil.com", "//evil.com", "javascript:alert(1)", "/\\evil.com", "\\\\evil", "/https://evil.com",
                    "/a\nb", "/a\x00b", "/a b", "/../x", "/admin", "/admin/x", "/api/admin", "/l/abcdef", "about", "",
                    "/%2F%2Fevil.com", "/a?x=1", "/a#b", "/" + "a" * 250, None):
            self.assertIsNone(utm.normalize_target_path(bad), bad)

    def test_schema_rejects_external_target_even_without_python_validation(self):
        utm.list_channels()
        connection = sqlite3.connect(self.path)
        for bad in ("//evil.com", "https://evil.com", "/\\evil"):
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO utm_links (code, target_path, utm_source, utm_medium, utm_campaign, created_at) "
                                   "VALUES ('abcdef', ?, 's', 'm', 'c', 'x')", (bad,))
        connection.close()

    def test_duplicate_combo_returns_existing_and_content_distinguishes(self):
        self.campaign()
        first = utm.create_links({"target_path": "/", "channel_keys": ["instagram", "kakao"], "campaign_key": "fall"})["links"]
        self.assertEqual([l["existed"] for l in first], [False, False])
        again = utm.create_links({"target_path": "/", "channel_keys": ["instagram"], "campaign_key": "fall"})["links"][0]
        self.assertTrue(again["existed"])
        self.assertEqual(again["code"], first[0]["code"])
        other = utm.create_links({"target_path": "/", "channel_keys": ["instagram"], "campaign_key": "fall", "utm_content": "reel"})["links"][0]
        self.assertFalse(other["existed"])
        self.assertNotEqual(other["code"], first[0]["code"])
        # archived combo can be re-created with a new code; unarchive of the old one then conflicts
        utm.set_archived(first[0]["code"], True)
        fresh = utm.create_links({"target_path": "/", "channel_keys": ["instagram"], "campaign_key": "fall"})["links"][0]
        self.assertNotEqual(fresh["code"], first[0]["code"])
        with self.assertRaises(store.StoreError):
            utm.set_archived(first[0]["code"], False)

    def test_code_collision_is_retried(self):
        self.campaign()
        taken = utm.create_links({"target_path": "/", "channel_keys": ["instagram"], "campaign_key": "fall"})["links"][0]["code"]
        codes = iter([taken, taken, "zzzzzz"])
        with patch.object(utm, "make_code", lambda: next(codes)):
            link = utm.create_links({"target_path": "/", "channel_keys": ["threads"], "campaign_key": "fall"})["links"][0]
        self.assertEqual(link["code"], "zzzzzz")

    def test_create_links_validation(self):
        self.campaign()
        cases = [
            {"target_path": "https://x.com", "channel_keys": ["instagram"], "campaign_key": "fall"},
            {"target_path": "/", "channel_keys": [], "campaign_key": "fall"},
            {"target_path": "/", "channel_keys": ["nope"], "campaign_key": "fall"},
            {"target_path": "/", "channel_keys": ["instagram"], "campaign_key": "missing"},
            {"target_path": "/", "channel_keys": ["instagram"], "campaign_key": "fall", "utm_content": "Bad Value"},
            {"target_path": "/", "channel_keys": ["instagram", "kakao"], "campaign_key": "fall", "utm_source_override": "x"},
        ]
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(store.StoreError):
                utm.create_links(payload)
        link = utm.create_links({"target_path": "/", "channel_keys": ["instagram"], "campaign_key": "fall",
                                 "utm_source_override": "ig_story", "utm_medium_override": "story"})["links"][0]
        self.assertEqual((link["utm_source"], link["utm_medium"]), ("ig_story", "story"))

    def test_read_ua(self):
        self.assertEqual(utm.read_ua(None), (True, "no-ua"))
        self.assertEqual(utm.read_ua("facebookexternalhit/1.1"), (True, "facebook"))
        self.assertEqual(utm.read_ua("curl/8.0"), (True, "generic-bot"))
        self.assertEqual(utm.read_ua(HUMAN_UA), (False, "kakaotalk-inapp"))
        self.assertEqual(utm.read_ua("Mozilla/5.0 Safari/605"), (False, None))

    def test_attribution_stats(self):
        self.campaign()
        ig, kakao = utm.create_links({"target_path": "/", "channel_keys": ["instagram", "kakao"], "campaign_key": "fall"})["links"]
        with patch.object(utm, "now_iso", return_value="2026-09-20T10:00:00Z"):
            for _ in range(4):
                utm.record_click(ig["code"], True, None, None)
            utm.record_click(ig["code"], False, "preview-bot", "facebook")
            utm.record_click(kakao["code"], True, None, "kakaotalk-inapp")
        raw = {"date": "1990-01-01"}
        with patch.object(store, "now_iso", return_value="2026-09-20T11:00:00Z"):
            tagged = {"utm": {"utm_source": "instagram", "utm_medium": "social", "utm_campaign": "fall"}}
            store.record_submission(raw, {**tagged, "short_code": ig["code"]}, result={})
            store.record_submission(raw, {**tagged, "short_code": ig["code"]}, error_code="INVALID_INPUT")
            store.record_submission(raw, tagged, result={})  # UTM direct (no short code)
            store.record_submission(raw, {"utm": {"utm_source": "other", "utm_medium": "x", "utm_campaign": "zzz"}}, result={})
        data = utm.utm_stats("2026-09-20", "2026-09-20")
        link = {row["code"]: row for row in data["links"]}
        self.assertEqual((link[ig["code"]]["clicks"], link[ig["code"]]["bot_clicks"], link[ig["code"]]["submissions"], link[ig["code"]]["success"]), (4, 1, 2, 1))
        self.assertEqual(link[ig["code"]]["conversion"], 0.5)
        self.assertEqual((link[kakao["code"]]["clicks"], link[kakao["code"]]["submissions"], link[kakao["code"]]["conversion"]), (1, 0, 0.0))
        channel = {row["key"]: row for row in data["by_channel"]}
        self.assertEqual((channel["instagram"]["clicks"], channel["instagram"]["submissions"], channel["instagram"]["direct_submissions"]), (4, 2, 1))
        campaign = {row["key"]: row for row in data["by_campaign"]}
        self.assertEqual((campaign["fall"]["clicks"], campaign["fall"]["submissions"], campaign["fall"]["direct_submissions"]), (5, 2, 1))
        self.assertEqual(data["totals"]["clicks"], 5)
        self.assertEqual(data["totals"]["bot_clicks"], 1)
        self.assertEqual(data["totals"]["direct_submissions"], 2)
        self.assertEqual(len(data["direct"]), 2)
        self.assertEqual(data["daily"], [{"day": "2026-09-20", "clicks": 5, "bot_clicks": 1, "submissions": 2, "direct_submissions": 2}])
        self.assertEqual(utm.utm_stats("2026-09-21", None)["totals"]["clicks"], 0)


class UtmHttpTests(unittest.TestCase):
    """Runs over the real loopback server, reusing AdminTests' fixtures (not its test cases)."""
    setUp = AdminTests.setUp
    request = AdminTests.request
    login = AdminTests.login
    admin = AdminTests.admin
    chart = AdminTests.chart

    def setup_links(self, cookie):
        status, _, _ = self.admin("POST", "/api/admin/utm/campaigns", cookie, {"key": "fall", "label_ko": "가을"})
        self.assertEqual(status, 201)
        status, _, data = self.admin("POST", "/api/admin/utm/links", cookie,
                                     {"target_path": "/", "channel_keys": ["instagram"], "campaign_key": "fall", "utm_content": "reel"})
        self.assertEqual(status, 200)
        return data["links"][0]

    def test_utm_routes_require_auth_and_same_origin(self):
        for path in ("/api/admin/utm-stats", "/api/admin/utm/channels", "/api/admin/utm/campaigns", "/api/admin/utm/links"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 401)
        posts = ("/api/admin/utm/channels", "/api/admin/utm/campaigns", "/api/admin/utm/links",
                 "/api/admin/utm/channels/instagram", "/api/admin/utm/links/abcdef/archive")
        for path in posts:
            with self.subTest(path=path):
                self.assertEqual(self.request("POST", path, {"x": 1}, {"Origin": self.origin})[0], 401)
        cookie = self.login()
        for path in posts:
            for headers in ({"Cookie": cookie}, {"Cookie": cookie, "Origin": "https://attacker.example"}):
                with self.subTest(path=path, headers=headers):
                    self.assertEqual(self.request("POST", path, {"x": 1}, headers)[0], 403)

    def test_redirect_counts_humans_only(self):
        cookie = self.login()
        link = self.setup_links(cookie)
        status, headers, _ = self.request("GET", f"/l/{link['code']}", headers={"User-Agent": HUMAN_UA})
        self.assertEqual(status, 302)
        self.assertEqual(headers["cache-control"], "no-store")
        location = urlsplit(headers["location"])
        self.assertEqual(location.path, "/")
        self.assertFalse(location.netloc)
        self.assertEqual(parse_qs(location.query), {"utm_source": ["instagram"], "utm_medium": ["social"], "utm_campaign": ["fall"],
                                                    "utm_content": ["reel"], "sc": [link["code"]]})
        self.assertEqual(self.request("GET", f"/l/{link['code'].upper()}", headers={"User-Agent": HUMAN_UA})[0], 302)
        self.assertEqual(self.request("HEAD", f"/l/{link['code']}", headers={"User-Agent": HUMAN_UA})[0], 302)
        self.request("GET", f"/l/{link['code']}", headers={"User-Agent": "facebookexternalhit/1.1"})
        self.request("GET", f"/l/{link['code']}")  # no UA -> bot
        connection = sqlite3.connect(self.db)
        rows = connection.execute("SELECT counted, exclude_note, ua_family FROM utm_clicks ORDER BY id").fetchall()
        connection.close()
        self.assertEqual(rows, [(1, None, "kakaotalk-inapp"), (1, None, "kakaotalk-inapp"), (0, "head", "kakaotalk-inapp"),
                                (0, "preview-bot", "facebook"), (0, "preview-bot", "no-ua")])

    def test_unknown_malformed_and_archived_codes_go_home(self):
        cookie = self.login()
        link = self.setup_links(cookie)
        status, _, data = self.admin("POST", f"/api/admin/utm/links/{link['code']}/archive", cookie)
        self.assertEqual((status, data), (200, {"updated": 1}))
        for code in ("zzzzzz", "bad!", "abc", link["code"], "..%2F..%2Fadmin"):
            with self.subTest(code=code):
                status, headers, _ = self.request("GET", f"/l/{code}", headers={"User-Agent": HUMAN_UA})
                self.assertEqual(status, 302)
                self.assertEqual(headers["location"], "/?utm_source=short-link&utm_medium=unknown")
        connection = sqlite3.connect(self.db)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM utm_clicks").fetchone()[0], 0)
        connection.close()

    def test_redirect_survives_storage_failure_and_host_check(self):
        cookie = self.login()
        link = self.setup_links(cookie)
        with patch.object(utm, "record_click", side_effect=sqlite3.OperationalError("disk I/O error")):
            status, headers, _ = self.request("GET", f"/l/{link['code']}", headers={"User-Agent": HUMAN_UA})
        self.assertEqual(status, 302)
        self.assertIn(f"sc={link['code']}", headers["location"])
        with patch.object(utm, "resolve_link", side_effect=sqlite3.OperationalError("locked")):
            status, headers, _ = self.request("GET", f"/l/{link['code']}")
        self.assertEqual((status, headers["location"]), (302, utm.UNKNOWN_TARGET))
        self.assertEqual(self.request("GET", f"/l/{link['code']}", headers={"Host": "evil.example"})[0], 403)

    def test_duplicate_combo_over_http_and_validation_errors(self):
        cookie = self.login()
        link = self.setup_links(cookie)
        status, _, data = self.admin("POST", "/api/admin/utm/links", cookie,
                                     {"target_path": "/", "channel_keys": ["instagram"], "campaign_key": "fall", "utm_content": "reel"})
        self.assertEqual((status, data["links"][0]["code"], data["links"][0]["existed"]), (200, link["code"], True))
        status, _, data = self.admin("POST", "/api/admin/utm/links", cookie,
                                     {"target_path": "//evil.com", "channel_keys": ["instagram"], "campaign_key": "fall"})
        self.assertEqual((status, data["error"]["code"]), (422, "INVALID_INPUT"))
        status, _, _ = self.admin("POST", "/api/admin/utm/campaigns", cookie, {"key": "fall", "label_ko": "중복"})
        self.assertEqual(status, 422)
        status, _, data = self.admin("POST", "/api/admin/utm/channels/instagram", cookie, {"is_active": False})
        self.assertEqual((status, data), (200, {"updated": 1}))
        status, _, _ = self.admin("POST", "/api/admin/utm/channels/nothere", cookie, {"is_active": False})
        self.assertEqual(status, 404)
        status, _, data = self.admin("POST", "/api/admin/utm/links", cookie,
                                     {"target_path": "/", "channel_keys": ["instagram"], "campaign_key": "fall"})
        self.assertEqual(status, 422)  # inactive channel
        status, _, data = self.admin("POST", "/api/admin/utm/channels", cookie,
                                     {"key": "band", "label_ko": "밴드", "utm_source": "band", "utm_medium": "social"})
        self.assertEqual(status, 201)
        status, _, data = self.admin("GET", "/api/admin/utm/links?unknown=1", cookie)
        self.assertEqual(status, 422)

    def test_end_to_end_click_then_chart_appears_in_link_metrics(self):
        cookie = self.login()
        link = self.setup_links(cookie)
        status, headers, _ = self.request("GET", f"/l/{link['code']}", headers={"User-Agent": HUMAN_UA})
        query = parse_qs(urlsplit(headers["location"]).query)
        client = {"visitor_id": "visitorAAAAAAAAAAAAAA", "name": "테스트", "store_consent": True,
                  "utm": {k: v[0] for k, v in query.items() if k.startswith("utm_")}, "short_code": query["sc"][0]}
        self.assertEqual(self.chart(CHART, client)[0], 200)
        status, _, data = self.admin("GET", "/api/admin/utm/links", cookie)
        row = next(item for item in data["links"] if item["code"] == link["code"])
        self.assertEqual((row["clicks"], row["submissions"], row["success"], row["conversion"]), (1, 1, 1, 1.0))
        status, _, stats = self.admin("GET", "/api/admin/utm-stats", cookie)
        self.assertEqual(status, 200)
        self.assertEqual((stats["totals"]["clicks"], stats["totals"]["submissions"], stats["totals"]["direct_submissions"]), (1, 1, 0))
        status, _, stats = self.admin("GET", "/api/admin/utm-stats?from=bad", cookie)
        self.assertEqual(status, 422)


del AdminTests  # imported only for fixtures; keep the loader from collecting it twice

if __name__ == "__main__":
    unittest.main()
