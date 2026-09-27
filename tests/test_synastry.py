"""Synastry rules: inter-aspect orbs, angle-angle exclusion, house overlays, and the HTTP contract."""
import unittest

from natal.errors import ChartError
from natal.engine import calculate_chart
from natal.synastry import SYNASTRY_ASPECTS, calculate_synastry, house_overlays, houses_swept, inter_aspects, orb_range


def chart(longitudes, asc=0.0, mc=270.0, with_angles=False):
    bodies = [{"id": key, "longitude": lon} for key, lon in longitudes.items()]
    angles = [{"id": "ASC", "longitude": asc}, {"id": "MC", "longitude": mc}] if with_angles else []
    houses = [{"number": i + 1, "longitude": (asc + 30 * i) % 360} for i in range(12)]
    return {"bodies": bodies, "angles": angles, "houses": houses}


PERSON = {"date": "1990-05-15", "time": "14:30", "timezone": "Asia/Seoul", "latitude": 37.5665,
          "longitude": 126.978, "place": "Seoul", "house_system": "P", "node_mode": "true"}


class SynastryRuleTests(unittest.TestCase):
    def test_luminary_bonus_boundary(self):
        a, b = chart({"Sun": 10.0}), chart({"Venus": 17.0, "Mars": 17.01})
        found = {(x["b"], x["name"]) for x in inter_aspects(a, b)}
        self.assertIn(("Venus", "Conjunction"), found)  # 7° = 6 + 1 luminary
        self.assertNotIn(("Mars", "Conjunction"), found)

    def test_planet_orb_without_luminary(self):
        a = chart({"Venus": 0.0})
        self.assertTrue(inter_aspects(a, chart({"Mars": 95.0})))       # square orb 5
        self.assertFalse(inter_aspects(a, chart({"Mars": 95.1})))

    def test_point_orb_and_angle_pairs(self):
        a = chart({"Venus": 1.9}, asc=100.0, mc=10.0, with_angles=True)
        b = chart({"Chiron": 0.0}, asc=100.5, mc=200.0, with_angles=True)
        pairs = {(x["a"], x["b"]) for x in inter_aspects(a, b)}
        self.assertIn(("Venus", "Chiron"), pairs)
        self.assertNotIn(("ASC", "ASC"), pairs)  # angle-to-angle excluded

    def test_wraparound_and_strength_sorting(self):
        result = inter_aspects(chart({"Moon": 359.0, "Pluto": 0.5}), chart({"Sun": 1.0}))
        self.assertEqual([x["a"] for x in result], ["Moon", "Pluto"])  # luminary outranks a tighter Pluto
        self.assertAlmostEqual(result[0]["separation"], 2.0)
        self.assertTrue(result[0]["strong"])

    def test_quincunx_orb(self):
        self.assertEqual(inter_aspects(chart({"Venus": 0.0}), chart({"Saturn": 152.0}))[0]["name"], "Quincunx")
        self.assertFalse(inter_aspects(chart({"Venus": 0.0}), chart({"Saturn": 152.1})))

    def test_house_overlay_cusp_is_half_open(self):
        overlays = house_overlays(chart({"Sun": 30.0, "Moon": 29.999}), chart({}, asc=0.0, with_angles=True))
        self.assertEqual({x["body"]: x["house"] for x in overlays}, {"Sun": 2, "Moon": 1})
        self.assertEqual([x["body"] for x in overlays], ["Moon", "Sun"])  # angular 1H before 2H

    def test_real_charts_and_person_tagged_errors(self):
        result = calculate_synastry({"person_a": PERSON, "person_b": {**PERSON, "date": "1992-11-03", "time": "08:05"}})
        self.assertEqual(len(result["overlays"]["a_in_b"]), 13)  # 12 bodies + ASC
        self.assertTrue(all(x["orb"] <= x["allowed_orb"] for x in result["aspects"]))
        with self.assertRaises(ChartError) as ctx:
            calculate_synastry({"person_a": PERSON, "person_b": {**PERSON, "latitude": 91}})
        self.assertEqual(ctx.exception.details["person"], "person_b")
        with self.assertRaises(ChartError):
            calculate_synastry({"person_a": PERSON})


