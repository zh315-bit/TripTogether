import itertools
import math
import random

import pytest

from app.services.routing import (
    EARTH_RADIUS_KM, Stop, haversine_km, order_segment, path_km, propose_order,
)


def cost(points, order, start=None, end=None):
    sequence = ([start] if start else []) + [points[i] for i in order] + ([end] if end else [])
    return path_km(sequence)


def brute_force(points, start=None, end=None):
    return min(cost(points, list(p), start, end) for p in itertools.permutations(range(len(points))))


def random_points(rng, n):
    return [(35 + rng.random(), 139 + rng.random()) for _ in range(n)]


# ---- Haversine -----------------------------------------------------------

@pytest.mark.parametrize("a,b,expected", [
    ((48.8566, 2.3522), (51.5074, -0.1278), 343.5),        # Paris - London
    ((0, 0), (0, 1), math.pi * EARTH_RADIUS_KM / 180),     # one degree of the equator
    ((10, 20), (11, 20), math.pi * EARTH_RADIUS_KM / 180),   # one degree of a meridian
    ((0, 179.9), (0, -179.9), 22.24),                       # across the antimeridian
    ((0, -180), (0, 180), 0.0),                             # same meridian, two spellings
    ((90, 0), (-90, 0), math.pi * EARTH_RADIUS_KM),         # pole to pole
    ((0, 0), (0, 180), math.pi * EARTH_RADIUS_KM),          # antipodal: clamp keeps asin defined
    ((89.999999, 10), (89.999999, -170), 0.0002224),        # across the pole
])
def test_haversine_known_distances(a, b, expected):
    assert haversine_km(a, b) == pytest.approx(expected, rel=2e-3, abs=1e-3)
    assert haversine_km(a, b) == pytest.approx(haversine_km(b, a))


def test_identical_points_are_zero():
    assert haversine_km((35.714766, 139.796655), (35.714766, 139.796655)) == 0.0
    assert path_km([]) == 0.0 and path_km([(1, 1)]) == 0.0


# ---- Segment ordering ----------------------------------------------------

@pytest.mark.parametrize("n", [0, 1])
def test_trivial_segments(n):
    assert order_segment([(35.0, 139.0)] * n) == list(range(n))


def test_matches_brute_force_on_small_inputs():
    # Seeded, so this is deterministic; it measures quality, not just validity.
    rng = random.Random(20261014)
    optimal = trials = 0
    for trial in range(300):
        points = random_points(rng, rng.randint(2, 7))
        start = random_points(rng, 1)[0] if trial % 3 == 0 else None
        end = random_points(rng, 1)[0] if trial % 4 == 0 else None
        order = order_segment(points, start, end)
        assert sorted(order) == list(range(len(points)))
        heuristic, best = cost(points, order, start, end), brute_force(points, start, end)
        assert heuristic <= best * 1.12 + 1e-9
        optimal += math.isclose(heuristic, best, rel_tol=1e-9, abs_tol=1e-9)
        trials += 1
    assert optimal / trials >= 0.95


def test_never_worse_than_greedy_or_input_order():
    rng = random.Random(7)
    for _ in range(50):
        points = random_points(rng, 12)
        start = random_points(rng, 1)[0]
        order = order_segment(points, start)
        assert cost(points, order, start) <= cost(points, list(range(12)), start) + 1e-9


def test_fixed_endpoints_shape_the_path():
    line = [(35.0, 139.0 + 0.01 * k) for k in range(5)]
    shuffled = [line[i] for i in (3, 0, 4, 1, 2)]
    east, west = (35.0, 139.10), (35.0, 138.90)
    forward = [shuffled[i] for i in order_segment(shuffled, start=west)]
    backward = [shuffled[i] for i in order_segment(shuffled, start=east)]
    assert forward == line and backward == line[::-1]
    assert [shuffled[i] for i in order_segment(shuffled, end=west)] == line[::-1]


def test_deterministic_with_ties():
    duplicates = [(35.0, 139.0)] * 4 + [(35.0, 139.01)] * 2
    assert order_segment(duplicates) == order_segment(list(duplicates))
    assert order_segment(duplicates) == [0, 1, 2, 3, 4, 5]


def test_fifty_points_is_fast_enough():
    import time
    points = random_points(random.Random(1), 50)
    started = time.perf_counter()
    order_segment(points)
    assert time.perf_counter() - started < 2


# ---- Day proposal with anchors -------------------------------------------

def stops(*specs):
    """spec: (item_id, longitude offset or None, anchored)."""
    return [Stop(item_id, None if offset is None else (35.0, 139.0 + 0.01 * offset), anchored)
            for item_id, offset, anchored in specs]


def test_reorders_movable_run_after_fixed_start():
    day = stops((1, 0, True), (2, 3, False), (3, 1, False), (4, 4, False), (5, 2, False))
    assert propose_order(day) == [1, 3, 5, 2, 4]


def test_anchors_keep_slots_and_nothing_crosses_them():
    # 3 is timed (anchored, located); 6 is unlocated (anchored, no point).
    day = stops((1, 0, True), (2, 2, False), (3, 5, True), (4, 9, False), (5, 6, False),
                (6, None, True), (7, 8, False), (8, 7, False))
    proposed = propose_order(day)
    assert [proposed.index(i) for i in (1, 3, 6)] == [0, 2, 5]
    assert set(proposed[3:5]) == {4, 5} and set(proposed[6:]) == {7, 8}
    # After the unlocated 6, the route continues from 4 (offset 9): 7 (8) then 8 (7).
    assert proposed == [1, 2, 3, 5, 4, 6, 7, 8]


def test_unlocated_anchor_is_transparent_to_distance():
    # Segment after the unlocated item 2 continues from item 1's point.
    day = stops((1, 0, True), (2, None, True), (3, 2, False), (4, 1, False))
    assert propose_order(day) == [1, 2, 4, 3]


def test_free_start_when_first_is_not_kept():
    day = stops((1, 2, False), (2, 0, False), (3, 1, False), (4, 3, False))
    assert propose_order(day) in ([2, 3, 1, 4], [4, 1, 3, 2])


def test_keeps_original_when_not_shorter():
    already = stops((1, 0, True), (2, 1, False), (3, 2, False))
    assert propose_order(already) == [1, 2, 3]
    all_anchored = stops((1, 3, True), (2, 0, True), (3, 2, True))
    assert propose_order(all_anchored) == [1, 2, 3]
    assert propose_order([]) == []


def test_never_longer_than_original():
    rng = random.Random(99)
    for _ in range(100):
        day = [Stop(i, (35 + rng.random(), 139 + rng.random()), rng.random() < 0.3)
               for i in range(rng.randint(1, 15))]
        proposed = propose_order(day)
        by_id = {stop.item_id: stop for stop in day}
        assert sorted(proposed) == [stop.item_id for stop in day]
        assert [i for i, s in zip(proposed, day) if s.anchored] == [s.item_id for s in day if s.anchored]
        assert path_km([by_id[i].point for i in proposed]) <= path_km([s.point for s in day]) + 1e-9


def test_unlocated_movable_stop_is_rejected():
    with pytest.raises(ValueError):
        propose_order([Stop(1, None, False)])
