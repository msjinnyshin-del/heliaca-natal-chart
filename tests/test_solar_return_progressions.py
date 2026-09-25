"""Solar return and secondary progressions (spec §11).

Expectations come from direct Swiss calls or closed-form formulas in this file, never from the module under test.
"""
from datetime import datetime, timedelta, timezone
import math
import unittest
from unittest.mock import patch

import swisseph as swe

from natal import progressions
from natal.engine import calculate_chart, checked_calc, engine_session
from natal.moment import chart_at_utc, utc_from_jd_tt
from natal.errors import ChartError
from natal.progressions import YEAR_DAYS, calculate_progressions
from natal.solar_return import calculate_solar_return

NATAL = {"date": "1985-07-14", "time": "21:45:00", "timezone": "America/New_York", "latitude": 40.7128,
         "longitude": -74.006, "place": "New York", "house_system": "P", "node_mode": "true"}
SEOUL = {"latitude": 37.5665, "longitude": 126.978, "timezone": "Asia/Seoul", "place": "서울"}
d, r = math.radians, math.degrees


def arcsec(a, b):
    return abs((a - b + 180) % 360 - 180) * 3600


def apparent_sun(utc):
    # Own session and flag check: never rely on global Swiss state left behind by another call.
    with engine_session():
        jd_tt, _ = swe.utc_to_jd(utc.year, utc.month, utc.day, utc.hour, utc.minute,
                                 utc.second + utc.microsecond / 1e6, swe.GREG_CAL)
        return checked_calc(jd_tt, swe.SUN)[0][0]


