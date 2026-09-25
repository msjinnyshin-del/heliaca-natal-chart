"""Extra house systems, minor aspects, orb scale and Lilith variants (spec §3, §5, §6.1).

House cusps are checked against closed-form spherical-astronomy formulas written here, not against the
engine's own Swiss house call, so the adapter's system-code mapping and array indexing are verified.
"""
import math
import unittest

import swisseph as swe

from natal import rules
from natal.engine import calculate_chart
from natal.errors import ChartError

BASE = {"date": "1985-07-14", "time": "21:45:00", "timezone": "America/New_York", "latitude": 40.7128,
        "longitude": -74.006, "house_system": "P", "node_mode": "true"}
SEOUL = {**BASE, "date": "1990-05-01", "time": "09:30:00", "timezone": "Asia/Seoul", "latitude": 37.5665, "longitude": 126.978}
d, r = math.radians, math.degrees


def arcsec(a, b):
    return abs((a - b + 180) % 360 - 180) * 3600


def expected_cusps(chart, system):
    """Houses 11, 12, 2, 3 from RAMC, true obliquity and latitude (standard textbook constructions)."""
    n = chart["normalized"]
    eps = swe.calc(n["jd_tt"], swe.ECL_NUT, 0)[0][0]
    ramc = (swe.sidtime(n["jd_ut1"]) * 15 + n["longitude"]) % 360
    phi = n["latitude"]

    def on_ecliptic(oblique_ascension, pole):
        return r(math.atan2(math.sin(d(oblique_ascension)),
                            math.cos(d(oblique_ascension)) * math.cos(d(eps)) - math.sin(d(eps)) * math.tan(d(pole)))) % 360

    def from_ra(ra):
        return r(math.atan2(math.sin(d(ra)), math.cos(d(ra)) * math.cos(d(eps)))) % 360

    if system == "R":  # equal division of the celestial equator
        return {n_: on_ecliptic(ramc + h, r(math.atan(math.tan(d(phi)) * math.sin(d(h)))))
                for n_, h in ((11, 30), (12, 60), (2, 120), (3, 150))}
    if system == "C":  # equal division of the prime vertical
        out = {}
        for n_, h in ((11, 30), (12, 60), (2, 120), (3, 150)):
            offset = r(math.atan(math.tan(d(h)) * math.cos(d(phi)))) if h < 90 else 180 - r(math.atan(math.tan(d(180 - h)) * math.cos(d(phi))))
            out[n_] = on_ecliptic(ramc + offset, r(math.asin(math.sin(d(phi)) * math.sin(d(h)))))
        return out
    if system == "B":  # Alcabitius: trisected diurnal/nocturnal semi-arcs of the Ascendant, projected by RA
        asc = next(a for a in chart["angles"] if a["id"] == "ASC")["longitude"]
        declination = r(math.asin(math.sin(d(eps)) * math.sin(d(asc))))
        diurnal = 90 + r(math.asin(math.tan(d(phi)) * math.tan(d(declination))))
        nocturnal = 180 - diurnal
        return {11: from_ra(ramc + diurnal / 3), 12: from_ra(ramc + 2 * diurnal / 3),
                2: from_ra(ramc + diurnal + nocturnal / 3), 3: from_ra(ramc + diurnal + 2 * nocturnal / 3)}
    raise AssertionError(system)


