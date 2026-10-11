from fastapi.testclient import TestClient

from simdemocracy.api import create_app


def test_observer_run_returns_an_explained_history() -> None:
    client = TestClient(create_app())
    page = client.get("/")
    assert page.status_code == 200
    assert "Why did this happen?" in page.text
    response = client.post(
        "/api/run",
        json={"seed": 3, "ticks": 12, "population": 60, "parliament_seats": 21},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["seed"] == 3
    assert body["ticks_run"] == 12
    assert any(event["type"] == "election_held" for event in body["events"])
    assert body["metrics"]["historical_causality"]["factor_coverage"] == 1.0
    repeated = client.post(
        "/api/run",
        json={"seed": 3, "ticks": 12, "population": 60, "parliament_seats": 21},
    )
    assert repeated.json()["events"] == body["events"]