def parse_utc(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def body(chart, body_id):
    return next(item for item in chart["bodies"] + chart["angles"] if item["id"] == body_id)


class SolarReturn(unittest.TestCase):
    def test_return_instant_puts_the_sun_back_on_its_natal_longitude(self):
        result = calculate_solar_return({"natal": NATAL, "year": 2026, "location": SEOUL})
        natal_sun = body(result["natal"], "Sun")["longitude"]
        exact = parse_utc(result["exact"]["utc"])
        self.assertLess(arcsec(apparent_sun(exact), natal_sun), 0.01)
        # A genuine crossing: one minute earlier the Sun is behind, one minute later ahead.
        before = (apparent_sun(exact - timedelta(minutes=1)) - natal_sun + 180) % 360 - 180
        after = (apparent_sun(exact + timedelta(minutes=1)) - natal_sun + 180) % 360 - 180
        self.assertLess(before, 0)
        self.assertGreater(after, 0)
        self.assertLessEqual(abs((exact - datetime(2026, 7, 15, 1, 45, tzinfo=timezone.utc)).total_seconds()), 2 * 86400)

    def test_return_chart_is_cast_for_the_chosen_location(self):
        result = calculate_solar_return({"natal": NATAL, "year": 2026, "location": SEOUL})
        chart = result["return"]
        self.assertEqual((chart["normalized"]["timezone"], chart["normalized"]["latitude"]), ("Asia/Seoul", 37.5665))
        direct = calculate_chart({**SEOUL, "date": chart["input"]["date"], "time": chart["input"]["time"],
                                  "house_system": "P", "node_mode": "true", "fold": chart["input"].get("fold")},
                                 allow_future=True)
        self.assertEqual([h["longitude"] for h in chart["houses"]], [h["longitude"] for h in direct["houses"]])
        self.assertLess(arcsec(body(chart, "Sun")["longitude"], body(result["natal"], "Sun")["longitude"]), 0.05)
        natal_houses = {item["body"]: item["house"] for item in result["return_in_natal_houses"]}
        self.assertIn("Sun", natal_houses)
        self.assertEqual(natal_houses["Sun"], body(result["natal"], "Sun")["house"])

    def test_leap_day_and_year_end_births(self):
        leap = {**NATAL, **SEOUL, "date": "2000-02-29", "time": "12:00:00"}
        exact = parse_utc(calculate_solar_return({"natal": leap, "year": 2001, "location": SEOUL})["exact"]["utc"])
        self.assertIn((exact.month, exact.day), {(2, 27), (2, 28), (3, 1)})
        year_end = {**NATAL, **SEOUL, "date": "1990-12-31", "time": "23:30:00"}
        exact = parse_utc(calculate_solar_return({"natal": year_end, "year": 2020, "location": SEOUL})["exact"]["utc"])
        self.assertLessEqual(abs((exact - datetime(2020, 12, 31, 14, 30, tzinfo=timezone.utc)).total_seconds()), 2 * 86400)

    def test_local_time_and_offset_describe_the_same_instant(self):
        result = calculate_solar_return({"natal": NATAL, "year": 2026, "location": SEOUL})
        chart = result["return"]
        self.assertEqual(result["exact"]["local"], f"{chart['input']['date']}T{chart['input']['time']}")
        self.assertEqual(result["exact"]["offset"], chart["normalized"]["offset"])

    def test_year_2100_boundary(self):
        # Born 2000-12-31 23:50 in Seoul: the 2100 birthday return falls on 2101-01-01 local time.
        late = {**NATAL, **SEOUL, "date": "2000-12-31", "time": "23:50:00"}
        with self.assertRaises(ChartError) as caught:
            calculate_solar_return({"natal": late, "year": 2100, "location": SEOUL})
        self.assertEqual(caught.exception.code, "UNSUPPORTED_DATE")
        self.assertIn("2100", str(caught.exception))

    def test_invalid_requests(self):
        cases = [
            ({"natal": NATAL, "year": 2026}, "INVALID_INPUT"),  # location must be chosen explicitly
            ({"natal": NATAL, "year": 2026, "location": {**SEOUL, "place": ["x"]}}, "INVALID_INPUT"),
            ({"natal": NATAL, "year": 2026, "location": {**SEOUL, "place": "x" * 301}}, "INVALID_INPUT"),
            ({"natal": NATAL, "year": 1985, "location": SEOUL}, "INVALID_INPUT"),
            ({"natal": NATAL, "year": 2101, "location": SEOUL}, "UNSUPPORTED_DATE"),
            ({"natal": NATAL, "year": "2026", "location": SEOUL}, "INVALID_INPUT"),
            ({"natal": NATAL, "year": True, "location": SEOUL}, "INVALID_INPUT"),
            ({"natal": NATAL, "year": 2026, "location": {**SEOUL, "latitude": 95}}, "INVALID_INPUT"),
            ({"natal": NATAL, "year": 2026, "location": {**SEOUL, "extra": 1}}, "INVALID_INPUT"),
            ({"natal": {**NATAL, "time": None, "time_accuracy": "unknown"}, "year": 2026, "location": SEOUL}, "INVALID_INPUT"),
            ({"natal": NATAL, "year": 2026, "location": SEOUL, "more": 1}, "INVALID_INPUT"),
        ]
        for payload, code in cases:
            with self.subTest(payload=payload), self.assertRaises(ChartError) as caught:
                calculate_solar_return(payload)
            self.assertEqual(caught.exception.code, code)


class InstantHelpers(unittest.TestCase):
    def test_leap_second_instant_does_not_crash(self):
        with engine_session():
            jd_tt = swe.utc_to_jd(2016, 12, 31, 23, 59, 60.2, swe.GREG_CAL)[0]
        moment = utc_from_jd_tt(jd_tt)
        self.assertLessEqual(abs((moment - datetime(2017, 1, 1, tzinfo=timezone.utc)).total_seconds()), 1)

    def test_repeated_local_hour_keeps_the_right_fold(self):
        place = {"latitude": 40.7128, "longitude": -74.006, "timezone": "America/New_York", "place": "New York"}
        settings = calculate_chart(NATAL)["settings"]
        first = chart_at_utc(datetime(2025, 11, 2, 5, 30, tzinfo=timezone.utc), place, settings, allow_future=True)
        second = chart_at_utc(datetime(2025, 11, 2, 6, 30, tzinfo=timezone.utc), place, settings, allow_future=True)
        self.assertEqual((first["input"]["time"], second["input"]["time"]), ("01:30:00", "01:30:00"))
        self.assertEqual((first["normalized"]["utc"], second["normalized"]["utc"]), ("2025-11-02T05:30:00Z", "2025-11-02T06:30:00Z"))

    def test_skipped_local_hour_never_yields_a_nonexistent_time(self):
        place = {"latitude": 40.7128, "longitude": -74.006, "timezone": "America/New_York"}
        settings = calculate_chart(NATAL)["settings"]
        chart = chart_at_utc(datetime(2025, 3, 9, 6, 59, 59, 600000, tzinfo=timezone.utc), place, settings, allow_future=True)
        self.assertEqual((chart["input"]["time"], chart["normalized"]["offset"]), ("03:00:00", "-04:00"))


class SecondaryProgressions(unittest.TestCase):
    MOMENT = {"date": "2015-07-14", "time": "21:45", "timezone": "America/New_York"}

    def test_day_for_a_year_key(self):
        result = calculate_progressions({"natal": NATAL, "moment": self.MOMENT})
        natal_utc = parse_utc(result["natal"]["normalized"]["utc"])
        target_utc = datetime(2015, 7, 15, 1, 45, tzinfo=timezone.utc)
        elapsed_days = (target_utc - natal_utc).total_seconds() / 86400
        expected = natal_utc + timedelta(days=elapsed_days / YEAR_DAYS)
        self.assertEqual(YEAR_DAYS, 365.24219)
        self.assertAlmostEqual(result["age_years"], elapsed_days / YEAR_DAYS, places=9)
        self.assertLessEqual(abs((parse_utc(result["progressed"]["normalized"]["utc"]) - expected).total_seconds()), 0.5)

    def test_progressed_bodies_are_the_ephemeris_at_the_progressed_instant(self):
        result = calculate_progressions({"natal": NATAL, "moment": self.MOMENT})
        progressed = result["progressed"]
        jd_tt = progressed["normalized"]["jd_tt"]
        for body_id, number in (("Sun", swe.SUN), ("Moon", swe.MOON), ("Mars", swe.MARS)):
            expected = swe.calc(jd_tt, number, swe.FLG_SWIEPH | swe.FLG_SPEED)[0][0]
            self.assertLess(arcsec(body(progressed, body_id)["longitude"], expected), 1, body_id)
        ids = {b["id"] for b in progressed["bodies"]}
        self.assertFalse(ids & {"Fortune", "Spirit"})
        self.assertIsNone(progressed["sect"])

    def test_angles_move_by_solar_arc_and_asc_follows_the_closed_form(self):
        result = calculate_progressions({"natal": NATAL, "moment": self.MOMENT})
        natal, progressed = result["natal"], result["progressed"]
        arc = (body(progressed, "Sun")["longitude"] - body(natal, "Sun")["longitude"]) % 360
        mc = (body(natal, "MC")["longitude"] + arc) % 360
        self.assertLess(arcsec(body(progressed, "MC")["longitude"], mc), 1e-3)
        eps = swe.calc(progressed["normalized"]["jd_tt"], swe.ECL_NUT, 0)[0][0]
        armc = r(math.atan2(math.sin(d(mc)) * math.cos(d(eps)), math.cos(d(mc)))) % 360
        phi = natal["normalized"]["latitude"]
        asc = r(math.atan2(math.cos(d(armc)), -(math.sin(d(armc)) * math.cos(d(eps)) + math.tan(d(phi)) * math.sin(d(eps))))) % 360
        self.assertLess(arcsec(body(progressed, "ASC")["longitude"], asc), 1)
        cusps = {h["number"]: h["longitude"] for h in progressed["houses"]}
        self.assertLess(arcsec(cusps[10], mc), 1e-3)
        self.assertLess(arcsec(cusps[1], asc), 1)
        self.assertEqual(result["settings"]["angles"], "solar-arc-longitude")
        natal_cusps = [h["longitude"] for h in sorted(natal["houses"], key=lambda h: h["number"])]
        placed = {item["body"]: item["house"] for item in result["progressed_in_natal_houses"]}
        self.assertTrue({"Sun", "Moon", "Jupiter", "Saturn", "ASC", "MC"} <= set(placed))
        from natal.rules import house_for
        self.assertEqual(placed["ASC"], house_for(body(progressed, "ASC")["longitude"], natal_cusps))

    def test_progressed_to_natal_aspects_are_within_one_degree(self):
        result = calculate_progressions({"natal": NATAL, "moment": self.MOMENT})
        self.assertTrue(result["aspects"])
        for aspect in result["aspects"]:
            p = body(result["progressed"], aspect["progressed"])["longitude"]
            n = body(result["natal"], aspect["natal"])["longitude"]
            self.assertAlmostEqual(abs(arcsec(p, n) / 3600 - aspect["angle"]), aspect["orb"], places=9)
            self.assertLessEqual(aspect["orb"], 1.0)
            # The bi-wheel draws `a` on the inner (natal) chart and `b` on the outer (progressed) one.
            self.assertEqual((aspect["a"], aspect["b"]), (aspect["natal"], aspect["progressed"]))

    def test_invalid_requests(self):
        cases = [
            ({"natal": NATAL, "moment": {**self.MOMENT, "date": "1980-01-01"}}, "INVALID_INPUT"),
            ({"natal": NATAL, "moment": {**self.MOMENT, "date": "2101-01-01"}}, "UNSUPPORTED_DATE"),
            ({"natal": {**NATAL, "time": None, "time_accuracy": "unknown"}, "moment": self.MOMENT}, "INVALID_INPUT"),
            ({"natal": NATAL, "moment": {**self.MOMENT, "latitude": 1}}, "INVALID_INPUT"),
            ({"natal": NATAL}, "INVALID_INPUT"),
        ]
        for payload, code in cases:
            with self.subTest(payload=payload), self.assertRaises(ChartError) as caught:
                calculate_progressions(payload)
            self.assertEqual(caught.exception.code, code)

    def test_recent_birth_with_a_far_target_is_not_refused_as_a_future_birth(self):
        recent = {**NATAL, **SEOUL, "date": "2026-09-01", "time": "12:00:00"}
        with patch("natal.time_input.now_utc", return_value=datetime(2026, 9, 25, tzinfo=timezone.utc)):
            result = calculate_progressions({"natal": recent, "moment": {"date": "2100-01-01", "time": "00:00", "timezone": "Asia/Seoul"}})
        self.assertGreater(parse_utc(result["progressed"]["normalized"]["utc"]), datetime(2026, 9, 25, tzinfo=timezone.utc))
        self.assertTrue(all(b["altitude"] is None for b in result["progressed"]["bodies"]))

    def test_progressed_house_failures_are_refused(self):
        with patch.object(progressions.swe, "houses_armc", side_effect=swe.Error("polar")):
            with self.assertRaises(ChartError) as caught:
                calculate_progressions({"natal": NATAL, "moment": self.MOMENT})
        self.assertEqual(caught.exception.code, "HOUSE_SYSTEM_UNAVAILABLE")
        reversed_cusps = tuple((300 - 30 * i) % 360 for i in range(12))
        with patch.object(progressions.swe, "houses_armc", return_value=(reversed_cusps, (0.0,) * 10)):
            with self.assertRaises(ChartError) as caught:
                calculate_progressions({"natal": NATAL, "moment": self.MOMENT})
        self.assertEqual(caught.exception.code, "HOUSE_SYSTEM_UNAVAILABLE")

    def test_polar_birth_with_placidus_is_refused_not_substituted(self):
        with self.assertRaises(ChartError) as caught:
            calculate_progressions({"natal": {**NATAL, "latitude": 80}, "moment": self.MOMENT})
        self.assertEqual(caught.exception.code, "HOUSE_SYSTEM_UNAVAILABLE")
        # Whole Sign has no polar failure, so the same birth progresses normally.
        result = calculate_progressions({"natal": {**NATAL, "latitude": 80, "house_system": "W"}, "moment": self.MOMENT})
        self.assertEqual(len(result["progressed"]["houses"]), 12)


if __name__ == "__main__":
    unittest.main()
