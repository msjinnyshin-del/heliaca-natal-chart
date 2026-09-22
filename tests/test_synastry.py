"""Synastry rules: inter-aspect orbs, angle-angle exclusion, house overlays, and the HTTP contract."""
import unittest

from natal.errors import ChartError
from natal.synastry import calculate_synastry, house_overlays, inter_aspects


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


if __name__ == "__main__":
    unittest.main()
