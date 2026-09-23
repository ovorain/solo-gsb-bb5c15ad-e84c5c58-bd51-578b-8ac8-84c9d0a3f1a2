"""业务服务层：请求模型 -> 规范化问题 -> 求解 -> 响应模型。"""
from __future__ import annotations

from app.models import (
    EdgeScore,
    RepairRequest,
    RepairResponse,
    SeatingRequest,
    SeatingResponse,
)
from app.solver import (
    SeatingProblem,
    cycle_edges,
    explain_infeasible,
    solve,
    solve_repair,
)


def build_problem(request: SeatingRequest) -> SeatingProblem:
    """把请求规范化为算法层的问题描述。"""
    forbidden = frozenset(pair.normalized() for pair in request.forbidden_pairs)

    scores: dict[tuple[int, int], float] = {}
    for pair in request.pair_scores:
        scores[pair.normalized()] = pair.score

    fixed: dict[int, int] = {}
    for assignment in request.fixed_seats:
        fixed[assignment.seat] = assignment.guest

    return SeatingProblem(
        n=request.guests, forbidden=forbidden, scores=scores, fixed=fixed
    )


def build_edge_scores(
    problem: SeatingProblem, arrangement: list[int]
) -> list[EdgeScore]:
    """组装整圈各邻接边的得分明细（首尾边同样包含；n == 2 只一条）。"""
    guest_to_seat = {guest: seat for seat, guest in enumerate(arrangement, start=1)}
    edge_scores: list[EdgeScore] = []
    for a, b in cycle_edges(arrangement):
        seat_a, seat_b = guest_to_seat[a], guest_to_seat[b]
        if seat_a > seat_b:
            seat_a, seat_b = seat_b, seat_a
        edge_scores.append(
            EdgeScore(
                seats=(seat_a, seat_b),
                guests=(a, b),
                score=problem.score(a, b),
            )
        )
    return edge_scores


def optimize(request: SeatingRequest) -> SeatingResponse:
    n = request.guests
    problem = build_problem(request)

    arrangement, total_score = solve(problem)
    if arrangement is None:
        return SeatingResponse(
            feasible=False,
            guests=n,
            reason=explain_infeasible(problem),
        )

    return SeatingResponse(
        feasible=True,
        guests=n,
        arrangement=arrangement,
        total_score=total_score,
        edge_scores=build_edge_scores(problem, arrangement),
    )


def repair(request: RepairRequest) -> RepairResponse:
    """临时调整约束后修复座次：先最少换座，再最高得分，再字典序最小。"""
    n = request.guests
    problem = build_problem(request)
    original = request.original_arrangement

    arrangement, total_score, moved = solve_repair(problem, original)
    if arrangement is None:
        return RepairResponse(
            feasible=False,
            guests=n,
            reason=explain_infeasible(problem),
        )

    changed_seats = [
        seat
        for seat, guest in enumerate(arrangement, start=1)
        if guest != original[seat - 1]
    ]

    # 排列为双射：变动座位数与被移动宾客数必然相等
    return RepairResponse(
        feasible=True,
        guests=n,
        arrangement=arrangement,
        total_score=total_score,
        edge_scores=build_edge_scores(problem, arrangement),
        moved_guests=moved,
        changed_seats=changed_seats,
    )
