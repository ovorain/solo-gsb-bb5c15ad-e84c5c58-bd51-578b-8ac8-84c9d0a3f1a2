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
    """枚举所有排列，返回 (最优排列, 最高分, 最少换座数)。

    排序：换座人数升序 -> 得分降序 -> 排列字典序升序。
    """
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
        moved = sum(1 for i, guest in enumerate(perm) if guest != original[i])
        key = (moved, -total, perm)
        if best_key is None or key < best_key:
            best_key = key
    if best_key is None:
        return None
    return list(best_key[2]), -best_key[1], best_key[0]


def test_repair_keeps_feasible_original_unchanged():
    # 原座次已满足新约束时零换座原样返回，即便存在得分更高的其他排列
    prob = _problem(4, scores=[(1, 2, 100), (3, 4, 100)])
    original = [4, 3, 2, 1]
    arrangement, total, moved = solve_repair(prob, original)
    assert arrangement == original
    assert moved == 0
    assert total == pytest.approx(sum(prob.score(a, b) for a, b in cycle_edges(original)))


def test_repair_minimizes_moved_then_score_then_lex():
    # 新禁邻 (3, 4)：原 [4,3,2,1] 中 3、4 相邻；
    # 换 2 人可行，所有可行结果同分 0，取字典序最小
    prob = _problem(4, forbidden=[(3, 4)])
    arrangement, total, moved = solve_repair(prob, [4, 3, 2, 1])
    assert moved == 2
    assert arrangement == [1, 3, 2, 4]
    assert total == 0.0
    # 变动座位恰好是换座宾客所在的座位
    assert [s for s, g in enumerate(arrangement, start=1) if g != [4, 3, 2, 1][s - 1]] == [1, 4]


def test_repair_prefers_higher_score_among_minimal_moves():
    # 原 [1,2,3,4] 新增禁邻 (2,3)：仅换 2 人的修复有多种；
    # 给 (1,3) 配 9 分使包含该边的排列在最少换座集合中胜出
    prob = _problem(4, forbidden=[(2, 3)], scores=[(1, 3, 9)])
    arrangement, total, moved = solve_repair(prob, [1, 2, 3, 4])
    assert moved == 2
    assert total == 9.0
    # [1,2,4,3] 含边 (1,3)（首尾闭合）：换座最少、得分最高、字典序最小
    assert arrangement == [1, 2, 4, 3]


def test_repair_original_may_violate_fixed_seats():
    # 原座次允许不符合新约束：新固定 seat2=3，原 [1,2,3] 中 seat2 是 2
    prob = _problem(3, fixed={2: 3})
    arrangement, _, moved = solve_repair(prob, [1, 2, 3])
    assert arrangement[1] == 3
    assert moved == 2  # [1,3,2]：2 号、3 号位变动


def test_repair_n2_single_edge_and_zero_moves_on_tie():
    prob = _problem(2, scores=[(1, 2, 7)])
    arrangement, total, moved = solve_repair(prob, [2, 1])
    assert sorted(arrangement) == [1, 2]
    assert total == 7  # 两人圆桌只计一条邻接边
    assert moved == 0  # 两种排列同一条边同分：保留原座次


def test_repair_infeasible():
    prob = _problem(2, forbidden=[(1, 2)])
    arrangement, _, moved = solve_repair(prob, [1, 2])
    assert arrangement is None
    assert moved == 0


@pytest.mark.parametrize("n", [2, 3, 4, 5, 6])
def test_repair_matches_brute_force_random(n):
    import random

    rng = random.Random(998877 + n)
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
        # 原座次是任意完整排列（可能违反新约束）
        original = list(rng.sample(guests, n))
        prob = SeatingProblem(
            n=n,
            forbidden=frozenset(forbidden),
            scores=dict(scored),
            fixed=fixed,
        )
        got = solve_repair(prob, original)
        expected = _brute_force_repair(prob, original)
        if expected is None:
            assert got[0] is None, (n, trial, prob)
            assert got[2] == 0
        else:
            exp_arr, exp_score, exp_moved = expected
            assert got[0] == exp_arr, (n, trial, prob, got, exp_arr)
            assert got[1] == pytest.approx(exp_score)
            assert got[2] == exp_moved


def test_repair_n12_runs_quickly():
    import random
    import time

    rng = random.Random(42)
    pairs = list(itertools.combinations(range(1, 13), 2))
    rng.shuffle(pairs)
    scores = {p: rng.randint(0, 20) for p in pairs[:30]}
    forbidden = set(pairs[30:36])
    prob = SeatingProblem(n=12, forbidden=frozenset(forbidden), scores=scores)
    original = list(range(1, 13))
    rng.shuffle(original)
    start = time.perf_counter()
    arrangement, total, moved = solve_repair(prob, original)
    elapsed = time.perf_counter() - start
    assert arrangement is not None
    assert elapsed < 5.0
    edges = cycle_edges(arrangement)
    assert all(not prob.is_forbidden(a, b) for a, b in edges)
    assert total == pytest.approx(sum(prob.score(a, b) for a, b in edges))
    assert moved == sum(
        1 for i, guest in enumerate(arrangement) if guest != original[i]
    )
