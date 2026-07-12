import random
import pytest

from app.services.matching_service import solve, MatchingError


def check_valid(participants, result, allow_same=False):
    house = dict(participants)
    givers = set(result.keys())
    receivers = set(result.values())
    ids = {p[0] for p in participants}
    assert givers == ids, "everyone gives exactly once"
    assert receivers == ids, "everyone receives exactly once (no duplicates)"
    for g, r in result.items():
        assert g != r, "no self-match"
        if not allow_same:
            assert house[g] != house[r], "no same-household match"


def test_basic_three_people():
    parts = [(1, 10), (2, 20), (3, 30)]
    check_valid(parts, solve(parts))


def test_couples_never_match_each_other():
    parts = [(1, 10), (2, 10), (3, 20), (4, 20), (5, 30), (6, 30)]
    for _ in range(200):
        check_valid(parts, solve(parts))


def test_impossible_configuration_raises():
    # 3 of 4 people in one household, cross-household required -> impossible
    parts = [(1, 10), (2, 10), (3, 10), (4, 20)]
    with pytest.raises(MatchingError):
        solve(parts)


def test_same_household_allowed_relaxes_constraint():
    parts = [(1, 10), (2, 10), (3, 10)]
    check_valid(parts, solve(parts, allow_same_household=True), allow_same=True)


def test_fuzz_1000_runs_50_people():
    rng = random.Random(42)
    for _ in range(1000):
        n = rng.randint(5, 50)
        parts = [(i, rng.randint(1, max(2, n // 3))) for i in range(1, n + 1)]
        counts = {}
        for _, hh in parts:
            counts[hh] = counts.get(hh, 0) + 1
        if max(counts.values()) > n // 2:
            with pytest.raises(MatchingError):
                solve(parts)
        else:
            check_valid(parts, solve(parts))
