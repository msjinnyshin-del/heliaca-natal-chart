"""Unknown birth time (spec §2.3): noon representative, whole-local-day scan, time-dependent items excluded.

Scan events are cross-checked against the independent reported-time path (calculate_chart at a fixed
local time), never against the scan's own output.
"""
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from natal import time_input
from natal.engine import calculate_chart
from natal.errors import ChartError
from natal.unknown_time import find_crossings, find_windows

SEOUL = {"timezone": "Asia/Seoul", "latitude": 37.5665, "longitude": 126.978, "place": "서울",
         "house_system": "P", "node_mode": "true"}
MOON_INGRESS_DAY = "1990-05-01"  # Moon Cancer -> Leo in Seoul local time (found via the reported path)
MERCURY_STATION_DAY = "1990-05-17"  # Mercury retrograde -> direct


def unknown(date, **extra):
    return calculate_chart({**SEOUL, "date": date, "time_accuracy": "unknown", **extra})


def reported(date, local_time):
    chart = calculate_chart({**SEOUL, "date": date, "time": local_time})
    return {body["id"]: body for body in chart["bodies"]}


def shifted(local_iso, seconds):
    moment = datetime.fromisoformat(local_iso) + timedelta(seconds=seconds)
    return moment.date().isoformat(), moment.strftime("%H:%M:%S")


def separation(a, b):
    return abs((a["longitude"] - b["longitude"] + 180) % 360 - 180)


class ScanHelpers(unittest.TestCase):
    def test_crossings_are_bisected_between_samples(self):
        roots = find_crossings(lambda f: f - 0.3217, 144)
        self.assertEqual(len(roots), 1)
        self.assertAlmostEqual(roots[0], 0.3217, delta=1 / 144 / 2 ** 12)
        self.assertEqual(find_crossings(lambda f: 1.0, 144), [])

    def test_narrow_dip_between_samples_is_not_missed(self):
        # Samples at k/144 all miss the window around 0.5003; endpoint-only or sample-only checks would say "never".
        windows = find_windows(lambda f: abs(f - 0.5003) * 1000 - 0.05, 144)
        self.assertEqual(len(windows), 1)
        start, end = windows[0]
        self.assertAlmostEqual(start, 0.50025, delta=1e-5)
        self.assertAlmostEqual(end, 0.50035, delta=1e-5)

    def test_narrow_gap_inside_a_window_splits_it(self):
        windows = find_windows(lambda f: 0.05 - abs(f - 0.2503) * 1000, 144)
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0][0], 0.0)
        self.assertAlmostEqual(windows[0][1], 0.25025, delta=1e-5)
        self.assertAlmostEqual(windows[1][0], 0.25035, delta=1e-5)
        self.assertEqual(windows[1][1], 1.0)

    def test_short_touch_at_the_day_edges_does_not_flip_the_rest_of_the_day(self):
        # Two edge brackets used to find the same dip with slightly different boundaries.
        self.assertEqual(len(find_windows(lambda x: abs(x - 0.005) * 50 - 0.01, 144)), 1)
        self.assertEqual(len(find_windows(lambda x: abs(x - 0.995) * 50 - 0.01, 144)), 1)
        (start, end), = find_windows(lambda x: abs(x - 0.005) * 50 - 0.01, 144)
        self.assertAlmostEqual(start, 0.0048, delta=1e-5)
        self.assertAlmostEqual(end, 0.0052, delta=1e-5)

    def test_whole_range_and_empty(self):
        self.assertEqual(find_windows(lambda f: -1.0, 144), [(0.0, 1.0)])
        self.assertEqual(find_windows(lambda f: 1.0, 144), [])


