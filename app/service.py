"""业务服务层：请求模型 -> 规范化问题 -> 求解 -> 响应模型。"""
from __future__ import annotations

from app.models import EdgeScore, SeatingRequest, SeatingResponse
from app.solver import SeatingProblem, cycle_edges, explain_infeasible, solve


def optimize(request: SeatingRequest) -> SeatingResponse:
    n = request.guests

    forbidden = frozenset(pair.normalized() for pair in request.forbidden_pairs)

    scores: dict[tuple[int, int], float] = {}
    for pair in request.pair_scores:
        scores[pair.normalized()] = pair.score

    fixed: dict[int, int] = {}
    for assignment in request.fixed_seats:
        fixed[assignment.seat] = assignment.guest

    problem = SeatingProblem(
        n=n, forbidden=forbidden, scores=scores, fixed=fixed
    )

    arrangement, total_score = solve(problem)
    if arrangement is None:
        return SeatingResponse(
            feasible=False,
            guests=n,
            reason=explain_infeasible(problem),
        )

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

    return SeatingResponse(
        feasible=True,
        guests=n,
        arrangement=arrangement,
        total_score=total_score,
        edge_scores=edge_scores,
    )
