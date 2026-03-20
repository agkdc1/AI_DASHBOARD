"""Human-like mouse trajectory generation using cubic Bezier curves."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class Point:
    x: float
    y: float


def bezier_curve(
    p0: Point,
    p1: Point,
    p2: Point,
    p3: Point,
    steps: int = 50,
) -> list[Point]:
    """Evaluate a cubic Bezier curve at *steps* evenly spaced t values."""
    points: list[Point] = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        x = u**3 * p0.x + 3 * u**2 * t * p1.x + 3 * u * t**2 * p2.x + t**3 * p3.x
        y = u**3 * p0.y + 3 * u**2 * t * p1.y + 3 * u * t**2 * p2.y + t**3 * p3.y
        points.append(Point(x, y))
    return points


def _random_control_points(start: Point, end: Point) -> tuple[Point, Point]:
    """Generate 2 control points that create a natural arc."""
    mid_x = (start.x + end.x) / 2
    mid_y = (start.y + end.y) / 2
    dx = end.x - start.x
    dy = end.y - start.y
    dist = math.hypot(dx, dy)
    # Perpendicular offset scaled to distance
    offset = random.uniform(30, min(100, dist * 0.4)) * random.choice([-1, 1])
    # Perpendicular direction
    if dist > 0:
        perp_x = -dy / dist
        perp_y = dx / dist
    else:
        perp_x, perp_y = 0, 1

    cp1 = Point(
        mid_x + perp_x * offset * random.uniform(0.3, 0.7) + random.uniform(-10, 10),
        mid_y + perp_y * offset * random.uniform(0.3, 0.7) + random.uniform(-10, 10),
    )
    cp2 = Point(
        mid_x + perp_x * offset * random.uniform(0.3, 0.7) + random.uniform(-10, 10),
        mid_y + perp_y * offset * random.uniform(0.3, 0.7) + random.uniform(-10, 10),
    )
    return cp1, cp2


def generate_path(
    start: tuple[int, int],
    end: tuple[int, int],
    control_points: list[dict[str, int]] | None = None,
    jitter_sigma: float = 1.5,
) -> list[tuple[int, int]]:
    """Return a list of (x, y) integer coordinates for a human-like mouse path.

    If *control_points* are provided (from Gemini), use them as Bezier CPs.
    Otherwise generate random ones.
    """
    p0 = Point(*start)
    p3 = Point(*end)

    if control_points and len(control_points) >= 2:
        p1 = Point(control_points[0]["x"], control_points[0]["y"])
        p2 = Point(control_points[1]["x"], control_points[1]["y"])
    elif control_points and len(control_points) == 1:
        p1 = Point(control_points[0]["x"], control_points[0]["y"])
        p2, = _random_control_points(p0, p3)[1:2] or (p1,)
        _, p2 = _random_control_points(p0, p3)
    else:
        p1, p2 = _random_control_points(p0, p3)

    dist = math.hypot(p3.x - p0.x, p3.y - p0.y)
    steps = max(20, int(dist / 5))
    raw = bezier_curve(p0, p1, p2, p3, steps=steps)

    # Add Gaussian jitter
    path: list[tuple[int, int]] = []
    for pt in raw:
        jx = pt.x + random.gauss(0, jitter_sigma)
        jy = pt.y + random.gauss(0, jitter_sigma)
        path.append((int(round(jx)), int(round(jy))))

    # Overshoot: 15% chance of overshooting by 5-15px then correcting
    if random.random() < 0.15 and dist > 30:
        overshoot_dist = random.uniform(5, 15)
        dx = p3.x - p0.x
        dy = p3.y - p0.y
        if dist > 0:
            ox = int(p3.x + dx / dist * overshoot_dist)
            oy = int(p3.y + dy / dist * overshoot_dist)
            path.append((ox, oy))
        # Correct back
        path.append((int(p3.x), int(p3.y)))

    return path


def ease_in_out(t: float) -> float:
    """Ease-in-out timing function (slow start, fast middle, slow end)."""
    if t < 0.5:
        return 2 * t * t
    return -1 + (4 - 2 * t) * t


def compute_delays(n_points: int, total_ms: int) -> list[int]:
    """Compute per-step delays (ms) that follow an ease-in-out speed profile."""
    if n_points <= 1:
        return [total_ms]

    # Raw speed factors (inverse of ease-in-out derivative approx)
    raw: list[float] = []
    for i in range(n_points - 1):
        t = (i + 0.5) / (n_points - 1)
        speed = max(0.1, abs(4 * t - 2))  # derivative of ease_in_out
        raw.append(1.0 / speed)

    total_raw = sum(raw)
    delays = [max(1, int(r / total_raw * total_ms)) for r in raw]

    # Adjust to match total
    diff = total_ms - sum(delays)
    if diff != 0 and delays:
        delays[-1] = max(1, delays[-1] + diff)

    return delays


def fitts_duration(distance: float) -> int:
    """Estimate movement duration (ms) using Fitts's Law approximation."""
    a, b = 200, 150  # base ms + log factor
    if distance < 1:
        return a
    return int(a + b * math.log2(1 + distance / 10))