class UnknownTimeChart(unittest.TestCase):
    def test_contract_excludes_time_dependent_items(self):
        chart = unknown(MOON_INGRESS_DAY, aspect_profile={"targets": {"angles": ["ASC", "MC"], "lots": True}})
        normalized = chart["normalized"]
        self.assertEqual((chart["calculation_status"], normalized["time_accuracy"]), ("success", "unknown"))
        self.assertEqual(normalized["representative_local_time"], "12:00:00")
        self.assertEqual(normalized["utc"], "1990-05-01T03:00:00Z")
        self.assertEqual(normalized["day_range"], {"start_utc": "1990-04-30T15:00:00Z", "end_utc": "1990-05-01T15:00:00Z", "hours": 24.0})
        self.assertEqual((chart["angles"], chart["houses"], chart["sect"]), ([], [], None))
        ids = [body["id"] for body in chart["bodies"]]
        self.assertNotIn("Fortune", ids)
        self.assertNotIn("Spirit", ids)
        self.assertTrue(all(body["house"] is None and body["altitude"] is None for body in chart["bodies"]))
        self.assertFalse(any(a["target_group"] in ("angles", "lots") for a in chart["aspects"]))
        self.assertEqual(set(chart["metadata"]["excluded_by_mode"]),
                         {"ASC", "MC", "DSC", "IC", "houses", "Fortune", "Spirit", "sect"})
        # Noon positions equal the reported chart at local noon.
        noon = reported(MOON_INGRESS_DAY, "12:00")
        for body in chart["bodies"]:
            self.assertAlmostEqual(body["longitude"], noon[body["id"]]["longitude"], places=9)

    def test_moon_ingress_is_found_and_matches_reported_positions(self):
        moon = next(b for b in unknown(MOON_INGRESS_DAY)["bodies"] if b["id"] == "Moon")
        sensitivity = moon["time_sensitivity"]
        self.assertFalse(sensitivity["sign_stable"])
        self.assertEqual(sensitivity["signs"], [3, 4])
        (ingress,) = sensitivity["ingresses"]
        self.assertEqual((ingress["from_sign_index"], ingress["to_sign_index"]), (3, 4))
        before, after = reported(*shifted(ingress["local"], -5)), reported(*shifted(ingress["local"], 5))
        self.assertEqual((before["Moon"]["sign_index"], after["Moon"]["sign_index"]), (3, 4))
        sun = next(b for b in unknown(MOON_INGRESS_DAY)["bodies"] if b["id"] == "Sun")
        self.assertTrue(sun["time_sensitivity"]["sign_stable"])
        self.assertEqual(sun["time_sensitivity"]["ingresses"], [])

    def test_station_is_found_and_matches_reported_speed(self):
        mercury = next(b for b in unknown(MERCURY_STATION_DAY)["bodies"] if b["id"] == "Mercury")
        sensitivity = mercury["time_sensitivity"]
        self.assertFalse(sensitivity["direction_stable"])
        (station,) = sensitivity["stations"]
        self.assertEqual(station["to"], "D")
        before, after = reported(*shifted(station["local"], -600)), reported(*shifted(station["local"], 600))
        self.assertLess(before["Mercury"]["speed"], 0)
        self.assertGreater(after["Mercury"]["speed"], 0)

    def test_aspect_stability_matches_reported_orbs(self):
        chart = unknown(MOON_INGRESS_DAY)
        stable = [a for a in chart["aspects"] if a["stability"] == "stable"]
        partial = [a for a in chart["aspects"] if a["stability"] == "partial"]
        self.assertTrue(stable and partial)
        for aspect in stable:
            self.assertEqual([(w["start_local"], w["end_local"]) for w in aspect["windows"]],
                             [("1990-05-01T00:00:00", "1990-05-02T00:00:00")])
            for local_time in [f"{hour:02d}:00" for hour in range(24)] + ["23:59"]:
                bodies = reported(MOON_INGRESS_DAY, local_time)
                orb = abs(separation(bodies[aspect["a"]], bodies[aspect["b"]]) - aspect["angle"])
                self.assertLessEqual(orb, aspect["allowed_orb"], (aspect["id"], aspect["name"], local_time))
        checked = 0
        for aspect in partial:
            for window in aspect["windows"]:
                for edge, inside_sign in ((window["start_local"], 1), (window["end_local"], -1)):
                    if edge.endswith("T00:00:00"):
                        continue  # day boundary, not an orb edge
                    outside = reported(*shifted(edge, -5 * inside_sign))
                    inside = reported(*shifted(edge, 5 * inside_sign))
                    orb_out = abs(separation(outside[aspect["a"]], outside[aspect["b"]]) - aspect["angle"])
                    orb_in = abs(separation(inside[aspect["a"]], inside[aspect["b"]]) - aspect["angle"])
                    self.assertGreater(orb_out, aspect["allowed_orb"], (aspect["id"], edge))
                    self.assertLessEqual(orb_in, aspect["allowed_orb"], (aspect["id"], edge))
                    checked += 1
        self.assertGreater(checked, 0)

    def test_short_and_long_dst_days_use_real_local_day_length(self):
        base = {"timezone": "America/New_York", "latitude": 40.7128, "longitude": -74.006, "house_system": "P",
                "node_mode": "true", "time_accuracy": "unknown"}
        spring = calculate_chart({**base, "date": "2024-03-10"})["normalized"]["day_range"]
        fall = calculate_chart({**base, "date": "2024-11-03"})["normalized"]["day_range"]
        self.assertEqual(spring, {"start_utc": "2024-03-10T05:00:00Z", "end_utc": "2024-03-11T04:00:00Z", "hours": 23.0})
        self.assertEqual(fall, {"start_utc": "2024-11-03T04:00:00Z", "end_utc": "2024-11-04T05:00:00Z", "hours": 25.0})

    def test_daily_longitude_range_is_reported(self):
        moon = next(b for b in unknown(MOON_INGRESS_DAY)["bodies"] if b["id"] == "Moon")
        day_range = moon["time_sensitivity"]["range"]
        first, last = reported(MOON_INGRESS_DAY, "00:00"), reported("1990-05-02", "00:00")
        self.assertAlmostEqual(day_range["start"]["longitude"], first["Moon"]["longitude"], places=6)
        self.assertAlmostEqual(day_range["end"]["longitude"], last["Moon"]["longitude"], places=6)
        self.assertGreater(day_range["degrees"], 10)

    def test_nonexistent_local_date_is_rejected(self):
        with self.assertRaises(ChartError) as caught:
            calculate_chart({"date": "2011-12-30", "timezone": "Pacific/Apia", "latitude": -13.83, "longitude": -171.76,
                             "house_system": "P", "node_mode": "true", "time_accuracy": "unknown"})
        self.assertEqual(caught.exception.code, "NONEXISTENT_LOCAL_TIME")

    def test_gap_straddling_midnight_starts_at_the_transition(self):
        # Toronto 1919-03-31 skipped 23:30 -> 00:30, so the local date begins at 00:30 EDT (04:30Z).
        chart = calculate_chart({"date": "1919-03-31", "timezone": "America/Toronto", "latitude": 43.65, "longitude": -79.38,
                                 "house_system": "P", "node_mode": "true", "time_accuracy": "unknown"})
        self.assertEqual(chart["normalized"]["day_range"]["start_utc"], "1919-03-31T04:30:00Z")
        previous = calculate_chart({"date": "1919-03-30", "timezone": "America/Toronto", "latitude": 43.65, "longitude": -79.38,
                                    "house_system": "P", "node_mode": "true", "time_accuracy": "unknown"})
        self.assertEqual(previous["normalized"]["day_range"]["end_utc"], "1919-03-31T04:30:00Z")

    def test_repeated_hour_stamps_carry_their_offset(self):
        chart = calculate_chart({"date": "2024-11-03", "timezone": "America/New_York", "latitude": 40.7128, "longitude": -74.006,
                                 "house_system": "P", "node_mode": "true", "time_accuracy": "unknown"})
        window = next(a for a in chart["aspects"] if a["stability"] == "stable")["windows"][0]
        self.assertEqual((window["start_offset"], window["end_offset"]), ("-04:00", "-05:00"))

    def test_deterministic(self):
        self.assertEqual(unknown(MOON_INGRESS_DAY), unknown(MOON_INGRESS_DAY))

    def test_invalid_combinations(self):
        cases = [
            ({"time": "12:00"}, "INVALID_INPUT"),  # a time contradicts "unknown"
            ({"time_accuracy": "approximate", "time": "12:00"}, "INVALID_INPUT"),
            ({"time_accuracy": "sometimes"}, "INVALID_INPUT"),
            ({"fold": 1}, "INVALID_INPUT"),
        ]
        for extra, code in cases:
            with self.subTest(extra=extra), self.assertRaises(ChartError) as caught:
                calculate_chart({**SEOUL, "date": MOON_INGRESS_DAY, "time_accuracy": "unknown", **extra})
            self.assertEqual(caught.exception.code, code)

    def test_day_not_fully_past_is_rejected(self):
        now = datetime(2026, 9, 25, 3, 0, tzinfo=timezone.utc)  # 12:00 in Seoul
        with patch.object(time_input, "now_utc", return_value=now):
            with self.assertRaises(ChartError) as caught:
                unknown("2026-09-25")
            self.assertEqual(caught.exception.code, "UNSUPPORTED_DATE")
            self.assertEqual(unknown("2026-09-24")["normalized"]["time_accuracy"], "unknown")

    def test_lunar_date_with_unknown_time(self):
        chart = unknown("1990-04-07", calendar="lunar")
        self.assertEqual(chart["normalized"]["solar_date"], MOON_INGRESS_DAY)

    def test_multi_chart_tools_reject_unknown_time(self):
        from natal.composite import calculate_composite
        from natal.synastry import calculate_synastry
        from natal.transits import calculate_transits
        known = {**SEOUL, "date": "1985-07-14", "time": "21:45"}
        blind = {**SEOUL, "date": MOON_INGRESS_DAY, "time_accuracy": "unknown"}
        moment = {"date": "2026-01-01", "time": "12:00", "timezone": "Asia/Seoul"}
        calls = [lambda: calculate_synastry({"person_a": known, "person_b": blind}),
                 lambda: calculate_composite({"person_a": blind, "person_b": known}),
                 lambda: calculate_transits({"natal": blind, "moment": moment})]
        for call in calls:
            with self.assertRaises(ChartError) as caught:
                call()
            self.assertEqual(caught.exception.code, "INVALID_INPUT")


if __name__ == "__main__":
    unittest.main()
