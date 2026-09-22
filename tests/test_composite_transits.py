"""Composite midpoints and transit aspects, including wraparound and motion boundaries."""
import unittest

from natal.composite import calculate_composite, composite_cusps, midpoint
from natal.errors import ChartError
from natal.transits import calculate_transits, transit_aspects

A = {"date": "1972-08-27", "time": "22:20", "timezone": "America/New_York", "latitude": 29.6516,
     "longitude": -82.3248, "place": "G", "house_system": "P", "node_mode": "true"}
B = {"date": "1967-12-24", "time": "15:00", "timezone": "Asia/Seoul", "latitude": 37.5665,
     "longitude": 126.978, "place": "S", "house_system": "P", "node_mode": "true"}


class CompositeTests(unittest.TestCase):
    def test_midpoint_uses_shorter_arc(self):
        self.assertAlmostEqual(midpoint(350, 20), 5)
        self.assertAlmostEqual(midpoint(20, 350), 5)
        self.assertAlmostEqual(midpoint(100, 200), 150)

    def test_cusps_stay_ordered_when_a_midpoint_flips(self):
        a = [(i * 30) % 360 for i in range(12)]
        b = [(i * 30 + 170) % 360 for i in range(12)]
        cusps = composite_cusps(a, b)
        widths = [(cusps[(i + 1) % 12] - cusps[i]) % 360 for i in range(12)]
        self.assertAlmostEqual(sum(widths), 360)

    def test_real_composite_matches_hand_midpoints(self):
        result = calculate_composite({"person_a": A, "person_b": B})
        composite = {b["id"]: b for b in result["composite"]["bodies"]}
        sun_a = next(b for b in result["person_a"]["bodies"] if b["id"] == "Sun")["longitude"]
        sun_b = next(b for b in result["person_b"]["bodies"] if b["id"] == "Sun")["longitude"]
        self.assertAlmostEqual(composite["Sun"]["longitude"], midpoint(sun_a, sun_b))
        self.assertAlmostEqual((composite["SouthNode"]["longitude"] - composite["NorthNode"]["longitude"]) % 360, 180)
        asc = next(a for a in result["composite"]["angles"] if a["id"] == "ASC")["longitude"]
        self.assertAlmostEqual(asc, 42.11, places=1)
        for system in "WEKO":
            with self.subTest(system=system):
                calculate_composite({"person_a": {**A, "house_system": system}, "person_b": {**B, "house_system": system}})

    def test_person_tagged_error(self):
        with self.assertRaises(ChartError) as ctx:
            calculate_composite({"person_a": A, "person_b": {**B, "latitude": 95}})
        self.assertEqual(ctx.exception.details["person"], "person_b")


def point(pid, lon, speed=None):
    return {"id": pid, "longitude": lon, "speed": speed, "direction": "R" if speed and speed < 0 else "D"}


class TransitTests(unittest.TestCase):
    def test_orb_boundary_and_motion(self):
        natal = {"bodies": [point("Sun", 100.0)], "angles": []}
        applying = transit_aspects(natal, {"bodies": [point("Mars", 97.0, 0.5)]})
        self.assertEqual((applying[0]["name"], applying[0]["motion"]), ("Conjunction", "applying"))
        separating = transit_aspects(natal, {"bodies": [point("Mars", 97.0, -0.5)]})
        self.assertEqual(separating[0]["motion"], "separating")
        self.assertFalse(transit_aspects(natal, {"bodies": [point("Mars", 96.9, 0.5)]}))

    def test_motion_on_inner_side_of_aspect_and_wraparound(self):
        natal = {"bodies": [point("Moon", 359.0)], "angles": []}
        # Transit at 1° is 2° past the natal Moon going forward: separating.
        self.assertEqual(transit_aspects(natal, {"bodies": [point("Venus", 1.0, 1.0)]})[0]["motion"], "separating")
        # Square: separation 89° (< 90) and widening toward exact = applying.
        natal = {"bodies": [point("Sun", 0.0)], "angles": []}
        self.assertEqual(transit_aspects(natal, {"bodies": [point("Saturn", 89.0, 0.1)]})[0]["motion"], "applying")

    def test_real_transits_and_moment_validation(self):
        result = calculate_transits({"natal": A, "moment": {"date": "2026-09-22", "time": "12:00", "timezone": "Asia/Seoul"}})
        self.assertTrue(result["aspects"])
        self.assertEqual(len(result["transit_houses"]), 12)
        with self.assertRaises(ChartError):
            calculate_transits({"natal": A, "moment": {"date": "2026-09-22", "time": "12:00", "timezone": "Asia/Seoul", "latitude": 1}})
        future = calculate_transits({"natal": A, "moment": {"date": "2040-01-01", "time": "00:00", "timezone": "UTC"}})
        self.assertEqual(future["transit"]["normalized"]["utc"], "2040-01-01T00:00:00Z")
        with self.assertRaises(ChartError):
            calculate_transits({"natal": A, "moment": {"date": "2101-01-01", "time": "00:00", "timezone": "UTC"}})
        with self.assertRaises(ChartError):  # future birth is still rejected, even via /api/chart-style input
            calculate_transits({"natal": {**A, "date": "2040-01-01"}, "moment": {"date": "2026-09-22", "time": "12:00", "timezone": "UTC"}})


if __name__ == "__main__":
    unittest.main()
