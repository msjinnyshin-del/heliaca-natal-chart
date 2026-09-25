"""Whole-local-day scan for unknown birth time (spec §2.3, rule `unknown-day-scan-v1`).

The day is sampled every 10 minutes; state changes between samples are bisected, and local extrema are
refined so a short orb touch (or a short gap) between two samples is not missed. Endpoint-only comparison
is never used. Functions take a fraction f in [0, 1] of the local day.
"""
from datetime import timedelta
import math

from .time_input import format_offset
from .rules import aspect_candidates, aspect_entry, position, separation_of

RULE_VERSION = "unknown-day-scan-v1"
STEP_MINUTES = 10
BISECT_ITERATIONS = 12  # a 10-minute step shrinks below 0.2 s
EXTREMUM_ITERATIONS = 40
GOLDEN = (math.sqrt(5) - 1) / 2


def _samples(steps):
    return [k / steps for k in range(steps + 1)]


def bisect(lo, hi, changed, iterations=BISECT_ITERATIONS):
    """Boundary in (lo, hi] where `changed(f)` first becomes true; changed(lo) is false, changed(hi) true."""
    for _ in range(iterations):
        mid = (lo + hi) / 2
        if changed(mid):
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def find_crossings(func, steps):
    """Fractions where `func(f) <= 0` switches between consecutive samples."""
    fs = _samples(steps)
    values = [func(f) <= 0 for f in fs]
    roots = []
    for k in range(steps):
        if values[k] != values[k + 1]:
            start = values[k]
            roots.append(bisect(fs[k], fs[k + 1], lambda f, start=start: (func(f) <= 0) != start))
    return roots


def _extremum(func, lo, hi, maximize):
    sign = -1 if maximize else 1
    a, b = lo, hi
    c, d = b - GOLDEN * (b - a), a + GOLDEN * (b - a)
    fc, fd = sign * func(c), sign * func(d)
    for _ in range(EXTREMUM_ITERATIONS):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - GOLDEN * (b - a)
            fc = sign * func(c)
        else:
            a, c, fc = c, d, fd
            d = a + GOLDEN * (b - a)
            fd = sign * func(d)
    point = (a + b) / 2
    return point, func(point)


def find_windows(func, steps):
    """Maximal [start, end] fractions where func(f) <= 0, including touches and gaps shorter than a step."""
    fs = _samples(steps)
    values = [func(f) for f in fs]
    inside = [value <= 0 for value in values]
    boundaries = []
    for k in range(steps):
        if inside[k] != inside[k + 1]:
            start = inside[k]
            boundaries.append(bisect(fs[k], fs[k + 1], lambda f, start=start: (func(f) <= 0) != start))
    # Brackets around every sampled local extremum (and the two edge intervals) whose neighbours share a state.
    brackets = set()
    for k in range(steps + 1):
        lo, hi = fs[max(k - 1, 0)], fs[min(k + 1, steps)]
        neighbours = [values[j] for j in (k - 1, k + 1) if 0 <= j <= steps]
        if any(inside[j] != inside[k] for j in (k - 1, k + 1) if 0 <= j <= steps):
            continue
        is_min = all(values[k] <= value for value in neighbours)
        is_max = all(values[k] >= value for value in neighbours)
        if (is_min and not inside[k]) or (is_max and inside[k]) or k in (0, steps):
            brackets.add((lo, hi, inside[k]))
    for lo, hi, state in sorted(brackets):
        point, value = _extremum(func, lo, hi, maximize=state)
        if (value <= 0) != state:
            flips = lambda f, state=state: (func(f) <= 0) != state
            boundaries.append(bisect(lo, point, flips))
            boundaries.append(bisect(point, hi, lambda f, state=state: (func(f) <= 0) == state))
    # Classify every piece between boundaries by its midpoint instead of toggling state at each boundary,
    # so a duplicated or missed boundary can never invert the rest of the day.
    cuts = [0.0] + sorted(b for b in boundaries if 0.0 < b < 1.0) + [1.0]
    windows = []
    for lo, hi in zip(cuts, cuts[1:]):
        if hi - lo <= 1e-12 or func((lo + hi) / 2) > 0:
            continue
        if windows and lo - windows[-1][1] <= 1e-6:
            windows[-1] = (windows[-1][0], hi)
        else:
            windows.append((lo, hi))
    return windows


