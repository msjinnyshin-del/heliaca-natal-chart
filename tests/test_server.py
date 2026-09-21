"""Exercise the actual loopback HTTP boundary, including private-file isolation."""
import http.client
import importlib
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch


class ServerTests(unittest.TestCase):
    def setUp(self):
        # Never write test submissions into the real admin database.
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        env = patch.dict(os.environ, {"NATAL_DB_PATH": os.path.join(directory.name, "test.sqlite3")})
        env.start()
        self.addCleanup(env.stop)
        try:
            module = importlib.import_module("server")
        except ModuleNotFoundError:
            module = None
        self.assertIsNotNone(module, "The local chart HTTP server must exist")
        self.server = module.make_server(0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request(method, path, body, headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_reference_and_environment_files_are_not_served(self):
        for path in ("/ref/sample-chart.png", "/.venv/pyvenv.cfg", "/../AGENTS.md", "/%2e%2e/AGENTS.md"):
            with self.subTest(path=path):
                status, _, body = self.request("GET", path)
                self.assertEqual(status, 404)
                self.assertNotIn(b"Swiss", body)

    def test_rebinding_host_is_rejected(self):
        status, _, _ = self.request("GET", "/", headers={"Host": "attacker.example"})
        self.assertEqual(status, 403)

    def test_cross_origin_chart_request_is_rejected(self):
        status, _, _ = self.request("POST", "/api/chart", "{}", {"Content-Type": "application/json", "Origin": "https://attacker.example"})
        self.assertEqual(status, 403)

    def test_malformed_json_and_nonobjects_rejected(self):
        for raw in ("{", "[]", "null", '{"latitude":NaN}'):
            with self.subTest(raw=raw):
                status, _, body = self.request("POST", "/api/chart", raw, {"Content-Type": "application/json"})
                self.assertEqual(status, 400)
                self.assertIn("error", json.loads(body))

    def test_large_payload_and_wrong_content_type_rejected(self):
        status, _, _ = self.request("POST", "/api/chart", "x" * 16385, {"Content-Type": "application/json"})
        self.assertEqual(status, 413)
        status, _, _ = self.request("POST", "/api/chart", "{}", {"Content-Type": "text/plain"})
        self.assertEqual(status, 415)

    def test_validation_error_is_structured_and_not_cached(self):
        status, headers, raw = self.request("POST", "/api/chart", "{}", {"Content-Type": "application/json"})
        self.assertEqual(status, 422)
        self.assertIn("code", json.loads(raw)["error"])
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_real_chart_uses_engine_not_fixed_response(self):
        payload = {"date": "1985-07-14", "time": "21:45:00", "timezone": "America/New_York", "latitude": 40.7128, "longitude": -74.006, "place": "reference", "house_system": "P", "node_mode": "true", "time_accuracy": "reported"}
        status, _, raw = self.request("POST", "/api/chart", json.dumps(payload), {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        result = json.loads(raw)
        self.assertEqual(result["normalized"]["utc"], "1985-07-15T01:45:00Z")
        self.assertEqual(len(result["houses"]), 12)
        moon = next(body for body in result["bodies"] if body["id"] == "Moon")
        self.assertAlmostEqual(moon["longitude"], 77.94899, places=4)
        payload["date"] = "1985-07-15"
        status, _, raw = self.request("POST", "/api/chart", json.dumps(payload), {"Content-Type": "application/json"})
        moon_next = next(body for body in json.loads(raw)["bodies"] if body["id"] == "Moon")
        self.assertEqual(status, 200)
        self.assertGreater(moon_next["longitude"] - moon["longitude"], 10)


if __name__ == "__main__":
    unittest.main()
