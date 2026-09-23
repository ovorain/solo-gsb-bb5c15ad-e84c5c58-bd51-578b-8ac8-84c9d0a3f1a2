"""请求/响应 Pydantic 模型与入参校验。"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class Pair(BaseModel):
    """一对宾客。"""

    a: int = Field(..., description="宾客编号（1 起）", ge=1)
    b: int = Field(..., description="宾客编号（1 起）", ge=1)

    def normalized(self) -> tuple[int, int]:
        return (self.a, self.b) if self.a <= self.b else (self.b, self.a)


class ForbiddenPair(Pair):
    """禁邻宾客对。"""


class PairScore(Pair):
    """相邻宾客对及其得分。"""

    score: float = Field(..., description="二人相邻时的得分")


class FixedSeat(BaseModel):
    """固定座位指派。"""

    seat: int = Field(..., description="座位号（1 起）", ge=1)
    guest: int = Field(..., description="宾客编号（1 起）", ge=1)


class SeatingRequest(BaseModel):
    """座位优化请求。"""

    guests: int = Field(
        ..., ge=2, le=12, description="宾客人数（每人一席），取值 2~12"
    )
    forbidden_pairs: list[ForbiddenPair] = Field(
        default_factory=list, description="禁止相邻的宾客对"
    )
    pair_scores: list[PairScore] = Field(
        default_factory=list, description="宾客对相邻得分；未配置按 0 分计"
    )
    fixed_seats: list[FixedSeat] = Field(
        default_factory=list, description="固定座位指派"
    )

    @model_validator(mode="after")
    def _validate_references(self) -> "SeatingRequest":
        n = self.guests

        def _check_pair(pair: Pair, label: str) -> None:
            if pair.a == pair.b:
                raise ValueError(f"{label} 不能是同一位宾客: ({pair.a}, {pair.b})")
            if pair.a > n or pair.b > n:
                raise ValueError(
                    f"{label} ({pair.a}, {pair.b}) 引用了不存在的宾客，"
                    f"宾客编号须在 1~{n} 之间"
                )

        for pair in self.forbidden_pairs:
            _check_pair(pair, "禁邻宾客对")
        for pair in self.pair_scores:
            _check_pair(pair, "得分宾客对")

        # 同一对宾客既被禁邻又配置得分：约束语义冲突
        forbidden_keys = {p.normalized() for p in self.forbidden_pairs}
        scored_keys = [p.normalized() for p in self.pair_scores]
        overlap = forbidden_keys.intersection(scored_keys)
        if overlap:
            pair = sorted(overlap)[0]
            raise ValueError(
                f"宾客对 ({pair[0]}, {pair[1]}) 同时出现在禁邻列表和得分列表中，"
                "禁邻对不能配置相邻得分"
            )
        if len(scored_keys) != len(set(scored_keys)):
            raise ValueError("得分宾客对重复配置，每对宾客至多配置一个得分")

        for assignment in self.fixed_seats:
            if assignment.seat > n:
                raise ValueError(
                    f"固定座位号 {assignment.seat} 超出范围，座位号须在 1~{n} 之间"
                )
            if assignment.guest > n:
                raise ValueError(
                    f"固定宾客编号 {assignment.guest} 超出范围，"
                    f"宾客编号须在 1~{n} 之间"
                )

        seat_owners: dict[int, int] = {}
        for assignment in self.fixed_seats:
            owner = seat_owners.get(assignment.seat)
            if owner is not None and owner != assignment.guest:
                raise ValueError(
                    f"座位 {assignment.seat} 被同时固定给宾客 {owner} 和 "
                    f"宾客 {assignment.guest}"
                )
            seat_owners[assignment.seat] = assignment.guest

        guest_seats: dict[int, int] = {}
        for assignment in self.fixed_seats:
            seat = guest_seats.get(assignment.guest)
            if seat is not None and seat != assignment.seat:
                raise ValueError(
                    f"宾客 {assignment.guest} 被同时固定到 {seat} 号和 "
                    f"{assignment.seat} 号座位"
                )
            guest_seats[assignment.guest] = assignment.seat

        return self


class EdgeScore(BaseModel):
    """圆桌邻接边上的得分明细。"""

    seats: tuple[int, int] = Field(..., description="该边对应的两个座位号")
    guests: tuple[int, int] = Field(..., description="该边上的两位宾客")
    score: float = Field(..., description="该邻接边得分")


class SeatingResponse(BaseModel):
    """座位优化结果。"""

    feasible: bool = Field(..., description="是否存在可行排列")
    guests: int = Field(..., description="宾客人数")
    arrangement: list[int] = Field(
        default_factory=list,
        description="从 1 号位起的宾客编号序列；无可行排列时为空",
    )
    total_score: float = Field(0.0, description="整圈相邻总得分")
    edge_scores: list[EdgeScore] = Field(
        default_factory=list, description="各邻接边得分明细"
    )
    reason: str | None = Field(
        None, description="无可行排列时的原因说明；可行时为 null"
    )