class HouseSystems(unittest.TestCase):
    def test_new_systems_match_closed_form_cusps(self):
        for payload in (BASE, SEOUL, {**BASE, "latitude": -33.87, "longitude": 151.21, "timezone": "Australia/Sydney"}):
            placidus = {a["id"]: a["longitude"] for a in calculate_chart(payload)["angles"]}
            for system in "RCB":
                with self.subTest(place=payload["timezone"], system=system):
                    chart = calculate_chart({**payload, "house_system": system})
                    cusps = {h["number"]: h["longitude"] for h in chart["houses"]}
                    for number, longitude in expected_cusps(chart, system).items():
                        self.assertLessEqual(arcsec(cusps[number], longitude), 1, number)
                    # Quadrant systems share ASC/MC as cusps 1/10; axes stay independent of the system.
                    self.assertLessEqual(arcsec(cusps[1], placidus["ASC"]), 1e-6)
                    self.assertLessEqual(arcsec(cusps[10], placidus["MC"]), 1e-6)
                    self.assertLessEqual(arcsec(cusps[7], (cusps[1] + 180) % 360), 1e-6)
                    self.assertEqual(chart["settings"]["house_system"], system)

    def test_high_latitude_behaviour(self):
        # The Ascendant lies on the horizon, so its semi-arcs always exist and Alcabitius stays defined at 80°N;
        # its cusps must still match the closed form there.
        polar = {**BASE, "latitude": 80, "time": "00:00:00"}
        chart = calculate_chart({**polar, "house_system": "B"})
        cusps = {h["number"]: h["longitude"] for h in chart["houses"]}
        for number, longitude in expected_cusps(chart, "B").items():
            self.assertLessEqual(arcsec(cusps[number], longitude), 1, number)
        # Regiomontanus/Campanus cusps run backwards here; that is refused, never shown as a chart.
        for system in "RC":
            with self.subTest(system=system), self.assertRaises(ChartError) as caught:
                calculate_chart({**polar, "house_system": system})
            self.assertEqual(caught.exception.code, "HOUSE_SYSTEM_UNAVAILABLE")
        # ...while at another time of the same day the same place gives an ordered, valid set.
        for system in "RC":
            self.assertEqual(len(calculate_chart({**polar, "time": "12:00:00", "house_system": system})["houses"]), 12)

    def test_unknown_house_codes_are_rejected(self):
        for system in ("T", "G", "", "PP", None, 1):
            with self.subTest(system=system), self.assertRaises(ChartError):
                calculate_chart({**BASE, "house_system": system})


class MinorAspectsAndOrbScale(unittest.TestCase):
    def test_default_profile_is_major_only_and_versioned(self):
        chart = calculate_chart(BASE)
        profile = chart["settings"]["aspect_profile"]
        self.assertEqual((profile["version"], profile["minor"], profile["orb_scale"]), (rules.ASPECT_PROFILE_VERSION, [], 1.0))
        self.assertEqual(chart["settings"]["aspect_rule"], rules.ASPECT_PROFILE_VERSION)
        self.assertTrue({a["name"] for a in chart["aspects"]} <= {"Conjunction", "Sextile", "Square", "Trine", "Opposition"})

    def test_legacy_major_v2_profiles_give_identical_aspects(self):
        legacy = calculate_chart({**BASE, "aspect_profile": {"version": "major-v2"}})
        current = calculate_chart(BASE)
        self.assertEqual(legacy["aspects"], current["aspects"])

    def test_minor_aspects_are_opt_in_with_spec_orbs_and_no_luminary_bonus(self):
        chart = calculate_chart({**BASE, "aspect_profile": {"minor": list(rules.MINOR_NAMES)}})
        minors = [a for a in chart["aspects"] if a["name"] in rules.MINOR_NAMES]
        self.assertTrue(minors)
        base = {name: orb for name, _, orb in rules.MINOR_ASPECTS}
        for aspect in minors:
            self.assertLessEqual(aspect["orb"], aspect["allowed_orb"])
            if aspect["target_group"] == "planets":
                self.assertEqual(aspect["allowed_orb"], base[aspect["name"]])  # even with Sun/Moon
            else:
                self.assertLessEqual(aspect["allowed_orb"], 2)
        # Independent recomputation from the returned longitudes.
        longitudes = {b["id"]: b["longitude"] for b in chart["bodies"]} | {a["id"]: a["longitude"] for a in chart["angles"]}
        for aspect in minors:
            separation = arcsec(longitudes[aspect["a"]], longitudes[aspect["b"]]) / 3600
            self.assertAlmostEqual(abs(separation - aspect["angle"]), aspect["orb"], places=9)

    def test_orb_scale_multiplies_base_orbs(self):
        half = calculate_chart({**BASE, "aspect_profile": {"orb_scale": 0.5}})
        full = calculate_chart(BASE)
        self.assertTrue({a["id"] + a["name"] for a in half["aspects"]} <= {a["id"] + a["name"] for a in full["aspects"]})
        for aspect in half["aspects"]:
            if aspect["target_group"] == "planets":
                base = next(orb for name, _, orb in rules.ASPECTS if name == aspect["name"])
                bonus = 2 if "Sun" in (aspect["a"], aspect["b"]) or "Moon" in (aspect["a"], aspect["b"]) else 0
                self.assertAlmostEqual(aspect["allowed_orb"], (base + bonus) * 0.5)

    def test_invalid_profile_options(self):
        for profile in ({"orb_scale": 0}, {"orb_scale": 0.4}, {"orb_scale": 1.5}, {"orb_scale": "1"}, {"orb_scale": True},
                        {"version": "major-v2", "minor": ["Quincunx"]}, {"version": "major-v2", "orb_scale": 1.2},
                        {"orb_scale": float("nan")}, {"minor": ["BiQuintile"]}, {"minor": "Quincunx"},
                        {"minor": ["Quincunx", "Quincunx"]}, {"version": "major-v1"}):
            with self.subTest(profile=profile), self.assertRaises(ChartError) as caught:
                calculate_chart({**BASE, "aspect_profile": profile})
            self.assertEqual(caught.exception.code, "INVALID_INPUT")

    def test_allowed_ranges_never_overlap_at_the_maximum_scale(self):
        # A pair must never qualify for two aspects at once; this bounds the orb scale.
        profile = rules.normalize_aspect_profile({"minor": list(rules.MINOR_NAMES), "orb_scale": rules.ORB_SCALE_MAX,
                                                  "targets": {"nodes": True, "lots": True}})
        bodies = [{"id": body_id, "longitude": 0.0} for body_id in (*rules.PLANETS, "Chiron", "Lilith", "NorthNode", "Fortune")]
        by_pair = {}
        for a, b, group, name, target, allowed in rules.aspect_candidates(bodies, [{"id": "ASC", "longitude": 0.0}], profile):
            by_pair.setdefault((a["id"], b["id"]), []).append((target - allowed, target + allowed, name))
        for pair, ranges in by_pair.items():
            ranges.sort()
            for (lo1, hi1, n1), (lo2, hi2, n2) in zip(ranges, ranges[1:]):
                self.assertLess(hi1, lo2, (pair, n1, n2))


