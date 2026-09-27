"""Unknown birth time in composite, transits, progressions and solar return (spec §2.3, §11).

Each result is checked against independent reported-time calculations at several local times of the
unknown day: every position must fall inside its stated range, every `stable` aspect must hold at every
sampled time, and nothing in orb at a sampled time may be missing.
"""
import unittest

from natal.composite import calculate_composite
from natal.progressions import calculate_progressions
from natal.solar_return import calculate_solar_return
from natal.transits import calculate_transits

SEOUL = {"timezone": "Asia/Seoul", "latitude": 37.5665, "longitude": 126.978, "place": "Seoul", "house_system": "P", "node_mode": "true"}
KNOWN = {**SEOUL, "date": "1990-05-15", "time": "14:30"}
BLIND = {**SEOUL, "date": "1970-09-06", "time_accuracy": "unknown"}
TIMES = ("00:00:30", "05:59", "12:00", "18:01", "23:59:30")
EPS = 1e-3


def at(clock):
    return {**{k: v for k, v in BLIND.items() if k != "time_accuracy"}, "time": clock}


def inside(longitude, time_range):
    offset = (longitude - time_range["start"]["longitude"]) % 360
    return offset <= time_range["degrees"] + EPS or offset >= 360 - EPS


def check_aspects(case, result_aspects, samples, key):
    """samples: aspect lists from reported runs. key(aspect) identifies a pair+aspect."""
    found = {key(a): a for a in result_aspects}
    for aspects_at_time in samples:
        present = {key(a) for a in aspects_at_time}
        for k in present:
            case.assertIn(k, found, "in orb at a sampled time but missing")
        for k, entry in found.items():
            if entry["stability"] == "stable":
                case.assertIn(k, present, f"{k} marked stable but absent at a sampled time")


class UnknownMultiChart(unittest.TestCase):
    def test_transits(self):
        moment = {"date": "2026-09-28", "time": "12:00", "timezone": "Asia/Seoul"}
        result = calculate_transits({"natal": BLIND, "moment": moment})
        self.assertIsNone(result["transit_houses"])
        self.assertFalse({a["natal"] for a in result["aspects"]} & {"ASC", "MC"})
        key = lambda a: (a["transit"], a["natal"], a["name"])
        runs = [calculate_transits({"natal": at(t), "moment": moment})["aspects"] for t in TIMES]
        check_aspects(self, result["aspects"], [[a for a in run if a["natal"] not in ("ASC", "MC")] for run in runs], key)
        self.assertTrue(any(a["stability"] == "time_dependent" for a in result["aspects"]))

    def test_composite(self):
        result = calculate_composite({"person_a": KNOWN, "person_b": BLIND})
        composite = result["composite"]
        self.assertEqual((composite["angles"], composite["houses"]), ([], []))
        runs = [calculate_composite({"person_a": KNOWN, "person_b": at(t)})["composite"] for t in TIMES]
        ranges = {b["id"]: b for b in composite["bodies"]}
        for run in runs:
            for body in run["bodies"]:
                if not ranges[body["id"]]["midpoint_ambiguous"]:
                    self.assertTrue(inside(body["longitude"], ranges[body["id"]]["time_range"]), body["id"])
        usable = {b for b, item in ranges.items() if not item["midpoint_ambiguous"]}
        key = lambda a: (a["a"], a["b"], a["name"])
        check_aspects(self, composite["aspects"], [[a for a in run["aspects"] if a["a"] in usable and a["b"] in usable] for run in runs], key)

    def test_progressions(self):
        moment = {"date": "2026-09-28", "time": "12:00", "timezone": "Asia/Seoul"}
        result = calculate_progressions({"natal": BLIND, "moment": moment})
        progressed = result["progressed"]
        self.assertEqual((progressed["angles"], progressed["houses"], result["progressed_in_natal_houses"]), ([], [], None))
        runs = [calculate_progressions({"natal": at(t), "moment": moment}) for t in TIMES]
        ranges = {b["id"]: b["time_range"] for b in progressed["bodies"]}
        for run in runs:
            for body in run["progressed"]["bodies"]:
                self.assertTrue(inside(body["longitude"], ranges[body["id"]]), body["id"])
        key = lambda a: (a["progressed"], a["natal"], a["name"])
        check_aspects(self, result["aspects"], [[a for a in run["aspects"] if a["progressed"] not in ("ASC", "MC") and a["natal"] not in ("ASC", "MC")] for run in runs], key)
        moon = ranges["Moon"]
        self.assertGreater(moon["degrees"], 10)  # a whole birth day of progressed Moon motion

    def test_solar_return(self):
        location = {"latitude": 37.5665, "longitude": 126.978, "timezone": "Asia/Seoul", "place": "Seoul"}
        result = calculate_solar_return({"natal": BLIND, "year": 2026, "location": location})
        chart = result["return"]
        self.assertEqual((chart["angles"], chart["houses"], result["return_in_natal_houses"]), ([], [], None))
        window = result["return_window"]
        runs = [calculate_solar_return({"natal": at(t), "year": 2026, "location": location}) for t in TIMES]
        ranges = {b["id"]: b["time_range"] for b in chart["bodies"]}
        for run in runs:
            self.assertTrue(window["earliest"]["utc"] <= run["exact"]["utc"] <= window["latest"]["utc"])
            for body in run["return"]["bodies"]:
                if body["id"] in ranges:
                    self.assertTrue(inside(body["longitude"], ranges[body["id"]]), body["id"])
        key = lambda a: (a["a"], a["b"], a["name"])
        angles = {"ASC", "MC"}
        check_aspects(self, chart["aspects"], [[a for a in run["return"]["aspects"] if a["a"] not in angles and a["b"] not in angles
                                                and a["a"] not in ("Fortune", "Spirit") and a["b"] not in ("Fortune", "Spirit")] for run in runs], key)


