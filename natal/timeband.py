"""Relations that depend on an unknown birth time (spec §2.3, §11), shared by the multi-chart tools.

A "track" is a list of {body: longitude} samples along a path (usually every 10 minutes of the unknown
birth day). Between samples a body is treated as moving linearly; for the Moon over 10 minutes that is off
by far less than an arcsecond. Orb extremes are found exactly on that piecewise-linear path: within a segment
the orb only turns at 0°/180° separation or at the aspect angle itself, so ends and kinks suffice.
"""
import math

from .rules import position

STABLE, TIME_DEPENDENT = "stable", "time_dependent"


def signed(delta):
    return (delta + 180) % 360 - 180


def orb_range(difference, low, high, target):
    """Min/max orb from `target` while the directed difference A−B runs over [difference+low, difference+high]."""
    start, end = difference + low, difference + high
    points = [start, end]
    for kink in (0.0, 180.0, target, -target):
        k = kink + 360 * math.ceil((start - kink) / 360)
        while k <= end:
            points.append(k)
            k += 360
    orbs = [abs(abs(signed(point)) - target) for point in points]
    return min(orbs), max(orbs)


def unwrap(values):
    """Continuous (unwrapped) copy of a sampled longitude path."""
    out = [values[0]]
    for value in values[1:]:
        out.append(out[-1] + signed(value - out[-1]))
    return out


def path_orb_range(differences, target):
    """Min/max orb along a sampled path of directed differences A−B (both ends move together, e.g. the same birth time)."""
    path = unwrap(differences)
    low, high = math.inf, -math.inf
    for x, y in zip(path, path[1:] or path):
        lo, hi = orb_range(min(x, y), 0.0, abs(y - x), target)
        low, high = min(low, lo), max(high, hi)
    return low, high


def sweep(values, reference):
    """(low, high) offsets from `reference` over a sampled path (for independent unknown times)."""
    offsets = [signed(value - reference) for value in values]
    return min(offsets), max(offsets)


def classify(low, high, allowed):
    """None when never in orb; otherwise STABLE (in orb along the whole path) or TIME_DEPENDENT."""
    if low > allowed:
        return None
    return STABLE if high <= allowed else TIME_DEPENDENT


def body_range(representative, low, high):
    """Display range of a body that moves between reference+low and reference+high."""
    start, end = (representative + low) % 360, (representative + high) % 360
    first, last = math.floor((representative + low) / 30), math.floor((representative + high) / 30)
    signs = [index % 12 for index in range(first, last + 1)]
    return {"start": position(start), "end": position(end), "degrees": high - low,
            "sign_stable": len(signs) == 1, "signs": signs}
