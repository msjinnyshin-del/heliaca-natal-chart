"""Versioned longitude rules; display rounding never feeds classification."""
import math

from .errors import ChartError

SIGNS = ("양", "황소", "쌍둥이", "게", "사자", "처녀", "천칭", "전갈", "사수", "염소", "물병", "물고기")
PLANETS = ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto")
ASPECTS = (("Conjunction", 0, 8), ("Sextile", 60, 4), ("Square", 90, 6), ("Trine", 120, 6), ("Opposition", 180, 8))
ASPECT_PROFILE_VERSION = "major-v2"
EXTRA_GROUPS = ("chiron", "lilith", "nodes", "lots", "angles")
DEFAULT_ASPECT_PROFILE = {
    "version": ASPECT_PROFILE_VERSION,
    "targets": {"chiron": True, "lilith": True, "nodes": False, "lots": False, "angles": ["ASC", "MC"]},
    "orbs": {"chiron": 3.0, "lilith": 3.0, "nodes": 3.0, "lots": 3.0, "angles": 3.0},
}


def normalize_aspect_profile(value=None):
    if value is None:
        value = {}
    if not isinstance(value, dict) or set(value) - {"version", "targets", "orbs"}:
        raise ChartError("INVALID_INPUT", "aspect_profile은 version, targets, orbs 객체여야 합니다.")
    if value.get("version", ASPECT_PROFILE_VERSION) != ASPECT_PROFILE_VERSION:
        raise ChartError("INVALID_INPUT", f"지원하는 aspect profile은 {ASPECT_PROFILE_VERSION}입니다.")
    raw_targets = value.get("targets", {})
    raw_orbs = value.get("orbs", {})
    if not isinstance(raw_targets, dict) or set(raw_targets) - set(EXTRA_GROUPS):
        raise ChartError("INVALID_INPUT", "aspect target 그룹이 올바르지 않습니다.")
    if not isinstance(raw_orbs, dict) or set(raw_orbs) - set(EXTRA_GROUPS):
        raise ChartError("INVALID_INPUT", "aspect orb 그룹이 올바르지 않습니다.")
    targets = dict(DEFAULT_ASPECT_PROFILE["targets"])
    orbs = dict(DEFAULT_ASPECT_PROFILE["orbs"])
    for group in ("chiron", "lilith", "nodes", "lots"):
        if group in raw_targets and type(raw_targets[group]) is not bool:
            raise ChartError("INVALID_INPUT", f"aspect target {group}은 boolean이어야 합니다.")
        if group in raw_targets:
            targets[group] = raw_targets[group]
    if "angles" in raw_targets:
        angle_targets = raw_targets["angles"]
        if (not isinstance(angle_targets, list) or any(not isinstance(item, str) for item in angle_targets)
                or len(set(angle_targets)) != len(angle_targets) or any(item not in ("ASC", "MC") for item in angle_targets)):
            raise ChartError("INVALID_INPUT", "angle aspect target은 ASC와 MC의 중복 없는 배열이어야 합니다.")
        targets["angles"] = [item for item in ("ASC", "MC") if item in angle_targets]
    for group, orb in raw_orbs.items():
        if isinstance(orb, bool) or not isinstance(orb, (int, float)) or not math.isfinite(orb) or not 0 <= orb <= 3:
            raise ChartError("INVALID_INPUT", f"{group} aspect orb는 0 이상 3 이하의 유한한 수여야 합니다.")
        orbs[group] = float(orb)
    return {"version": ASPECT_PROFILE_VERSION, "targets": targets, "orbs": orbs}


def position(longitude):
    raw = longitude % 360
    # Integer arithmetic handles rounding into the next sign and 360 -> 0.
    seconds = int(math.floor(raw * 3600 + 0.5)) % 1296000
    display_sign, seconds = divmod(seconds, 108000)
    degrees, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return {"longitude": raw, "sign_index": int(raw // 30), "display_sign_index": display_sign,
            "position": f"{SIGNS[display_sign]} {degrees:02d}°{minutes:02d}′{seconds:02d}″"}


def house_for(longitude, cusps):
    matches = [i + 1 for i in range(12) if (longitude - cusps[i]) % 360 < (cusps[(i + 1) % 12] - cusps[i]) % 360]
    if len(matches) != 1:
        raise ChartError("HOUSE_SYSTEM_UNAVAILABLE", "황경을 하나의 하우스에 배정할 수 없습니다.")
    return matches[0]


def lots(asc, sun, moon, altitude):
    sect = "day" if altitude >= 0 else "night"
    difference = moon - sun if sect == "day" else sun - moon
    return sect, (asc + difference) % 360, (asc - difference) % 360


def aspect_candidates(bodies, angles, profile):
    """Every (a, b, group, name, target, allowed orb) the profile would test; shared by the day scan."""
    output = []
    bodies_by_id = {body["id"]: body for body in bodies}
    angles_by_id = {angle["id"]: angle for angle in angles}
    planets = [bodies_by_id[body_id] for body_id in PLANETS if body_id in bodies_by_id]
    extras = []
    if profile["targets"]["chiron"] and "Chiron" in bodies_by_id:
        extras.append((bodies_by_id["Chiron"], "chiron"))
    if profile["targets"]["lilith"] and "Lilith" in bodies_by_id:
        extras.append((bodies_by_id["Lilith"], "lilith"))
    if profile["targets"]["nodes"] and "NorthNode" in bodies_by_id:
        extras.append((bodies_by_id["NorthNode"], "nodes"))
    if profile["targets"]["lots"]:
        extras.extend((bodies_by_id[item], "lots") for item in ("Fortune", "Spirit") if item in bodies_by_id)
    extras.extend((angles_by_id[item], "angles") for item in profile["targets"]["angles"] if item in angles_by_id)

    pairs = []
    for i, a in enumerate(planets):
        pairs.extend((a, b, "planets") for b in planets[i + 1:])
        pairs.extend((a, b, group) for b, group in extras)
    for a, b, group in pairs:
        for name, target, base_orb in ASPECTS:
            allowed = (base_orb + (2 if a["id"] in ("Sun", "Moon") or b["id"] in ("Sun", "Moon") else 0)
                       if group == "planets" else min(base_orb, profile["orbs"][group]))
            output.append((a, b, group, name, target, allowed))
    return output


def separation_of(lon_a, lon_b):
    return abs((lon_a - lon_b + 180) % 360 - 180)


def aspect_entry(a, b, group, name, target, allowed, separation, profile):
    return {"id": "|".join(sorted((a["id"], b["id"]))), "a": a["id"], "b": b["id"],
            "name": name, "angle": target, "separation": separation, "orb": abs(separation - target),
            "allowed_orb": allowed, "rule_version": ASPECT_PROFILE_VERSION,
            "profile_version": profile["version"], "target_group": group,
            "motion": "not_evaluated"}


def aspects(bodies, angles, profile=None):
    profile = normalize_aspect_profile(profile)
    output = []
    for a, b, group, name, target, allowed in aspect_candidates(bodies, angles, profile):
        separation = separation_of(a["longitude"], b["longitude"])
        if abs(separation - target) <= allowed:
            output.append(aspect_entry(a, b, group, name, target, allowed, separation, profile))
    return output