class ExtraPointOrbs(unittest.TestCase):
    def test_extra_point_orbs_follow_scale_user_cap_and_minor_cap(self):
        bodies = [{"id": "Sun", "longitude": 0.0}, {"id": "Mars", "longitude": 0.0}, {"id": "Chiron", "longitude": 0.0}]
        profile = rules.normalize_aspect_profile({"minor": list(rules.MINOR_NAMES), "orb_scale": 1.4,
                                                  "orbs": {"chiron": 2.5}})
        allowed = {(a["id"], b["id"], name): orb for a, b, _, name, _, orb in rules.aspect_candidates(bodies, [], profile)}
        expected = {
            ("Sun", "Mars", "Conjunction"): 14.0, ("Sun", "Mars", "Sextile"): 8.4, ("Sun", "Mars", "Quincunx"): 4.2,
            ("Sun", "Mars", "Quintile"): 2.8,  # minor: no luminary bonus
            ("Sun", "Chiron", "Conjunction"): 2.5, ("Sun", "Chiron", "Sextile"): 2.5,  # user cap below 4*1.4
            ("Sun", "Chiron", "Quincunx"): 2.0, ("Sun", "Chiron", "SemiSquare"): 2.0,  # minor extra cap 2 deg
        }
        for key, value in expected.items():
            self.assertAlmostEqual(allowed[key], value, msg=key)

    def test_unknown_time_scan_uses_scaled_and_minor_orbs(self):
        chart = calculate_chart({**SEOUL, "time": None, "time_accuracy": "unknown",
                                 "aspect_profile": {"minor": list(rules.MINOR_NAMES), "orb_scale": 0.5}})
        minor = [a for a in chart["aspects"] if a["name"] in rules.MINOR_NAMES]
        self.assertTrue(minor)
        for aspect in chart["aspects"]:
            if aspect["target_group"] == "planets" and aspect["name"] in rules.MINOR_NAMES:
                self.assertAlmostEqual(aspect["allowed_orb"], dict((n, o) for n, _, o in rules.MINOR_ASPECTS)[aspect["name"]] * 0.5)
        # Window edges sit on the scaled orb boundary: re-check one partial edge through the reported path.
        from datetime import datetime, timedelta
        for aspect in (a for a in chart["aspects"] if a["stability"] == "partial"):
            window = aspect["windows"][0]
            edge = window["start_local"] if not window["start_local"].endswith("T00:00:00") else window["end_local"]
            if edge.endswith("T00:00:00"):
                continue
            moment = datetime.fromisoformat(edge)
            orbs = []
            for delta in (-5, 5):
                t = moment + timedelta(seconds=delta)
                bodies = {b["id"]: b for b in calculate_chart({**SEOUL, "date": t.date().isoformat(), "time": t.strftime("%H:%M:%S")})["bodies"]}
                orbs.append(abs(arcsec(bodies[aspect["a"]]["longitude"], bodies[aspect["b"]]["longitude"]) / 3600 - aspect["angle"]))
            self.assertTrue(min(orbs) <= aspect["allowed_orb"] < max(orbs), (aspect["id"], aspect["name"], edge, orbs))
            break
        else:
            self.fail("no partial aspect with an interior edge")


