"""API 层测试。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_optimize_basic():
    response = client.post(
        "/api/v1/seating/optimize",
        json={
            "guests": 4,
            "pair_scores": [
                {"a": 1, "b": 2, "score": 10},
                {"a": 3, "b": 4, "score": 10},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["feasible"] is True
    assert data["arrangement"] == [1, 2, 3, 4]
    assert data["total_score"] == 20
    assert len(data["edge_scores"]) == 4
    assert data["reason"] is None


def test_optimize_with_fixed_and_forbidden():
    response = client.post(
        "/api/v1/seating/optimize",
        json={
            "guests": 5,
            "forbidden_pairs": [{"a": 1, "b": 2}],
            "fixed_seats": [{"seat": 1, "guest": 3}],
        },
    )
    data = response.json()
    assert data["feasible"] is True
    assert data["arrangement"][0] == 3
    edges = [set(e["guests"]) for e in data["edge_scores"]]
    assert {1, 2} not in edges


def test_infeasible_returns_reason():
    response = client.post(
        "/api/v1/seating/optimize",
        json={
            "guests": 2,
            "forbidden_pairs": [{"a": 1, "b": 2}],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["feasible"] is False
    assert data["arrangement"] == []
    assert data["reason"]


def test_forced_forbidden_fixed_seats():
    response = client.post(
        "/api/v1/seating/optimize",
        json={
            "guests": 4,
            "forbidden_pairs": [{"a": 1, "b": 2}],
            "fixed_seats": [
                {"seat": 1, "guest": 1},
                {"seat": 2, "guest": 2},
            ],
        },
    )
    data = response.json()
    assert data["feasible"] is False
    assert "固定座位迫使" in data["reason"]


def test_guests_out_of_range_rejected():
    response = client.post(
        "/api/v1/seating/optimize",
        json={"guests": 3, "forbidden_pairs": [{"a": 1, "b": 4}]},
    )
    assert response.status_code == 422


def test_guests_count_bounds():
    response = client.post("/api/v1/seating/optimize", json={"guests": 13})
    assert response.status_code == 422
    response = client.post("/api/v1/seating/optimize", json={"guests": 1})
    assert response.status_code == 422


def test_self_pair_rejected():
    response = client.post(
        "/api/v1/seating/optimize",
        json={"guests": 3, "forbidden_pairs": [{"a": 2, "b": 2}]},
    )
    assert response.status_code == 422


def test_conflicting_forbidden_and_score_rejected():
    response = client.post(
        "/api/v1/seating/optimize",
        json={
            "guests": 3,
            "forbidden_pairs": [{"a": 1, "b": 2}],
            "pair_scores": [{"a": 2, "b": 1, "score": 5}],
        },
    )
    assert response.status_code == 422


def test_duplicate_guest_fixed_to_two_seats_rejected():
    response = client.post(
        "/api/v1/seating/optimize",
        json={
            "guests": 4,
            "fixed_seats": [
                {"seat": 1, "guest": 2},
                {"seat": 3, "guest": 2},
            ],
        },
    )
    assert response.status_code == 422


def test_opening_docs():
    response = client.get("/docs")
    assert response.status_code == 200


def test_repair_keeps_original_when_still_feasible():
    response = client.post(
        "/api/v1/seating/repair",
        json={
            "guests": 4,
            "pair_scores": [{"a": 1, "b": 2, "score": 10}],
            "original_arrangement": [4, 3, 2, 1],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["feasible"] is True
    assert data["arrangement"] == [4, 3, 2, 1]
    assert data["moved_guests"] == 0
    assert data["changed_seats"] == []
    assert len(data["edge_scores"]) == 4
    assert data["reason"] is None


def test_repair_minimal_change_with_new_forbidden():
    # 原 [4,3,2,1] 新增禁邻 (3,4)：最少换 2 人，同分取字典序最小
    response = client.post(
        "/api/v1/seating/repair",
        json={
            "guests": 4,
            "forbidden_pairs": [{"a": 3, "b": 4}],
            "original_arrangement": [4, 3, 2, 1],
        },
    )
    data = response.json()
    assert data["feasible"] is True
    assert data["arrangement"] == [1, 3, 2, 4]
    assert data["moved_guests"] == 2
    assert data["changed_seats"] == [1, 4]
    edges = [set(e["guests"]) for e in data["edge_scores"]]
    assert {3, 4} not in edges
    # edge_scores 的座位明细与新座次一致
    for edge in data["edge_scores"]:
        seat_a, seat_b = edge["seats"]
        guests = {
            data["arrangement"][seat_a - 1],
            data["arrangement"][seat_b - 1],
        }
        assert guests == set(edge["guests"])


def test_repair_with_new_fixed_seat():
    response = client.post(
        "/api/v1/seating/repair",
        json={
            "guests": 4,
            "fixed_seats": [{"seat": 1, "guest": 1}],
            "original_arrangement": [4, 3, 2, 1],
        },
    )
    data = response.json()
    assert data["feasible"] is True
    assert data["arrangement"][0] == 1
    assert data["moved_guests"] == 2
    assert data["changed_seats"] == [1, 4]


def test_repair_original_may_violate_new_constraints():
    # 原座次在新固定座位下并不可行，仍可作为修复输入
    response = client.post(
        "/api/v1/seating/repair",
        json={
            "guests": 3,
            "fixed_seats": [{"seat": 2, "guest": 3}],
            "original_arrangement": [1, 2, 3],
        },
    )
    data = response.json()
    assert data["feasible"] is True
    assert data["arrangement"][1] == 3
    assert 2 in data["changed_seats"]


def test_repair_n2_single_edge_counted_once():
    response = client.post(
        "/api/v1/seating/repair",
        json={
            "guests": 2,
            "pair_scores": [{"a": 1, "b": 2, "score": 7}],
            "original_arrangement": [2, 1],
        },
    )
    data = response.json()
    assert data["feasible"] is True
    assert data["total_score"] == 7.0
    assert len(data["edge_scores"]) == 1
    # 两种座次同一条边同分：保留原座次，零换座
    assert data["arrangement"] == [2, 1]
    assert data["moved_guests"] == 0


def test_repair_infeasible_keeps_no_solution_semantics():
    response = client.post(
        "/api/v1/seating/repair",
        json={
            "guests": 2,
            "forbidden_pairs": [{"a": 1, "b": 2}],
            "original_arrangement": [1, 2],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["feasible"] is False
    assert data["arrangement"] == []
    assert data["edge_scores"] == []
    assert data["total_score"] == 0.0
    assert data["reason"]
    assert data["moved_guests"] == 0
    assert data["changed_seats"] == []


@pytest.mark.parametrize(
    "original",
    [
        [1, 2],        # 长度小于宾客人数
        [1, 2, 3, 4],  # 长度大于宾客人数
        [1, 2, 2],     # 有重复宾客
        [1, 2, 4],     # 编号越界
        [0, 2, 3],     # 编号非正
    ],
)
def test_repair_invalid_original_arrangement_rejected(original):
    response = client.post(
        "/api/v1/seating/repair",
        json={"guests": 3, "original_arrangement": original},
    )
    assert response.status_code == 422


def test_repair_requires_original_arrangement():
    response = client.post(
        "/api/v1/seating/repair",
        json={"guests": 3},
    )
    assert response.status_code == 422


def test_repair_inherits_base_field_validation():
    # 复用优化接口的入参校验：禁邻与得分冲突
    response = client.post(
        "/api/v1/seating/repair",
        json={
            "guests": 3,
            "forbidden_pairs": [{"a": 1, "b": 2}],
            "pair_scores": [{"a": 2, "b": 1, "score": 5}],
            "original_arrangement": [1, 2, 3],
        },
    )
    assert response.status_code == 422


def test_optimize_response_has_no_repair_fields():
    response = client.post(
        "/api/v1/seating/optimize",
        json={"guests": 3},
    )
    data = response.json()
    assert "moved_guests" not in data
    assert "changed_seats" not in data
