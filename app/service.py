"""业务服务层：请求模型 -> 规范化问题 -> 求解 -> 响应模型。"""
from __future__ import annotations

from app.models import (
    EdgeScore,
    RepairSeatingRequest,
    RepairSeatingResponse,
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


def _build_problem(request: SeatingRequest) -> SeatingProblem:
    forbidden = frozenset(pair.normalized() for pair in request.forbidden_pairs)

    scores: dict[tuple[int, int], float] = {}
    for pair in request.pair_scores:
        scores[pair.normalized()] = pair.score

    fixed: dict[int, int] = {}
    for assignment in request.fixed_seats:
        fixed[assignment.seat] = assignment.guest

    return SeatingProblem(n=request.guests, forbidden=forbidden, scores=scores,
                          fixed=fixed)


def _build_edge_scores(
    arrangement: list[int], problem: SeatingProblem
) -> list[EdgeScore]:
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
    problem = _build_problem(request)

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
        edge_scores=_build_edge_scores(arrangement, problem),
    )


def repair(request: RepairSeatingRequest) -> RepairSeatingResponse:
    n = request.guests
    problem = _build_problem(request)
    original = request.original_arrangement

    result = solve_repair(problem, original)
    if result is None:
        return RepairSeatingResponse(
            feasible=False,
            guests=n,
            reason=explain_infeasible(problem),
        )

    arrangement, total_score, changed_count = result
    changed_seats = [
        seat
        for seat, (new_guest, old_guest) in enumerate(
            zip(arrangement, original), start=1
        )
        if new_guest != old_guest
    ]

    return RepairSeatingResponse(
        feasible=True,
        guests=n,
        arrangement=arrangement,
        total_score=total_score,
        edge_scores=_build_edge_scores(arrangement, problem),
        changed_count=changed_count,
        changed_seats=changed_seats,
    )
