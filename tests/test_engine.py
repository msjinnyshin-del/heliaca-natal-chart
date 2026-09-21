import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


REFERENCE = {
    "date": "1985-07-14", "time": "21:45:00", "timezone": "America/New_York",
    "latitude": 40.7128, "longitude": -74.006,
    "house_system": "P", "node_mode": "true", "time_accuracy": "reported",
}


class EngineAcceptance(unittest.TestCase):
    def test_reference_contract_and_regression_snapshot(self):
        try:
            module = importlib.import_module("natal.engine")
        except ModuleNotFoundError:
            module = None
        calculate = getattr(module, "calculate_chart", None)
        self.assertTrue(callable(calculate), "실제 calculate_chart adapter가 필요합니다")
        chart = calculate(REFERENCE)
        self.assertEqual(chart["normalized"]["utc"], "1985-07-15T01:45:00Z")
        self.assertEqual(chart["normalized"]["offset"], "-04:00")
        self.assertEqual(len(chart["bodies"]), 16)
        # Regression snapshot of THIS engine for a fictional person (not an independent
        # reference): (sign, degree, minute, second) captured from calculate_chart itself.
        observed = {
            "Sun": (3, 22, 31, 39), "Moon": (2, 17, 56, 56),
            "Mercury": (4, 19, 2, 21), "Venus": (2, 9, 28, 58),
            "Mars": (3, 23, 27, 11), "Jupiter": (10, 14, 33, 14),
            "Saturn": (7, 21, 33, 40), "Uranus": (8, 14, 34, 5),
            "Neptune": (9, 1, 40, 55), "Pluto": (7, 1, 55, 35),
            "NorthNode": (1, 16, 6, 22), "Lilith": (1, 4, 47, 50),
            "ASC": (10, 19, 19, 51), "MC": (8, 6, 56, 24),
            "Fortune": (11, 23, 54, 34),
        }
        actual = {b["id"]: b for b in chart["bodies"] + chart["angles"]}
        for name, (sign, degree, minute, second) in observed.items():
            expected = sign * 30 + degree + minute / 60 + second / 3600
            difference = abs((actual[name]["longitude"] - expected + 180) % 360 - 180) * 3600
            self.assertLessEqual(difference, 1, name)
        motions = {body["id"]: body["direction"] for body in chart["bodies"]}
        self.assertEqual(motions["Pluto"], "S")
        self.assertEqual(motions["Jupiter"], "R")
        self.assertEqual(motions["Chiron"], "D")
        self.assertEqual(motions["NorthNode"], "R")

    def test_nodes_and_mean_lilith(self):
        from natal.engine import calculate_chart
        true = calculate_chart(REFERENCE)
        mean = calculate_chart({**REFERENCE, "node_mode": "mean"})
        a = {b["id"]: b for b in true["bodies"]}
        b = {b["id"]: b for b in mean["bodies"]}
        self.assertGreater(abs(a["NorthNode"]["longitude"] - b["NorthNode"]["longitude"]), 1)
        self.assertEqual(a["Sun"], b["Sun"])
        self.assertAlmostEqual((a["SouthNode"]["longitude"] - a["NorthNode"]["longitude"]) % 360, 180)
        self.assertAlmostEqual(a["SouthNode"]["declination"], -a["NorthNode"]["declination"])
        self.assertAlmostEqual(a["Lilith"]["longitude"], 34.7973350, places=5)

    def test_true_node_can_move_direct(self):
        from natal.engine import calculate_chart
        chart = calculate_chart({**REFERENCE, "date": "2020-01-03"})
        node = next(b for b in chart["bodies"] if b["id"] == "NorthNode")
        self.assertGreater(node["speed"], 0)
        self.assertFalse(node["retrograde"])
        self.assertEqual(node["direction"], "D")

    def test_five_house_systems_and_independent_mc(self):
        from natal.engine import calculate_chart
        charts = {s: calculate_chart({**REFERENCE, "house_system": s}) for s in "PWEKO"}
        for system, chart in charts.items():
            self.assertEqual(len(chart["houses"]), 12, system)
            for body in chart["bodies"]:
                self.assertIn(body["house"], range(1, 13))
            angles = {a["id"]: a["longitude"] for a in chart["angles"]}
            self.assertAlmostEqual((angles["DSC"] - angles["ASC"]) % 360, 180)
            self.assertAlmostEqual((angles["IC"] - angles["MC"]) % 360, 180)
        self.assertEqual(charts["W"]["houses"][0]["longitude"], 300)  # ASC in Aquarius -> whole-sign 1st = 300
        self.assertEqual(charts["E"]["houses"][0]["longitude"], charts["E"]["angles"][0]["longitude"])
        for system in "WE":
            self.assertNotEqual(charts[system]["houses"][9]["longitude"], charts[system]["angles"][1]["longitude"])

    def test_day_night_lots_and_horizon_boundary(self):
        from natal.engine import calculate_chart
        from natal.rules import lots
        night = calculate_chart(REFERENCE)
        day = calculate_chart({**REFERENCE, "time": "12:00:00"})
        for chart, expected_sect in ((day, "day"), (night, "night")):
            self.assertEqual(chart["sect"], expected_sect)
            bodies = {b["id"]: b for b in chart["bodies"]}
            asc = chart["angles"][0]["longitude"]
            delta = bodies["Moon"]["longitude"] - bodies["Sun"]["longitude"]
            if expected_sect == "night":
                delta = -delta
            self.assertAlmostEqual(bodies["Fortune"]["longitude"], (asc + delta) % 360)
            self.assertAlmostEqual(bodies["Spirit"]["longitude"], (asc - delta) % 360)
            self.assertIsNone(bodies["Fortune"]["declination"])
        self.assertEqual(lots(30, 20, 40, 0), ("day", 50, 10))
        self.assertEqual(lots(30, 20, 40, -1e-12), ("night", 10, 50))

    def test_other_input_changes_real_results_and_is_deterministic(self):
        from natal.engine import calculate_chart
        a = calculate_chart(REFERENCE)
        b = calculate_chart({**REFERENCE, "date": "2000-02-29", "timezone": "Asia/Kathmandu", "latitude": 27.7, "longitude": 85.3})
        self.assertEqual(b["normalized"]["offset"], "+05:45")
        self.assertNotEqual(a["bodies"][0]["longitude"], b["bodies"][0]["longitude"])
        self.assertEqual(a, calculate_chart(REFERENCE))
        json.dumps(a, allow_nan=False)
        for body in a["bodies"]:
            self.assertEqual(body["antiscia"], (180 - body["longitude"]) % 360)
        self.assertEqual(a["metadata"]["requested_flags"], 258)
        self.assertEqual({f["name"] for f in a["metadata"]["data"]}, {"sepl_18.se1", "semo_18.se1", "seas_18.se1"})

    def test_default_aspect_profile_has_no_axis_or_optional_point_duplicates(self):
        from natal.engine import calculate_chart
        chart = calculate_chart(REFERENCE)
        settings = chart["settings"]
        self.assertEqual(settings["aspect_rule"], "major-v2")
        self.assertEqual(settings["aspect_profile"]["targets"], {
            "chiron": True, "lilith": True, "nodes": False, "lots": False,
            "angles": ["ASC", "MC"],
        })
        point_ids = {item["b"] for item in chart["aspects"] if item["b"] not in {"Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"}}
        self.assertFalse(point_ids & {"DSC", "IC", "NorthNode", "SouthNode", "Fortune", "Spirit"})
        angle_aspects = [item for item in chart["aspects"] if item["b"] in {"ASC", "MC"}]
        self.assertEqual([(a["a"], a["b"], a["name"]) for a in angle_aspects], [
            ("Moon", "ASC", "Trine"), ("Mercury", "ASC", "Opposition"),
            ("Venus", "MC", "Opposition"), ("Saturn", "ASC", "Square"),
        ])
        self.assertTrue(all(item["profile_version"] == "major-v2" for item in chart["aspects"]))

    def test_optional_aspect_targets_are_explicit_and_north_node_only(self):
        from natal.engine import calculate_chart
        profile = {"version": "major-v2", "targets": {"chiron": True, "lilith": True, "nodes": True, "lots": True, "angles": ["ASC", "MC"]},
                   "orbs": {"chiron": 3, "lilith": 3, "nodes": 3, "lots": 3, "angles": 3}}
        chart = calculate_chart({**REFERENCE, "aspect_profile": profile})
        target_ids = {aspect["b"] for aspect in chart["aspects"]} | {aspect["a"] for aspect in chart["aspects"]}
        # Reference North Node: only Mercury/Jupiter squares fall inside the 3 deg point orb.
        node_pairs = {(a["a"], a["b"], a["name"]) for a in chart["aspects"] if a["b"] == "NorthNode"}
        self.assertEqual(node_pairs, {("Mercury", "NorthNode", "Square"), ("Jupiter", "NorthNode", "Square")})
        self.assertTrue(all(a["orb"] <= 3 for a in chart["aspects"] if a["b"] == "NorthNode"))
        self.assertNotIn("SouthNode", target_ids)
        self.assertTrue(target_ids & {"Fortune", "Spirit"})
        self.assertEqual(chart["input"]["aspect_profile"], profile)
        # Positive case: 1980-03-15 has Mars conjunct North Node within 3 deg; South Node never becomes a target.
        other = calculate_chart({**REFERENCE, "date": "1980-03-15", "aspect_profile": profile})
        node_aspects = [(a["a"], a["b"], a["name"]) for a in other["aspects"] if "Node" in a["a"] or "Node" in a["b"]]
        self.assertIn(("Mars", "NorthNode", "Conjunction"), node_aspects)
        self.assertFalse(any("SouthNode" in pair[:2] for pair in node_aspects))
        self.assertTrue(all(a["orb"] <= 3 for a in other["aspects"] if a["b"] == "NorthNode"))

    def test_location_source_is_validated_and_recorded(self):
        from natal.engine import calculate_chart
        source = {"mode": "geocoded", "provider": "Open-Meteo / GeoNames", "place_id": 5128581,
                  "label": "New York, New York, USA", "reference_latitude": 40.7143,
                  "reference_longitude": -74.006, "reference_timezone": "America/New_York"}
        chart = calculate_chart({**REFERENCE, "location_source": source})
        self.assertEqual(chart["input"]["location_source"], source)
        self.assertEqual(chart["metadata"]["geocoding"]["mode"], "geocoded")
        self.assertIn("도시 중심", chart["metadata"]["geocoding"]["note"])

    def test_serializes_whole_swiss_transaction(self):
        import natal.engine as engine
        inputs = [REFERENCE, {**REFERENCE, "date": "2001-04-01", "house_system": "W", "node_mode": "mean", "latitude": -33.86, "longitude": 151.2, "timezone": "Australia/Sydney"}]
        expected = [engine.calculate_chart(p) for p in inputs]
        original = engine.swe.calc
        active, peak = 0, 0
        counter_lock = threading.Lock()
        def tracked(*args):
            nonlocal active, peak
            with counter_lock:
                active += 1
                peak = max(peak, active)
            try:
                time.sleep(0.001)
                return original(*args)
            finally:
                with counter_lock:
                    active -= 1
        with patch.object(engine.swe, "calc", tracked), ThreadPoolExecutor(max_workers=4) as pool:
            result = list(pool.map(engine.calculate_chart, inputs * 3))
        self.assertEqual(result, expected * 3)
        self.assertEqual(peak, 1)


