"""算法层测试。"""
from __future__ import annotations

import itertools

import pytest

from app.solver import (
    SeatingProblem,
    cycle_edges,
    explain_infeasible,
    solve,
    solve_repair,
)


def _problem(n, forbidden=(), scores=(), fixed=None):
    return SeatingProblem(
        n=n,
        forbidden=frozenset(tuple(sorted(p)) for p in forbidden),
        scores={tuple(sorted((a, b))): s for a, b, s in scores},
        fixed=dict(fixed or {}),
    )


def _brute_force(problem: SeatingProblem):
    """枚举所有排列，返回 (最优排列, 最高分)；同分取字典序最小。"""
    n = problem.n
    fixed = problem.fixed
    best_key = None
    for perm in itertools.permutations(range(1, n + 1)):
        if any(perm[seat - 1] != guest for seat, guest in fixed.items()):
            continue
        edges = cycle_edges(list(perm))
        if any(problem.is_forbidden(a, b) for a, b in edges):
            continue
        total = sum(problem.score(a, b) for a, b in edges)
        key = (-total, perm)
        if best_key is None or key < best_key:
            best_key = key
    if best_key is None:
        return None
    return list(best_key[1]), -best_key[0]


def test_unconstrained_returns_identity_order():
    arrangement, total = solve(_problem(4))
    assert arrangement == [1, 2, 3, 4]
    assert total == 0.0


def test_tie_break_is_lexicographic_with_forbidden():
    # 禁邻 (3, 4)：所有可行排列得分相同（全 0），应取字典序最小
    arrangement, _ = solve(_problem(4, forbidden=[(3, 4)]))
    # [1,2,3,4]、[1,2,4,3] 中 3、4 均相邻；字典序最小的可行排列
    assert arrangement == [1, 3, 2, 4]


def test_maximize_total_score_including_closing_edge():
    # 闭合边 (1,4) 给高分，必须被选中
    prob = _problem(
        4,
        scores=[(1, 2, 10), (3, 4, 10), (1, 4, 100)],
    )
    arrangement, total = solve(prob)
    assert total == 120
    edges = set(cycle_edges(arrangement))
    assert {(1, 2), (3, 4), (1, 4)} <= edges


def test_fixed_seats_respected():
    prob = _problem(5, scores=[(2, 4, 5)], fixed={1: 2, 3: 4})
    arrangement, total = solve(prob)
    assert arrangement[0] == 2
    assert arrangement[2] == 4
    # 2 与 4 可在圈上相邻以拿 5 分（座位 1 与 3 不相邻，需视完整排列）
    assert total >= 0


def test_n2_single_edge_counted_once():
    prob = _problem(2, scores=[(1, 2, 7)])
    arrangement, total = solve(prob)
    assert sorted(arrangement) == [1, 2]
    assert total == 7


def test_n2_forbidden_infeasible():
    prob = _problem(2, forbidden=[(1, 2)])
    arrangement, _ = solve(prob)
    assert arrangement is None
    assert "互为禁邻" in explain_infeasible(prob)


def test_forced_forbidden_by_fixed_seats():
    prob = _problem(4, forbidden=[(1, 2)], fixed={1: 1, 2: 2})
    arrangement, _ = solve(prob)
    assert arrangement is None
    reason = explain_infeasible(prob)
    assert "固定座位迫使" in reason


def test_completely_isolated_guest():
    prob = _problem(4, forbidden=[(1, 2), (1, 3), (1, 4)])
    arrangement, _ = solve(prob)
    assert arrangement is None
    assert "宾客 1" in explain_infeasible(prob)


