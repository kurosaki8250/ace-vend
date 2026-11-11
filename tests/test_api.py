"""Tests for the Flask API and dashboard."""

from __future__ import annotations

import pytest

from ace_vend.agent import VendingAgent
from ace_vend.api import create_app
from ace_vend.config import Settings


@pytest.fixture()
def app():
    settings = Settings(seed=42, steps=60)
    application = create_app(
        settings=settings,
        agent=VendingAgent(settings=settings, mode="ace", seed=42),
        mode="ace",
    )
    application.config.update(TESTING=True)
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


class TestPages:
    def test_dashboard_renders(self, client):
        response = client.get("/")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "ACE-Vend" in body
        assert "/static/app.js" in body


class TestStateEndpoints:
    def test_health(self, client):
        payload = client.get("/api/health").get_json()
        assert payload == {"ok": True, "mode": "ace"}

    def test_state_has_the_expected_shape(self, client):
        payload = client.get("/api/state").get_json()
        for key in (
            "mode",
            "seed",
            "settings",
            "environment",
            "playbook",
            "guard",
            "metrics",
            "records",
            "learned",
        ):
            assert key in payload
        assert len(payload["environment"]["products"]) == 5

    def test_state_does_not_leak_the_api_key(self, client):
        body = client.get("/api/state").get_data(as_text=True)
        assert "api_key" not in body

    def test_playbook_endpoint(self, client):
        payload = client.get("/api/playbook").get_json()
        assert "bullets" in payload
        assert "stats" in payload

    def test_metrics_endpoint(self, client):
        payload = client.get("/api/metrics").get_json()
        assert payload["mode"] == "ace"
        assert "guard" in payload


class TestStepEndpoint:
    def test_step_advances_the_environment(self, client):
        before = client.get("/api/state").get_json()["environment"]["step"]
        payload = client.post("/api/step", json={}).get_json()

        assert payload["record"]["step"] == before + 1
        assert payload["state"]["environment"]["step"] == before + 1

    def test_step_accepts_customer_text(self, client):
        payload = client.post("/api/step", json={"customer": "I want a water"}).get_json()
        assert payload["record"]["request"]["kind"] == "buy"
        assert payload["record"]["request"]["sku"] == "water"

    def test_step_without_body_still_works(self, client):
        response = client.post("/api/step")
        assert response.status_code == 200

    def test_repeated_steps_grow_the_log(self, client):
        for _ in range(3):
            client.post("/api/step", json={})
        payload = client.get("/api/state").get_json()
        assert len(payload["records"]) == 3


class TestResetEndpoint:
    def test_reset_clears_progress(self, client):
        client.post("/api/step", json={})
        payload = client.post("/api/reset", json={"seed": 7}).get_json()

        assert payload["environment"]["step"] == 0
        assert payload["seed"] == 7
        assert payload["records"] == []

    def test_reset_can_switch_mode(self, client):
        payload = client.post("/api/reset", json={"mode": "baseline"}).get_json()
        assert payload["mode"] == "baseline"

    def test_reset_rejects_an_unknown_mode(self, client):
        response = client.post("/api/reset", json={"mode": "turbo"})
        assert response.status_code == 400


class TestModeEndpoint:
    def test_valid_mode_switches(self, client):
        payload = client.post("/api/mode", json={"mode": "static"}).get_json()
        assert payload["mode"] == "static"
        assert len(payload["playbook"]["bullets"]) == 6

    def test_invalid_mode_is_rejected(self, client):
        response = client.post("/api/mode", json={"mode": "nonsense"})
        assert response.status_code == 400
        assert "mode" in response.get_json()["error"]

    def test_missing_mode_is_rejected(self, client):
        assert client.post("/api/mode", json={}).status_code == 400


class TestExperimentEndpoint:
    def test_experiment_returns_three_conditions(self, client):
        payload = client.post("/api/experiment", json={"steps": 10, "seed": 42}).get_json()

        assert payload["steps"] == 10
        assert len(payload["conditions"]) == 3
        assert [c["key"] for c in payload["conditions"]] == [
            "baseline",
            "static",
            "ace",
        ]
        assert "Condition" in payload["table"]
        assert "| Condition |" in payload["markdown"]

    def test_experiment_clamps_the_step_count(self, client):
        payload = client.post("/api/experiment", json={"steps": 1}).get_json()
        assert payload["steps"] == 5

    def test_experiment_clamps_large_requests(self, client):
        payload = client.post("/api/experiment", json={"steps": 5000}).get_json()
        assert payload["steps"] == 500

    def test_experiment_does_not_persist_results(self, client):
        import ace_vend.experiment as experiment

        original = experiment._save
        called = {"value": False}

        def spy(*args, **kwargs):
            called["value"] = True
            return original(*args, **kwargs)

        experiment._save = spy
        try:
            client.post("/api/experiment", json={"steps": 5})
        finally:
            experiment._save = original

        assert called["value"] is False