if __name__ == "__main__":
    unittest.main()


class UnknownEdgeCases(unittest.TestCase):
    def test_transit_motion_is_not_claimed_when_birth_time_decides_it(self):
        from natal.transits import _motion_over
        # transit 2° past a natal body that sweeps ±6.5° over the day: applying for some births, separating for others
        self.assertEqual(_motion_over(2.0, -6.5, 6.5, 0.03, 0), "time_dependent")
        self.assertEqual(_motion_over(20.0, -6.5, 6.5, 0.03, 0), "separating")

    def test_transit_motion_matches_reported_runs(self):
        moment = {"date": "2026-09-28", "time": "12:00", "timezone": "Asia/Seoul"}
        result = calculate_transits({"natal": BLIND, "moment": moment})
        runs = [{(a["transit"], a["natal"], a["name"]): a["motion"] for a in calculate_transits({"natal": at(t), "moment": moment})["aspects"]} for t in TIMES]
        for aspect in result["aspects"]:
            if aspect["motion"] != "time_dependent":
                key = (aspect["transit"], aspect["natal"], aspect["name"])
                for run in runs:
                    if key in run:
                        self.assertEqual(run[key], aspect["motion"], key)

    def test_polar_birthplace_with_unknown_time(self):
        polar = {**BLIND, "latitude": 78.22, "longitude": 15.65, "timezone": "Arctic/Longyearbyen", "place": "Longyearbyen"}
        moment = {"date": "2026-09-28", "time": "12:00", "timezone": "UTC"}
        self.assertEqual(calculate_progressions({"natal": polar, "moment": moment})["progressed"]["houses"], [])
        location = {"latitude": 78.22, "longitude": 15.65, "timezone": "Arctic/Longyearbyen"}
        self.assertEqual(calculate_solar_return({"natal": polar, "year": 2026, "location": location})["return"]["houses"], [])
