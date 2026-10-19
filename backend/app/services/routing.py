"""Straight-line route distances and a heuristic visiting order.

Distances are great-circle ("as the crow flies") kilometres, not road,
walking or transit distance. The order comes from nearest neighbour plus
2-opt: usually good, never guaranteed shortest.
"""
from dataclasses import dataclass
import math
from typing import Optional, Sequence


EARTH_RADIUS_KM = 6371.0088  # IUGG mean radius
EPSILON_KM = 1e-9

Point = tuple[float, float]  # (latitude, longitude) in degrees


def haversine_km(a: Point, b: Point) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    # sin² of half the longitude difference is periodic, so ±180° needs no special case.
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    # Rounding can push h fractionally outside [0, 1] for identical or antipodal points.
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, max(0.0, h))))


def path_km(points: Sequence[Point]) -> float:
    return sum(haversine_km(a, b) for a, b in zip(points, points[1:]))


def order_segment(points: Sequence[Point], start: Optional[Point] = None,
                  end: Optional[Point] = None) -> list[int]:
    """Return an order of `points` (as indexes) for a short open path start → … → end.

    `start` and `end` are fixed neighbours outside the segment; either may be absent.
    Ties resolve by index, so equal input always yields the same order.
    """
    n = len(points)
    if n <= 1:
        return list(range(n))
    if start is None and end is not None:
        # Distances are symmetric: solve from the fixed end, then walk it backwards.
        return order_segment(points, start=end)[::-1]
    nodes = list(points) + [start or (0.0, 0.0), end or (0.0, 0.0)]
    s, e = n, n + 1
    dist = [[haversine_km(a, b) for b in nodes] for a in nodes]

    def edge(i: Optional[int], j: Optional[int]) -> float:
        # A missing endpoint is an open path end: that edge costs nothing.
        if i is None or j is None or (i == s and start is None) or (j == e and end is None):
            return 0.0
        return dist[i][j]

    def cost(order: list[int]) -> float:
        return edge(s, order[0]) + sum(dist[a][b] for a, b in zip(order, order[1:])) + edge(order[-1], e)

    def nearest_neighbour(first: int) -> list[int]:
        remaining = list(range(n))
        remaining.remove(first)
        order, current = [first], first
        while remaining:
            current = min(remaining, key=lambda j: (dist[current][j], j))
            remaining.remove(current)
            order.append(current)
        return order

    def two_opt(order: list[int]) -> list[int]:
        improved = True
        while improved:
            improved = False
            for i in range(n - 1):
                before = order[i - 1] if i > 0 else s
                for j in range(i + 1, n):
                    after = order[j + 1] if j + 1 < n else e
                    # Reversing order[i..j] only changes its two boundary edges.
                    delta = (edge(before, order[j]) + edge(order[i], after)
                             - edge(before, order[i]) - edge(order[j], after))
                    if delta < -EPSILON_KM:
                        order[i:j + 1] = reversed(order[i:j + 1])
                        improved = True
        return order

    # Greedy from every possible first stop: one greedy tour from a fixed start
    # is often trapped, and n <= 50 keeps n restarts cheap.
    seeds = [nearest_neighbour(i) for i in range(n)]
    candidates = [two_opt(seed) for seed in seeds]
    return min(candidates, key=lambda order: (round(cost(order), 9), order))


@dataclass(frozen=True)
class Stop:
    item_id: int
    point: Optional[Point]
    anchored: bool


def located_points(stops: Sequence[Stop]) -> list[Point]:
    return [stop.point for stop in stops if stop.point is not None]


def propose_order(stops: Sequence[Stop]) -> list[int]:
    """Reorder only runs of movable stops between anchors.

    Anchors (timed, unlocated or pinned items) keep their exact positions, so no
    item ever moves across one. Movable stops must have a point. The result is
    never longer than the original; if it is not shorter, the original is kept.
    """
    if any(not stop.anchored and stop.point is None for stop in stops):
        raise ValueError("Unlocated stops must be anchored")
    original = [stop.item_id for stop in stops]
    proposed: list[Stop] = []
    index = 0
    while index < len(stops):
        if stops[index].anchored:
            proposed.append(stops[index])
            index += 1
            continue
        segment_end = index
        while segment_end < len(stops) and not stops[segment_end].anchored:
            segment_end += 1
        segment = stops[index:segment_end]
        # Unlocated stops are transparent to distance, so connect to the nearest located ones.
        start = next((s.point for s in reversed(proposed) if s.point is not None), None)
        end = None
        for following in stops[segment_end:]:
            if not following.anchored:
                break  # The next segment's first stop is not decided yet.
            if following.point is not None:
                end = following.point
                break
        order = order_segment([stop.point for stop in segment], start, end)
        proposed.extend(segment[i] for i in order)
        index = segment_end
    if path_km(located_points(proposed)) < path_km(located_points(stops)) - EPSILON_KM:
        return [stop.item_id for stop in proposed]
    return original
