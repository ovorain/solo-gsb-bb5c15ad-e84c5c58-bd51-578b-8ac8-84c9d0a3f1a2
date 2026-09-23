"""API 层测试。"""
from __future__ import annotations

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


def test_optimize_response_has_no_repair_fields():
    response = client.post(
        "/api/v1/seating/optimize",
        json={"guests": 3},
    )
    data = response.json()
    assert "changed_count" not in data
    assert "changed_seats" not in data


def test_repair_basic_keeps_original_when_still_feasible():
    response = client.post(
        "/api/v1/seating/repair",
        json={
            "guests": 4,
            "forbidden_pairs": [{"a": 1, "b": 2}],
            "pair_scores": [{"a": 2, "b": 3, "score": 5}],
            "original_arrangement": [1, 3, 2, 4],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["feasible"] is True
    assert data["arrangement"] == [1, 3, 2, 4]
    assert data["changed_count"] == 0
    assert data["changed_seats"] == []
    assert data["reason"] is None
    assert len(data["edge_scores"]) == 4


def test_repair_minimizes_changes_then_maximizes_score():
    response = client.post(
        "/api/v1/seating/repair",
        json={
            "guests": 5,
            "forbidden_pairs": [{"a": 1, "b": 2}],
            "pair_scores": [{"a": 2, "b": 5, "score": 9}],
            "original_arrangement": [1, 2, 3, 4, 5],
        },
    )
    data = response.json()
    assert data["feasible"] is True
    # 同为 2 换时 [1,4,3,2,5] 得分高于字典序更小的 [1,3,2,4,5]
    assert data["arrangement"] == [1, 4, 3, 2, 5]
    assert data["changed_count"] == 2
    assert data["changed_seats"] == [2, 4]
    assert data["total_score"] == 9


def test_repair_original_violating_new_constraints_accepted():
    # 原座次既触犯新禁邻，又不符合新固定座位，仍然允许
    response = client.post(
        "/api/v1/seating/repair",
        json={
            "guests": 4,
            "forbidden_pairs": [{"a": 1, "b": 2}],
            "fixed_seats": [{"seat": 3, "guest": 4}],
            "original_arrangement": [1, 2, 3, 4],
        },
    )
    data = response.json()
    assert data["feasible"] is True
    assert data["arrangement"][2] == 4
    # 2 换方案均因禁邻 (1,2) 或固定座位冲突不可行，最少需换 3 人
    assert data["changed_count"] == 3
    assert set(data["changed_seats"]) <= {1, 2, 3, 4}
    assert len(data["changed_seats"]) == 3
    edges = [set(e["guests"]) for e in data["edge_scores"]]
    assert {1, 2} not in edges


def test_repair_n2_single_edge():
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
    assert data["changed_count"] == 0
    assert data["total_score"] == 7
    assert len(data["edge_scores"]) == 1


def test_repair_infeasible_keeps_existing_semantics():
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
    assert data["changed_count"] is None
    assert data["changed_seats"] is None
    assert data["reason"]


def test_repair_invalid_original_length_rejected():
    response = client.post(
        "/api/v1/seating/repair",
        json={"guests": 4, "original_arrangement": [1, 2, 3]},
    )
    assert response.status_code == 422


def test_repair_duplicate_guests_in_original_rejected():
    response = client.post(
        "/api/v1/seating/repair",
        json={"guests": 4, "original_arrangement": [1, 2, 2, 4]},
    )
    assert response.status_code == 422


def test_repair_out_of_range_guest_in_original_rejected():
    response = client.post(
        "/api/v1/seating/repair",
        json={"guests": 4, "original_arrangement": [1, 2, 3, 5]},
    )
    assert response.status_code == 422


def test_repair_missing_original_rejected():
    response = client.post(
        "/api/v1/seating/repair",
        json={"guests": 4},
    )
    assert response.status_code == 422
