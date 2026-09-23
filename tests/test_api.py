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
