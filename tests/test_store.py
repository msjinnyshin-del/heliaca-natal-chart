"""SQLite submission store: migrations, validation, aggregation and deletion."""
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from natal import store

VISITOR_A = "visitorAAAAAAAAAAAAAA"
VISITOR_B = "visitorBBBBBBBBBBBBBB"
RAW = {"date": "1985-07-14", "time": "21:45:00", "timezone": "America/New_York",
       "latitude": 40.7128, "longitude": -74.006, "place": "New York"}
RESULT = {"calculation_status": "success", "sect": "night", "normalized": {"utc": "1985-07-15T01:45:00Z"},
          "bodies": [{"id": "Sun", "sign_index": 3, "position": "게 22°31′39″"},
                     {"id": "Moon", "sign_index": 2, "position": "쌍둥이 17°56′56″"}],
          "angles": [{"id": "ASC", "sign_index": 10, "position": "물병 19°19′51″"}],
          "metadata": {"input_fingerprint": "abc123"}}


class StoreTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = os.path.join(directory.name, "admin.sqlite3")
        env = patch.dict(os.environ, {"NATAL_DB_PATH": self.path})
        env.start()
        self.addCleanup(env.stop)

    def record(self, client=None, result=RESULT, error_code=None, created_at=None, raw=RAW):
        with patch.object(store, "now_iso", return_value=created_at or "2026-09-20T10:00:00Z"):
            return store.record_submission(dict(raw), client or {}, result=result if error_code is None else None, error_code=error_code)

    def test_migration_sets_user_version_and_wal(self):
        self.record()
        connection = sqlite3.connect(self.path)
        self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], store.SCHEMA_VERSION)
        self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        connection.close()

    def test_success_row_keeps_full_raw_input_and_summary(self):
        row_id = self.record({"visitor_id": VISITOR_A, "name": " 가상인물 ", "consent": True,
                              "utm": {"utm_source": "instagram", "utm_campaign": "가을_런칭"}, "short_code": "abc234"})
        item = store.get_submission(row_id)
        self.assertEqual(item["raw_input"], RAW)
        self.assertEqual(item["display_name"], "가상인물")
        self.assertEqual((item["status"], item["error_code"], item["consent"]), ("success", None, 1))
        self.assertEqual((item["sun_sign"], item["moon_sign"], item["asc_sign"]), ("게", "쌍둥이", "물병"))
        self.assertEqual(item["summary"]["fingerprint"], "abc123")
        self.assertEqual((item["utm_source"], item["utm_campaign"], item["short_code"]), ("instagram", "가을_런칭", "abc234"))

    def test_failure_row_records_error_code(self):
        item = store.get_submission(self.record(error_code="INVALID_INPUT"))
        self.assertEqual((item["status"], item["error_code"], item["summary"]), ("INVALID_INPUT", "INVALID_INPUT", None))

    def test_invalid_client_values_are_dropped_not_fatal(self):
        cases = [
            {"visitor_id": "short"}, {"visitor_id": "x" * 65}, {"visitor_id": "bad id with spaces!!"},
            {"visitor_id": 12345678901234567890}, {"utm": {"utm_source": "<script>"}},
            {"utm": {"utm_source": "a" * 101}}, {"short_code": "../etc"}, {"utm": "not-a-dict"}, "not-a-dict",
        ]
        for client in cases:
            with self.subTest(client=client):
                info = store.clean_client(client)
                self.assertIsNone(info["visitor_id"])
                self.assertIsNone(info["utm_source"])
                self.assertIsNone(info["short_code"])
        self.assertEqual(store.clean_client({"visitor_id": VISITOR_A})["visitor_id"], VISITOR_A)

    def test_name_is_stripped_of_control_chars_and_capped(self):
        self.assertEqual(store.clean_name("a\x00b‮c\n"), "abc")
        self.assertEqual(len(store.clean_name("가" * 500)), store.NAME_MAX)
        self.assertIsNone(store.clean_name("   "))
        self.assertIsNone(store.clean_name(42))

    def test_stats_totals_daily_and_distributions(self):
        self.record({"visitor_id": VISITOR_A, "name": "A", "utm": {"utm_source": "ig"}}, created_at="2026-09-19T01:00:00Z")
        self.record({"visitor_id": VISITOR_A, "name": "A2"}, created_at="2026-09-20T01:00:00Z")
        self.record({"visitor_id": VISITOR_B, "name": "B"}, error_code="INVALID_INPUT", created_at="2026-09-20T02:00:00Z")
        self.record({}, created_at="2026-09-21T02:00:00Z")
        data = store.stats()
        self.assertEqual(data["totals"], {"submissions": 4, "success": 3, "failed": 1, "unique_visitors": 2, "unique_names": 3})
        self.assertEqual([(d["day"], d["total"], d["success"], d["failed"]) for d in data["daily"]],
                         [("2026-09-19", 1, 1, 0), ("2026-09-20", 2, 1, 1), ("2026-09-21", 1, 1, 0)])
        self.assertEqual({r["key"]: r["count"] for r in data["by_status"]}, {"success": 3, "INVALID_INPUT": 1})
        self.assertEqual(data["signs"]["sun"], [{"key": "게", "count": 3}])
        self.assertEqual(data["top_places"], [{"key": "New York", "count": 4}])
        self.assertIn({"key": "ig", "count": 1}, data["utm"]["source"])
        ranged = store.stats("2026-09-20", "2026-09-20")
        self.assertEqual(ranged["totals"]["submissions"], 2)

    def test_invalid_range_rejected(self):
        for value in ("2026-13-01", "yesterday", "2026-9-1"):
            with self.subTest(value=value), self.assertRaises(store.StoreError):
                store.stats(value, None)

    def test_users_grouped_by_visitor(self):
        self.record({"visitor_id": VISITOR_A, "name": "첫이름"}, created_at="2026-09-19T01:00:00Z")
        self.record({"visitor_id": VISITOR_A, "name": "새이름"}, created_at="2026-09-20T01:00:00Z")
        self.record({"visitor_id": VISITOR_B}, created_at="2026-09-20T03:00:00Z")
        self.record({}, created_at="2026-09-20T04:00:00Z")
        data = store.users()
        self.assertEqual(data["anonymous_submissions"], 1)
        by_id = {u["visitor_id"]: u for u in data["users"]}
        self.assertEqual(by_id[VISITOR_A]["count"], 2)
        self.assertEqual(by_id[VISITOR_A]["latest_name"], "새이름")
        self.assertEqual(by_id[VISITOR_A]["names"], ["새이름", "첫이름"])
        self.assertEqual((by_id[VISITOR_A]["first_seen"], by_id[VISITOR_A]["last_seen"]), ("2026-09-19T01:00:00Z", "2026-09-20T01:00:00Z"))
        self.assertIsNone(by_id[VISITOR_B]["latest_name"])
        self.assertEqual([u["visitor_id"] for u in store.users(q="첫")["users"]], [VISITOR_A])
        # LIKE wildcards are escaped.
        self.assertEqual(store.users(q="%")["users"], [])

    def test_list_filters_and_pagination(self):
        for index in range(5):
            self.record({"visitor_id": VISITOR_A, "name": f"n{index}"}, created_at=f"2026-09-2{index}T00:00:00Z")
        self.record({"visitor_id": VISITOR_B}, error_code="UNSUPPORTED_DATE")
        self.assertEqual(store.list_submissions()["total"], 6)
        self.assertEqual(store.list_submissions(visitor_id=VISITOR_B)["total"], 1)
        self.assertEqual(store.list_submissions(status="failed")["submissions"][0]["status"], "UNSUPPORTED_DATE")
        self.assertEqual(store.list_submissions(status="success")["total"], 5)
        page = store.list_submissions(visitor_id=VISITOR_A, limit=2, offset=2)
        self.assertEqual([r["display_name"] for r in page["submissions"]], ["n2", "n1"])
        self.assertNotIn("raw_input", page["submissions"][0])
        with self.assertRaises(store.StoreError):
            store.list_submissions(visitor_id="bad")
        with self.assertRaises(store.StoreError):
            store.list_submissions(status="x'; DROP TABLE submissions; --")

    def test_delete_submission_and_visitor(self):
        first = self.record({"visitor_id": VISITOR_A})
        self.record({"visitor_id": VISITOR_A})
        self.record({"visitor_id": VISITOR_B})
        self.assertEqual(store.delete_submission(first), 1)
        self.assertIsNone(store.get_submission(first))
        self.assertEqual(store.delete_submission(first), 0)
        self.assertEqual(store.delete_visitor(VISITOR_A), 1)
        self.assertEqual(store.list_submissions()["total"], 1)
        with self.assertRaises(store.StoreError):
            store.delete_visitor("%")

    def test_raw_input_round_trips_as_json(self):
        raw = {**RAW, "aspect_profile": {"version": "major-v2"}, "location_source": {"mode": "manual"}}
        item = store.get_submission(self.record(raw=raw))
        self.assertEqual(item["raw_input"], json.loads(json.dumps(raw)))


if __name__ == "__main__":
    unittest.main()