class MultiChartSettings(unittest.TestCase):
    def test_composite_requires_matching_definitions(self):
        from natal.composite import calculate_composite
        a = {**BASE, "house_system": "B"}
        for b in ({**SEOUL, "house_system": "P"}, {**SEOUL, "house_system": "B", "lilith_mode": "osculating"},
                  {**SEOUL, "house_system": "B", "aspect_profile": {"minor": ["Quincunx"]}}):
            with self.subTest(b=b), self.assertRaises(ChartError) as caught:
                calculate_composite({"person_a": a, "person_b": b})
            self.assertEqual(caught.exception.code, "INVALID_INPUT")
        result = calculate_composite({"person_a": a, "person_b": {**SEOUL, "house_system": "B"}})
        self.assertEqual(len(result["composite"]["houses"]), 12)
        self.assertEqual(result["composite"]["settings"]["house_system"], "B")

    def test_synastry_accepts_new_house_systems(self):
        from natal.synastry import calculate_synastry
        result = calculate_synastry({"person_a": {**BASE, "house_system": "R"}, "person_b": {**SEOUL, "house_system": "C"}})
        self.assertTrue(result["aspects"])


class LilithModes(unittest.TestCase):
    def test_mean_is_default_and_osculating_is_a_separate_named_point(self):
        mean = calculate_chart(BASE)
        oscu = calculate_chart({**BASE, "lilith_mode": "osculating"})
        m = next(b for b in mean["bodies"] if b["id"] == "Lilith")
        o = next(b for b in oscu["bodies"] if b["id"] == "Lilith")
        self.assertEqual((mean["settings"]["lilith_mode"], oscu["settings"]["lilith_mode"]), ("mean", "osculating"))
        self.assertIn("평균", m["name"])
        self.assertIn("오스큘레이팅", o["name"])
        self.assertGreater(arcsec(m["longitude"], o["longitude"]), 60)
        expected = swe.calc(oscu["normalized"]["jd_tt"], swe.OSCU_APOG, swe.FLG_SWIEPH | swe.FLG_SPEED)[0][0]
        self.assertLessEqual(arcsec(o["longitude"], expected), 1e-6)
        others = {b["id"]: b["longitude"] for b in oscu["bodies"] if b["id"] != "Lilith"}
        self.assertEqual(others, {b["id"]: b["longitude"] for b in mean["bodies"] if b["id"] != "Lilith"})

    def test_invalid_lilith_mode(self):
        for mode in ("true", "interpolated", "", None, 1):
            with self.subTest(mode=mode), self.assertRaises(ChartError) as caught:
                calculate_chart({**BASE, "lilith_mode": mode})
            self.assertEqual(caught.exception.code, "INVALID_INPUT")

    def test_osculating_lilith_works_with_unknown_time_scan(self):
        chart = calculate_chart({**SEOUL, "time": None, "time_accuracy": "unknown", "lilith_mode": "osculating"})
        lilith = next(b for b in chart["bodies"] if b["id"] == "Lilith")
        self.assertIn("range", lilith["time_sensitivity"])


if __name__ == "__main__":
    unittest.main()
