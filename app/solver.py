"""圆桌座位优化核心算法。

问题描述
--------
n 位宾客（2 <= n <= 12）围坐圆桌，座位从 1 开始顺次编号，
首尾两号座位相邻。需要在满足以下约束时最大化整圈相邻得分：

* 禁邻宾客对不能相邻（含首尾）；
* 固定座位的宾客必须坐在指定座位；
* 宾客对相邻得分未配置时按 0 分计；
* 总得分相同时，取从 1 号位起宾客编号序列字典序最小的排列。

实现
----
采用位掩码 DP：状态 ``(mask, prev, first)`` 表示
``mask`` 中的宾客已安排在最前面的 ``popcount(mask)`` 个座位上、
首座宾客为 ``first``、末座宾客为 ``prev`` 时的最优值。
按宾客编号升序枚举即可让元组值 ``(score, 后续序列)`` 的字典序比较
自然落实同分取字典序最小排列的要求。
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 浮点分值相等判定容差
_EPS = 1e-9


@dataclass(frozen=True)
class SeatingProblem:
    """一次座位优化问题的规范化输入。"""

    n: int
    forbidden: frozenset[tuple[int, int]]
    scores: dict[tuple[int, int], float]
    fixed: dict[int, int] = field(default_factory=dict)  # seat -> guest

    def score(self, a: int, b: int) -> float:
        if a == b:
            return 0.0
        return self.scores.get((a, b) if a < b else (b, a), 0.0)

    def is_forbidden(self, a: int, b: int) -> bool:
        if a == b:
            return True
        key = (a, b) if a < b else (b, a)
        return key in self.forbidden


def solve(problem: SeatingProblem) -> tuple[list[int] | None, float]:
    """求最优座位排列。

    返回 ``(排列, 总得分)``；无可行排列时返回 ``(None, 0.0)``。
    排列中第 i 个元素表示座位 ``i + 1`` 上的宾客编号。
    """
    n = problem.n
    fixed = problem.fixed
    full = (1 << n) - 1
    # memo[(mask, prev, first)] = (score, 从下一座位开始的后缀序列)
    memo: dict[tuple[int, int, int], tuple[float, tuple[int, ...]]] = {}

    def candidates(mask: int, seat: int) -> list[int]:
        """座位 ``seat``（1 起）在状态 ``mask`` 下允许放置的宾客（升序）。"""
        required = fixed.get(seat)
        if required is not None:
            bit = 1 << (required - 1)
            return [required] if not (mask & bit) else []
        return [g for g in range(1, n + 1) if not (mask & (1 << (g - 1)))]

    def dp(mask: int, prev: int, first: int) -> tuple[float, tuple[int, ...]] | None:
        key = (mask, prev, first)
        if key in memo:
            return memo[key]

        seat = mask.bit_count() + 1

        if mask == full:
            # 闭合首尾边。n == 2 时首与尾之间仍是同一条邻接边，
            # 已在入座时计过，不重复计分。
            if problem.is_forbidden(prev, first):
                outcome = None
            else:
                close_score = 0.0 if n == 2 else problem.score(prev, first)
                outcome = (close_score, ())
        else:
            outcome = None
            for guest in candidates(mask, seat):
                if problem.is_forbidden(prev, guest):
                    continue
                tail = dp(mask | (1 << (guest - 1)), guest, first)
                if tail is None:
                    continue
                total = problem.score(prev, guest) + tail[0]
                candidate = (total, (guest,) + tail[1])
                if outcome is None or _better(candidate, outcome):
                    outcome = candidate

        memo[key] = outcome
        return outcome

    best: tuple[float, tuple[int, ...]] | None = None
    required_first = fixed.get(1)
    first_guests = (
        [required_first] if required_first is not None else list(range(1, n + 1))
    )
    for first in first_guests:
        rest = dp(1 << (first - 1), first, first)
        if rest is None:
            continue
        candidate = (rest[0], (first,) + rest[1])
        if best is None or _better(candidate, best):
            best = candidate

    if best is None:
        return None, 0.0
    return list(best[1]), best[0]


def _better(
    candidate: tuple[float, tuple[int, ...]],
    current: tuple[float, tuple[int, ...]],
) -> bool:
    """candidate 是否优于 current：得分更高；同分则座位序列字典序更小。"""
    if candidate[0] > current[0] + _EPS:
        return True
    if candidate[0] < current[0] - _EPS:
        return False
    return candidate[1] < current[1]


def explain_infeasible(problem: SeatingProblem) -> str:
    """在无可行排列时返回人类可读的原因说明。"""
    n = problem.n
    fixed = problem.fixed

    # 固定座位唯一冲突（正常在入参校验阶段已拦截，此处兜底）
    guests_fixed: dict[int, int] = {}
    for seat, guest in fixed.items():
        if guest in guests_fixed:
            return (
                f"宾客 {guest} 被同时固定到 {guests_fixed[guest]} 号和 {seat} 号座位，"
                "固定座位约束自相矛盾"
            )
        guests_fixed[guest] = seat

    # 固定座位宾客之间被迫相邻（含首尾）
    if fixed:
        for seat in range(1, n + 1):
            a = fixed.get(seat)
            b = fixed.get(1 if seat == n else seat + 1)
            if a is not None and b is not None and problem.is_forbidden(a, b):
                other_seat = 1 if seat == n else seat + 1
                return (
                    f"固定座位迫使宾客 {a}（{seat} 号位）与宾客 {b}"
                    f"（{other_seat} 号位）相邻，但二人互为禁邻"
                )

    # 可相邻宾客数量不足以支撑圆桌上的两个邻座
    # （n == 2 时圆桌只提供一个不同的邻居）
    min_neighbors = 1 if n == 2 else 2
    for guest in range(1, n + 1):
        allowed = [
            other
            for other in range(1, n + 1)
            if other != guest and not problem.is_forbidden(guest, other)
        ]
        if len(allowed) < min_neighbors:
            forbidden_partners = [
                other
                for other in range(1, n + 1)
                if other != guest and problem.is_forbidden(guest, other)
            ]
            return (
                f"宾客 {guest} 与其余所有宾客"
                f"（{', '.join(map(str, forbidden_partners))}）互为禁邻，"
                "圆桌上无法为其安排任何邻座"
                if n == 2
                else f"宾客 {guest} 的可相邻宾客不足 2 人"
                f"（与宾客 {', '.join(map(str, forbidden_partners))} 互为禁邻），"
                "无法同时满足圆桌两侧的邻座要求"
            )

    # 固定宾客被禁邻包围：两个邻座方向上的可选宾客凑不齐
    if fixed and n >= 3:
        for seat, guest in fixed.items():
            options: list[list[int]] = []
            for neighbor_seat in (_left_seat(seat, n), _right_seat(seat, n)):
                forced = fixed.get(neighbor_seat)
                if forced is not None:
                    pool = (
                        []
                        if forced == guest or problem.is_forbidden(guest, forced)
                        else [forced]
                    )
                else:
                    pool = [
                        other
                        for other in range(1, n + 1)
                        if other != guest and not problem.is_forbidden(guest, other)
                    ]
                options.append(pool)
            left_pool, right_pool = options
            # 两侧各需一位不同宾客
            feasible_sides = any(
                left != right for left in left_pool for right in right_pool
            )
            if not feasible_sides:
                return (
                    f"固定在 {seat} 号位的宾客 {guest} 受固定座位与禁邻约束限制，"
                    "无法同时安排两个不互斥的左右邻座"
                )

    return "在同时满足禁邻与固定座位约束的前提下不存在可行排列"


def _left_seat(seat: int, n: int) -> int:
    return n if seat == 1 else seat - 1


def _right_seat(seat: int, n: int) -> int:
    return 1 if seat == n else seat + 1


def cycle_edges(arrangement: list[int]) -> list[tuple[int, int]]:
    """返回排列对应的圆桌邻接边（去重，n == 2 时只有一条）。"""
    n = len(arrangement)
    edges: list[tuple[int, int]] = []
    for i in range(n):
        a, b = arrangement[i], arrangement[(i + 1) % n]
        edge = (a, b) if a < b else (b, a)
        if edge not in edges:
            edges.append(edge)
    return edges
