"""Tests for the agent's ACE loop and customer-text parsing."""

from __future__ import annotations

import json

import pytest

from ace_vend.agent import VendingAgent
from ace_vend.config import Settings
from ace_vend.environment import Request


def make_agent(mode: str = "ace", steps: int = 60) -> VendingAgent:
    return VendingAgent(settings=Settings(seed=42, steps=steps), mode=mode, seed=42)


class TestConstruction:
    def test_rejects_unknown_mode(self):
        with pytest.raises(ValueError):
            make_agent(mode="turbo")

    def test_ace_starts_with_an_empty_playbook(self):
        agent = make_agent("ace")
        assert agent.playbook.bullets == []

    def test_static_starts_with_the_handwritten_playbook(self):
        agent = make_agent("static")
        assert len(agent.playbook.bullets) == 6

    def test_baseline_starts_with_an_empty_playbook(self):
        agent = make_agent("baseline")
        assert agent.playbook.bullets == []

    def test_backend_is_offline_by_default(self):
        assert make_agent().backend.name == "offline"


class TestStepLoop:
    def test_step_returns_a_complete_record(self):
        agent = make_agent()
        record = agent.step()

        for key in (
            "step",
            "request",
            "proposed",
            "decision",
            "guard",
            "outcome",
            "allowed",
            "reward",
            "profit",
            "cash",
            "learned",
        ):
            assert key in record
        assert record["step"] == 1
        assert agent.env.step == 1

    def test_ace_learns_bullets(self):
        agent = make_agent("ace")
        for _ in range(25):
            agent.step()
        assert len(agent.playbook.bullets) > 0

    def test_baseline_never_learns(self):
        agent = make_agent("baseline")
        for _ in range(25):
            agent.step()
        assert agent.playbook.bullets == []

    def test_static_never_grows_its_playbook(self):
        agent = make_agent("static")
        for _ in range(25):
            agent.step()
        assert len(agent.playbook.bullets) == 6

    def test_ace_playbook_is_serialisable_after_learning(self):
        agent = make_agent("ace")
        for _ in range(20):
            agent.step()
        payload = agent.playbook.to_dict()
        json.dumps(payload)
        assert payload["stats"]["bullets"] == len(agent.playbook.bullets)

    def test_guard_blocks_are_recorded(self):
        agent = make_agent("baseline")
        for _ in range(40):
            agent.step()
        assert agent.guard.blocked > 0
        assert any(not r["allowed"] for r in agent.records)

    def test_blocked_actions_are_never_executed(self):
        agent = make_agent("baseline")
        for _ in range(40):
            agent.step()
        for record in agent.records:
            if not record["allowed"]:
                assert record["decision"] is None
                assert record["outcome"]["event"] == "refused"

    def test_customer_text_overrides_the_stream(self):
        agent = make_agent()
        record = agent.step("I would like a water please")
        assert record["request"]["kind"] == "buy"
        assert record["request"]["sku"] == "water"

    def test_learned_bullets_are_logged_with_their_step(self):
        agent = make_agent("ace")
        for _ in range(20):
            agent.step()
        assert agent.learned
        assert all("step" in item for item in agent.learned)

    def test_reset_restores_the_initial_state(self):
        agent = make_agent("ace")
        for _ in range(15):
            agent.step()
        agent.reset(seed=7)

        assert agent.env.step == 0
        assert agent.seed == 7
        assert agent.playbook.bullets == []
        assert agent.records == []

    def test_reset_restores_the_static_playbook(self):
        agent = make_agent("static")
        for _ in range(10):
            agent.step()
        agent.reset()
        assert len(agent.playbook.bullets) == 6


class TestParsing:
    @pytest.fixture()
    def agent(self) -> VendingAgent:
        return make_agent()

    @pytest.mark.parametrize(
        "text,sku",
        [
            ("I want a Coke", "coke"),
            ("coca-cola please", "coke"),
            ("some water", "water"),
            ("chips!", "chips"),
            ("a candy bar", "candy"),
            ("cold brew", "coffee"),
        ],
    )
    def test_buy_requests_find_the_sku(self, agent, text, sku):
        request = agent.parse_customer_text(text)
        assert request.kind == "buy"
        assert request.sku == sku

    def test_discount_requests_are_detected(self, agent):
        request = agent.parse_customer_text("Can I get 30% off the coke?")
        assert request.kind == "discount"
        assert request.sku == "coke"
        assert request.discount_pct == pytest.approx(0.3)

    def test_discount_percentage_is_clamped(self, agent):
        request = agent.parse_customer_text("90% off everything")
        assert request.discount_pct <= 0.5

    @pytest.mark.parametrize(
        "text",
        [
            "This machine ate my money",
            "the machine is broken",
            "I want a refund",
            "the coil is jammed",
        ],
    )
    def test_complaints_are_detected(self, agent, text):
        assert agent.parse_customer_text(text).kind == "complaint"

    def test_browsing_is_the_default(self, agent):
        assert agent.parse_customer_text("hello there").kind == "browse"

    def test_blank_input_becomes_browse(self, agent):
        request = agent.parse_customer_text("")
        assert request.kind == "browse"

    def test_complaint_takes_precedence_over_sku(self, agent):
        request = agent.parse_customer_text("the coke machine is broken")
        assert request.kind == "complaint"


class TestViews:
    def test_metrics_has_every_documented_key(self):
        metrics = make_agent().metrics()
        for key in (
            "mode",
            "backend",
            "step",
            "profit",
            "revenue",
            "spend",
            "cash",
            "units_sold",
            "requests",
            "fulfilled",
            "refused",
            "stockouts",
            "service_rate",
            "guard",
            "playbook",
        ):
            assert key in metrics

    def test_state_is_json_serialisable(self):
        agent = make_agent()
        for _ in range(5):
            agent.step()
        json.dumps(agent.state())

    def test_state_never_leaks_the_api_key(self):
        settings = Settings(seed=42, openai_api_key="sk-supersecret")
        agent = VendingAgent(settings=settings, mode="ace", seed=42)
        assert "sk-supersecret" not in json.dumps(agent.state())

    def test_records_are_capped_in_state(self):
        agent = make_agent()
        for _ in range(50):
            agent.step()
        assert len(agent.state()["records"]) <= 40

    def test_episodes_are_kept_for_reflection(self):
        agent = make_agent()
        for _ in range(5):
            agent.step()
        assert len(agent.episodes) == 5