class TimeAndFailureTests(unittest.TestCase):
    def assert_code(self, payload, code):
        from natal.engine import calculate_chart
        from natal.errors import ChartError
        with self.assertRaises(ChartError) as result:
            calculate_chart(payload)
        self.assertEqual(result.exception.code, code)
        return result.exception

    def test_dst_gap_fold_and_exact_candidates(self):
        from natal.engine import calculate_chart
        self.assert_code({**REFERENCE, "date": "2024-03-10", "time": "02:30"}, "NONEXISTENT_LOCAL_TIME")
        payload = {**REFERENCE, "date": "2024-11-03", "time": "01:30"}
        error = self.assert_code(payload, "AMBIGUOUS_LOCAL_TIME")
        self.assertEqual([c["utc"] for c in error.details["candidates"]], ["2024-11-03T05:30:00Z", "2024-11-03T06:30:00Z"])
        self.assertEqual(calculate_chart({**payload, "fold": 0})["normalized"]["offset"], "-04:00")
        self.assertEqual(calculate_chart({**payload, "fold": 1})["normalized"]["offset"], "-05:00")
        self.assert_code({**payload, "fold": True}, "INVALID_INPUT")
        self.assert_code({**REFERENCE, "timezone": "Europe/London", "date": "2024-03-31", "time": "01:30"}, "NONEXISTENT_LOCAL_TIME")
        self.assert_code({**REFERENCE, "timezone": "Europe/London", "date": "2024-10-27", "time": "01:30"}, "AMBIGUOUS_LOCAL_TIME")

    def test_offsets_korean_dst_and_dateline(self):
        from natal.time_input import resolve_time
        cases = [("Asia/Seoul", "1988-07-01", "12:00", "+10:00", "1988-07-01T02:00:00+00:00"),
                 ("Asia/Kolkata", "2000-01-01", "00:10", "+05:30", "1999-12-31T18:40:00+00:00"),
                 ("Asia/Kathmandu", "2000-01-01", "00:10", "+05:45", "1999-12-31T18:25:00+00:00")]
        for zone, day, clock, offset, expected in cases:
            result = resolve_time({**REFERENCE, "timezone": zone, "date": day, "time": clock})
            self.assertEqual(result[0].isoformat(), expected)
            self.assertEqual(result[1], offset)
        self.assert_code({**REFERENCE, "timezone": "Pacific/Apia", "date": "2011-12-30", "time": "12:00"}, "NONEXISTENT_LOCAL_TIME")

    def test_bad_inputs(self):
        invalid = [{"date": "2000-02-30"}, {"date": "2000-1-01"}, {"time": "23:59:60"}, {"time": "24:00"},
                   {"time": "12:00Z"}, {"time_accuracy": "unknown"}, {"time_accuracy": "approximate"},
                   {"latitude": float("nan")}, {"latitude": float("inf")}, {"longitude": -181}, {"latitude": 91},
                   {"latitude": True}, {"latitude": 10 ** 400}, {"latitude": "29"}, {"timezone": "../UTC"}, {"timezone": "/etc/passwd"},
                   {"timezone": "Madeup/Zone"}, {"node_mode": "wrong"}, {"house_system": "wrong"}, {"calendar": "lunar"}]
        for change in invalid:
            with self.subTest(change=change):
                self.assert_code({**REFERENCE, **change}, "INVALID_INPUT")
        self.assert_code([], "INVALID_INPUT")
        invalid_profiles = [
            {"orbs": {"chiron": 3.01}},
            {"targets": {"angles": ["ASC", "DSC"]}},
            {"targets": {"angles": [["ASC"]]}},
            {"targets": {"nodes": "yes"}},
            {"version": "major-v1"},
        ]
        for profile in invalid_profiles:
            self.assert_code({**REFERENCE, "aspect_profile": profile}, "INVALID_INPUT")
        invalid_locations = [
            {"mode": "geocoded", "provider": "user", "place_id": None, "label": "x", "reference_latitude": 1, "reference_longitude": 2, "reference_timezone": "UTC"},
            {"mode": "manual", "provider": "user", "place_id": None, "label": "x", "reference_latitude": 91, "reference_longitude": 2, "reference_timezone": "UTC"},
        ]
        for source in invalid_locations:
            self.assert_code({**REFERENCE, "location_source": source}, "INVALID_INPUT")
        self.assert_code({**REFERENCE, "date": "1899-12-31"}, "UNSUPPORTED_DATE")
        self.assert_code({**REFERENCE, "date": "1900-01-01"}, "TIMEZONE_NEEDS_REVIEW")
        self.assert_code({**REFERENCE, "date": "1969-12-31"}, "TIMEZONE_NEEDS_REVIEW")
        future = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
        self.assert_code({**REFERENCE, "date": future}, "UNSUPPORTED_DATE")

    def test_future_instant_uses_resolved_utc_and_local_today(self):
        from natal.time_input import resolve_time
        frozen = datetime(2026, 9, 20, 23, 30, tzinfo=timezone.utc)
        with patch("natal.time_input.now_utc", return_value=frozen, create=True):
            result = resolve_time({**REFERENCE, "date": "2026-09-21", "time": "08:00", "timezone": "Asia/Seoul"})
            self.assertEqual(result[0], datetime(2026, 9, 20, 23, 0, tzinfo=timezone.utc))
            self.assert_code({**REFERENCE, "date": "2026-09-20", "time": "23:45", "timezone": "UTC"}, "UNSUPPORTED_DATE")

    def test_polar_houses_fail_no_silent_porphyry(self):
        for system in "PK":
            self.assert_code({**REFERENCE, "latitude": 80, "house_system": system}, "HOUSE_SYSTEM_UNAVAILABLE")

    def test_missing_corrupt_and_unpinned_data_fail(self):
        import natal.engine as engine
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            with patch.object(engine, "DATA_DIR", temp):
                self.assert_code(REFERENCE, "EPHEMERIS_DATA_MISSING")
                for path in (engine.ROOT / "data" / "ephe").glob("*.se1"):
                    (temp / path.name).write_bytes(path.read_bytes())
                (temp / "seas_18.se1").write_bytes(b"corrupt")
                self.assert_code(REFERENCE, "EPHEMERIS_DATA_MISSING")
                (temp / "seas_18.se1").write_bytes((engine.ROOT / "data" / "ephe" / "seas_18.se1").read_bytes())
                (temp / "seleapsec.txt").write_text("unversioned override")
                self.assert_code(REFERENCE, "EPHEMERIS_DATA_MISSING")

    def test_os_dotfiles_in_ephemeris_dir_are_ignored(self):
        import natal.engine as engine
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            for path in (engine.ROOT / "data" / "ephe").glob("*.se1"):
                (temp / path.name).write_bytes(path.read_bytes())
            (temp / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1")
            with patch.object(engine, "DATA_DIR", temp):
                self.assertEqual(engine.validate_data()["engine"], engine.validate_data()["engine"])
                (temp / "seleapsec.txt").write_text("unversioned override")
                self.assert_code(REFERENCE, "EPHEMERIS_DATA_MISSING")

    def test_moshier_and_nonfinite_output_rejected(self):
        import natal.engine as engine
        from natal.errors import ChartError
        for values, flags in (((1, 0, 1, 1, 0, 0), 260), ((float("nan"), 0, 1, 1, 0, 0), 258), ((1, 0, 1, 1, 0, 0), 2)):
            with patch.object(engine.swe, "calc", return_value=(values, flags)), self.assertRaises(ChartError) as result:
                engine.checked_calc(2451545, 0)
            self.assertEqual(result.exception.code, "UNEXPECTED_EPHEMERIS_FALLBACK")

    def test_pinned_timezone_source_ignores_host_tzpath(self):
        from natal.time_input import resolve_time
        with patch("zoneinfo.TZPATH", ("/nonexistent",)):
            self.assertEqual(resolve_time(REFERENCE)[1], "-04:00")

    def test_declared_tzdata_version_mismatch_fails(self):
        with patch("natal.time_input.tzdata.__version__", "wrong"):
            self.assert_code(REFERENCE, "TIMEZONE_NEEDS_REVIEW")


class RuleBoundaries(unittest.TestCase):
    def test_rounding_carry_and_raw_sign(self):
        from natal.rules import position
        result = position(29 + 59 / 60 + 59.8 / 3600)
        self.assertEqual(result["position"], "황소 00°00′00″")
        self.assertEqual(result["display_sign_index"], 1)
        self.assertEqual(result["sign_index"], 0)
        result = position(359 + 59 / 60 + 59.8 / 3600)
        self.assertEqual(result["position"], "양 00°00′00″")
        self.assertEqual(result["sign_index"], 11)
        self.assertEqual(position(30)["sign_index"], 1)

    def test_house_wrap_and_exact_cusp(self):
        from natal.rules import house_for
        cusps = [(350 + 30 * i) % 360 for i in range(12)]
        self.assertEqual(house_for(350, cusps), 1)
        self.assertEqual(house_for(0, cusps), 1)
        self.assertEqual(house_for(20, cusps), 2)
        self.assertEqual(house_for(349.99999, cusps), 12)

    def test_aspect_luminary_bonus_once_and_extra_cap(self):
        from natal.rules import aspects, PLANETS
        # Ten planet records are required by the production contract; arrange
        # the remaining records far from the target pair and select by pair.
        def pair(a, b, longitude):
            records = [{"id": a, "longitude": 0}, {"id": b, "longitude": longitude}]
            records += [{"id": p, "longitude": 240 + i} for i, p in enumerate(PLANETS) if p not in (a, b)]
            return [r for r in aspects(records, []) if r["a"] == a and r["b"] == b]
        self.assertEqual(pair("Sun", "Moon", 10)[0]["allowed_orb"], 10)
        self.assertEqual(pair("Sun", "Moon", 10.000001), [])
        self.assertEqual(pair("Mercury", "Jupiter", 8)[0]["allowed_orb"], 8)
        self.assertEqual(pair("Mercury", "Jupiter", 8.000001), [])
        records = [{"id": p, "longitude": 20 + i * 20} for i, p in enumerate(PLANETS)]
        records[0]["longitude"] = 0
        records += [{"id": "NorthNode", "longitude": 3}, {"id": "Fortune", "longitude": 3}]
        profile = {"version": "major-v2", "targets": {"chiron": False, "lilith": False, "nodes": True, "lots": False, "angles": []},
                   "orbs": {"chiron": 3, "lilith": 3, "nodes": 3, "lots": 3, "angles": 3}}
        found = aspects(records, [], profile)
        self.assertEqual(next(r for r in found if r["a"] == "Sun" and r["b"] == "NorthNode")["allowed_orb"], 3)
        self.assertFalse(any(r["a"] == "NorthNode" for r in found))
        records[10]["longitude"] = 3.000001
        self.assertFalse(any(r["a"] == "Sun" and r["b"] == "NorthNode" for r in aspects(records, [], profile)))


if __name__ == "__main__":
    unittest.main()