class UnknownTimeSynastryTests(unittest.TestCase):
    """Spec §11: a partner without a birth time contributes no angles or houses; day-varying relations are marked."""

    def test_orb_range_covers_kinks_and_wraparound(self):
        # A body sweeping 10°..24° ahead of a fixed one: conjunction orb runs 10°..24°.
        self.assertEqual(orb_range(10.0, 0.0, 14.0, 0), (10.0, 24.0))
        low, high = orb_range(85.0, 0.0, 10.0, 90)       # square passes exact inside the sweep
        self.assertAlmostEqual(low, 0.0)
        self.assertAlmostEqual(high, 5.0)
        low, high = orb_range(355.0, 0.0, 10.0, 0)       # crosses 0/360: separation dips to 0 then rises
        self.assertAlmostEqual(low, 0.0)
        self.assertAlmostEqual(high, 5.0)
        low, high = orb_range(175.0, 0.0, 10.0, 180)     # opposition kink at 180
        self.assertAlmostEqual(low, 0.0)
        self.assertAlmostEqual(high, 5.0)

    def test_stable_and_time_dependent_classification(self):
        a, b = chart({"Moon": 100.0}), chart({"Venus": 100.0})
        stable = inter_aspects(a, b, track_a=[{"Moon": 99.0}, {"Moon": 104.0}])  # orb 1..4 ≤ 7 all day
        self.assertEqual(stable[0]["stability"], "stable")
        partial = inter_aspects(a, b, track_a=[{"Moon": 95.0}, {"Moon": 108.0}])  # leaves orb after 107°
        self.assertEqual(partial[0]["stability"], "time_dependent")
        self.assertFalse(partial[0]["strong"])  # never promoted to a settled strong finding
        outside = inter_aspects(chart({"Moon": 120.0}), b, track_a=[{"Moon": 115.0}, {"Moon": 128.0}])
        self.assertFalse([x for x in outside if x["name"] == "Conjunction"])

    def test_houses_swept_counts_every_crossed_cusp(self):
        cusps = [30.0 * i for i in range(12)]
        self.assertEqual(houses_swept([25.0, 95.0], cusps), [1, 2, 3, 4])      # one coarse step over three cusps
        self.assertEqual(houses_swept([5.0, 355.0], cusps), [1, 12])           # backward over 0°
        self.assertEqual(houses_swept([10.0, 20.0], cusps), [1])
        self.assertEqual(houses_swept([30.0, 355.0], cusps), [2, 1, 12])     # backward, starting exactly on a cusp
        self.assertEqual(houses_swept([45.0, 30.0], cusps), [2])              # backward, landing on a cusp stays in 2

    def test_overlays_skip_unknown_host_and_list_houses_for_unknown_owner(self):
        host_unknown = {"bodies": [], "angles": [], "houses": []}
        self.assertIsNone(house_overlays(chart({"Sun": 10.0}), host_unknown))
        owner = chart({"Moon": 28.0})
        rows = house_overlays(owner, chart({}, asc=0.0), owner_track=[{"Moon": 25.0}, {"Moon": 38.0}])
        self.assertEqual(rows[0]["houses"], [1, 2])
        self.assertEqual(rows[0]["stability"], "time_dependent")

    def test_real_unknown_partner_matches_independent_times(self):
        unknown = {k: v for k, v in PERSON.items() if k != "time"} | {"date": "1992-11-03", "time_accuracy": "unknown"}
        result = calculate_synastry({"person_a": PERSON, "person_b": unknown})
        self.assertEqual(result["time_accuracy"], {"person_a": "reported", "person_b": "unknown"})
        self.assertIsNone(result["overlays"]["a_in_b"])                      # B has no houses
        self.assertNotIn("ASC", {x["body"] for x in result["overlays"]["b_in_a"]})
        self.assertFalse({x["b"] for x in result["aspects"]} & {"ASC", "MC"})
        moon_rows = [x for x in result["overlays"]["b_in_a"] if x["body"] == "Moon"]
        self.assertTrue(moon_rows and moon_rows[0]["houses"])
        found = {(x["a"], x["b"], x["name"]): x for x in result["aspects"]}
        self.assertTrue(any(x["stability"] == "time_dependent" for x in found.values()))
        a_points = {x["id"]: x["longitude"] for x in (*result["person_a"]["bodies"], *result["person_a"]["angles"])}
        # Independent reported-path charts across B's local day must agree with every classification.
        samples = []
        for clock in ("00:00:30", "05:59", "12:00", "18:01", "23:59:30"):
            chart_b = calculate_chart({**{k: v for k, v in unknown.items() if k != "time_accuracy"}, "time": clock})
            samples.append({x["id"]: x["longitude"] for x in chart_b["bodies"]})
        for (a_id, b_id, name), entry in found.items():
            target = dict((n, t) for n, t, _ in SYNASTRY_ASPECTS)[name]
            orbs = [abs(abs((a_points[a_id] - s[b_id] + 180) % 360 - 180) - target) for s in samples]
            low, high = entry["orb_range"]
            self.assertTrue(all(low - 1e-3 <= orb <= high + 1e-3 for orb in orbs), (a_id, b_id, name, orbs, low, high))
            if entry["stability"] == "stable":
                self.assertTrue(all(orb <= entry["allowed_orb"] + 1e-6 for orb in orbs))
        # Nothing in orb at any sampled time may be missing from the result.
        allowed_by = {n: o for n, _, o in SYNASTRY_ASPECTS}
        for s in samples:
            for a_id in ("Sun", "Moon", "Venus", "Mars"):
                for b_id in ("Sun", "Moon", "Venus", "Mars"):
                    for name, target, _ in SYNASTRY_ASPECTS:
                        allowed = allowed_by[name] + (1 if {a_id, b_id} & {"Sun", "Moon"} else 0)
                        orb = abs(abs((a_points[a_id] - s[b_id] + 180) % 360 - 180) - target)
                        if orb <= allowed - 1e-3:
                            self.assertIn((a_id, b_id, name), found)

    def test_both_unknown_has_no_overlays(self):
        unknown = {k: v for k, v in PERSON.items() if k != "time"} | {"time_accuracy": "unknown"}
        result = calculate_synastry({"person_a": unknown, "person_b": {**unknown, "date": "1992-11-03"}})
        self.assertEqual(result["overlays"], {"a_in_b": None, "b_in_a": None})
        self.assertTrue(all("stability" in x for x in result["aspects"]))


if __name__ == "__main__":
    unittest.main()