@pytest.mark.parametrize("n", [2, 3, 4, 5, 6])
def test_matches_brute_force_random(n):
    import random

    rng = random.Random(20260923 + n)
    guests = list(range(1, n + 1))
    all_pairs = list(itertools.combinations(guests, 2))
    for trial in range(40):
        rng.shuffle(all_pairs)
        forbidden = set(all_pairs[: rng.randrange(0, len(all_pairs) // 2 + 1)])
        scored = {
            p: rng.randint(-5, 10)
            for p in all_pairs
            if p not in forbidden and rng.random() < 0.7
        }
        fixed = {}
        if rng.random() < 0.6:
            seats = rng.sample(guests, rng.randint(1, min(3, n)))
            people = rng.sample(guests, len(seats))
            fixed = dict(zip(seats, people))
        prob = SeatingProblem(
            n=n,
            forbidden=frozenset(forbidden),
            scores=dict(scored),
            fixed=fixed,
        )
        got = solve(prob)
        expected = _brute_force(prob)
        if expected is None:
            assert got[0] is None, (n, trial, prob)
        else:
            exp_arr, exp_score = expected
            assert got[0] == exp_arr, (n, trial, prob, got, exp_arr)
            assert got[1] == pytest.approx(exp_score)


def test_n12_runs_quickly_unconstrained():
    import time

    prob = SeatingProblem(n=12, forbidden=frozenset(), scores={})
    start = time.perf_counter()
    arrangement, total = solve(prob)
    elapsed = time.perf_counter() - start
    assert arrangement == list(range(1, 13))
    assert total == 0.0
    assert elapsed < 5.0


def test_n12_with_constraints_runs_quickly():
    import random
    import time

    rng = random.Random(42)
    pairs = list(itertools.combinations(range(1, 13), 2))
    rng.shuffle(pairs)
    scores = {p: rng.randint(0, 20) for p in pairs[:30]}
    forbidden = set(pairs[30:36])
    prob = SeatingProblem(n=12, forbidden=frozenset(forbidden), scores=scores)
    start = time.perf_counter()
    arrangement, total = solve(prob)
    elapsed = time.perf_counter() - start
    assert arrangement is not None
    assert elapsed < 5.0
    edges = cycle_edges(arrangement)
    assert all(not prob.is_forbidden(a, b) for a, b in edges)
    assert total == pytest.approx(sum(prob.score(a, b) for a, b in edges))


def _brute_force_repair(problem: SeatingProblem, original: list[int]):
    """枚举所有排列，按 (换座人数, -得分, 字典序) 取最优。"""
    n = problem.n
    fixed = problem.fixed
    best_key = None
    for perm in itertools.permutations(range(1, n + 1)):
        if any(perm[seat - 1] != guest for seat, guest in fixed.items()):
            continue
        edges = cycle_edges(list(perm))
        if any(problem.is_forbidden(a, b) for a, b in edges):
            continue
        total = sum(problem.score(a, b) for a, b in edges)
        changed = sum(1 for seat in range(n) if perm[seat] != original[seat])
        key = (changed, -total, perm)
        if best_key is None or key < best_key:
            best_key = key
    if best_key is None:
        return None
    return list(best_key[2]), -best_key[1], best_key[0]


def test_repair_keeps_feasible_original_unchanged():
    # 原座次本身满足新约束且得分最优时，零换座直接保留
    prob = _problem(
        4,
        scores=[(1, 2, 10), (3, 4, 10), (1, 4, 100)],
    )
    original = [1, 2, 3, 4]
    arrangement, total, changed = solve_repair(prob, original)
    assert arrangement == [1, 2, 3, 4]
    assert changed == 0
    assert total == 120


def test_repair_minimizes_moved_guests_before_score():
    # 新增禁邻 (3,4)：[1,2,3,4] 不再可行。
    # 只需换 2 人即可修复，不应为更高得分换 4 人。
    prob = _problem(
        4,
        forbidden=[(3, 4)],
        scores=[(1, 4, 100)],
    )
    original = [1, 2, 3, 4]
    arrangement, total, changed = solve_repair(prob, original)
    assert changed == 2
    # 保留座位 1、4（宾客 1、4 不动），2/3 号位放 2、3
    assert arrangement == [1, 3, 2, 4]
    edges = cycle_edges(arrangement)
    assert (3, 4) not in edges
    # 首尾闭合边 (1,4) 仍在，得分 100；同分且同换座数时字典序最小
    assert total == 100


def test_repair_original_may_violate_new_fixed_seats():
    # 新增固定座位：3 号位必须坐 4，原座次不满足该约束也允许传入
    prob = _problem(4, fixed={3: 4})
    original = [1, 2, 3, 4]
    arrangement, _, changed = solve_repair(prob, original)
    assert arrangement[2] == 4
    assert changed == 2  # 3、4 互换是最少换座
    assert arrangement == [1, 2, 4, 3]


def test_repair_score_breaks_tie_among_minimal_moves():
    # n=5，新增禁邻 (1,2)，原座次 [1,2,3,4,5] 失效。
    # 同为 2 换时：字典序更小的 [1,3,2,4,5] 得 0 分，
    # [1,4,3,2,5] 含边 (2,5) 得 9 分，得分优先于字典序。
    prob = _problem(
        5,
        forbidden=[(1, 2)],
        scores=[(2, 5, 9)],
    )
    original = [1, 2, 3, 4, 5]
    arrangement, total, changed = solve_repair(prob, original)
    assert changed == 2
    assert arrangement == [1, 4, 3, 2, 5]
    assert total == 9


def test_repair_n2_single_edge_and_infeasible():
    prob = _problem(2, scores=[(1, 2, 7)])
    arrangement, total, changed = solve_repair(prob, [2, 1])
    assert changed == 0  # 原座次可行（圆排列等价），零换座
    assert total == 7  # 两人只计一条边

    infeasible = _problem(2, forbidden=[(1, 2)])
    assert solve_repair(infeasible, [1, 2]) is None


@pytest.mark.parametrize("n", [2, 3, 4, 5, 6])
def test_repair_matches_brute_force_random(n):
    import random

    rng = random.Random(778899 + n)
    guests = list(range(1, n + 1))
    all_pairs = list(itertools.combinations(guests, 2))
    for trial in range(40):
        rng.shuffle(all_pairs)
        forbidden = set(all_pairs[: rng.randrange(0, len(all_pairs) // 2 + 1)])
        scored = {
            p: rng.randint(-5, 10)
            for p in all_pairs
            if p not in forbidden and rng.random() < 0.7
        }
        fixed = {}
        if rng.random() < 0.6:
            seats = rng.sample(guests, rng.randint(1, min(3, n)))
            people = rng.sample(guests, len(seats))
            fixed = dict(zip(seats, people))
        # 原座次随机产生，刻意不要求满足新约束
        original = guests[:]
        rng.shuffle(original)
        prob = SeatingProblem(
            n=n,
            forbidden=frozenset(forbidden),
            scores=dict(scored),
            fixed=fixed,
        )
        got = solve_repair(prob, original)
        expected = _brute_force_repair(prob, original)
        if expected is None:
            assert got is None, (n, trial, prob, original)
        else:
            exp_arr, exp_score, exp_changed = expected
            assert got[0] == exp_arr, (n, trial, prob, original, got, expected)
            assert got[1] == pytest.approx(exp_score)
            assert got[2] == exp_changed


def test_repair_n12_runs_quickly():
    import random
    import time

    rng = random.Random(2024)
    pairs = list(itertools.combinations(range(1, 13), 2))
    rng.shuffle(pairs)
    scores = {p: rng.randint(0, 20) for p in pairs[:30]}
    forbidden = set(pairs[30:36])
    prob = SeatingProblem(n=12, forbidden=frozenset(forbidden), scores=scores)
    original = list(range(1, 13))
    rng.shuffle(original)
    start = time.perf_counter()
    result = solve_repair(prob, original)
    elapsed = time.perf_counter() - start
    assert result is not None
    assert elapsed < 5.0
    arrangement, total, changed = result
    edges = cycle_edges(arrangement)
    assert all(not prob.is_forbidden(a, b) for a, b in edges)
    assert total == pytest.approx(sum(prob.score(a, b) for a, b in edges))
    assert changed == sum(
        1 for seat in range(12) if arrangement[seat] != original[seat]
    )