def _travel(fs, longitude):
    """Total angular path over the sampled day (retrograde loops counted), in degrees."""
    values = [longitude(f) for f in fs]
    return sum(separation_of(a, b) for a, b in zip(values, values[1:]))


class DayClock:
    """Maps a day fraction to TT Julian day (linear; ΔT drift within one day is sub-millisecond) and to civil time."""

    def __init__(self, start_utc, end_utc, start_tt, end_tt, zone):
        self.start_utc, self.seconds = start_utc, (end_utc - start_utc).total_seconds()
        self.start_tt, self.span_tt, self.zone = start_tt, end_tt - start_tt, zone
        self.steps = max(1, round(self.seconds / 60 / STEP_MINUTES))

    def jd_tt(self, f):
        return self.start_tt + f * self.span_tt

    def stamp(self, f):
        utc = self.start_utc + timedelta(seconds=round(f * self.seconds))
        local = utc.astimezone(self.zone)
        # The offset tells a repeated local hour (25-hour day) apart.
        return {"utc": utc.isoformat().replace("+00:00", "Z"),
                "local": local.replace(tzinfo=None).isoformat(timespec="seconds"),
                "offset": format_offset(local.utcoffset())}


def scan_day(clock, positions, noon_bodies, profile):
    """`positions(jd_tt)` returns {body_id: (longitude, speed)}. Returns (sensitivity by body id, aspects)."""
    cache = {}

    def at(f):
        if f not in cache:
            cache[f] = positions(clock.jd_tt(f))
        return cache[f]

    fs = _samples(clock.steps)
    sensitivity = {}
    for body in noon_bodies:
        body_id = body["id"]
        sign = lambda f, body_id=body_id: int(at(f)[body_id][0] % 360 // 30)
        ingresses, signs = [], [sign(0.0)]
        for k in range(clock.steps):
            left, right = sign(fs[k]), sign(fs[k + 1])
            if left != right:
                point = bisect(fs[k], fs[k + 1], lambda f, left=left, sign=sign: sign(f) != left)
                after = sign(min(point + 1e-6, 1.0))
                ingresses.append({**clock.stamp(point), "from_sign_index": left, "to_sign_index": after})
                signs.append(after)
        stations = []
        for point in find_crossings(lambda f, body_id=body_id: at(f)[body_id][1], clock.steps):
            after = at(min(point + 1e-4, 1.0))[body_id][1]
            stations.append({**clock.stamp(point), "to": "R" if after < 0 else "D"})
        first, last = at(0.0)[body_id][0], at(1.0)[body_id][0]
        sensitivity[body_id] = {"sign_stable": not ingresses, "signs": signs, "ingresses": ingresses,
                                "direction_stable": not stations, "stations": stations,
                                # Where the body was at the first and last instant of the local day.
                                "range": {"start": position(first), "end": position(last),
                                          "degrees": _travel(fs, lambda f, body_id=body_id: at(f)[body_id][0])}}

    output = []
    for a, b, group, name, target, allowed in aspect_candidates(noon_bodies, [], profile):
        deviation = (lambda f, a=a["id"], b=b["id"], target=target, allowed=allowed:
                     abs(separation_of(at(f)[a][0], at(f)[b][0]) - target) - allowed)
        windows = find_windows(deviation, clock.steps)
        if not windows:
            continue
        noon_separation = separation_of(a["longitude"], b["longitude"])
        entry = aspect_entry(a, b, group, name, target, allowed, noon_separation, profile)
        entry.update({
            "stability": "stable" if windows == [(0.0, 1.0)] else "partial",
            "in_orb_at_representative": abs(noon_separation - target) <= allowed,
            "windows": [{"start_utc": clock.stamp(start)["utc"], "end_utc": clock.stamp(end)["utc"],
                         "start_local": clock.stamp(start)["local"], "end_local": clock.stamp(end)["local"],
                         "start_offset": clock.stamp(start)["offset"], "end_offset": clock.stamp(end)["offset"]}
                        for start, end in windows],
        })
        output.append(entry)
    return sensitivity, output
