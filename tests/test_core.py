# tests/test_core.py — Unit tests for ACE-Vend core components
#
# These tests use the mock LLM and an in-memory SQLite database so they
# run without downloading the model or touching the real data directory.

import json
import os
import sys
import tempfile
import pytest

# Point to a temp data dir before importing project modules
_TMP = tempfile.mkdtemp()
os.environ["ACE_VEND_TEST"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as cfg
cfg.DATABASE_PATH = os.path.join(_TMP, "test_inventory.db")
cfg.PLAYBOOK_PATH = os.path.join(_TMP, "test_playbook.txt")
cfg.DATA_DIR = _TMP


# ── Environment ──────────────────────────────────────────────────────────────

class TestVendingEnvironment:
    def setup_method(self):
        from backend.environment import VendingEnvironment
        self.env = VendingEnvironment()

    def test_initial_state(self):
        state = self.env.observe()
        assert state["cash"] == cfg.INITIAL_CASH
        assert state["status"] == "online"
        assert all(v > 0 for v in state["inventory"].values())

    def test_dispense_success(self):
        outcome = self.env.step_action({"type": "dispense", "item": "Coke", "payment": 2})
        assert outcome["success"] is True
        assert self.env.inventory["Coke"] == cfg.INITIAL_INVENTORY["Coke"] - 1
        assert self.env.cash == cfg.INITIAL_CASH + 2

    def test_dispense_out_of_stock(self):
        self.env.inventory["Coke"] = 0
        outcome = self.env.step_action({"type": "dispense", "item": "Coke", "payment": 2})
        assert outcome["success"] is False
        assert outcome.get("hallucination") is True

    def test_dispense_unknown_item(self):
        outcome = self.env.step_action({"type": "dispense", "item": "Soda", "payment": 5})
        assert outcome["success"] is False
        assert outcome.get("hallucination") is True

    def test_dispense_insufficient_payment(self):
        outcome = self.env.step_action({"type": "dispense", "item": "Coke", "payment": 0.5})
        assert outcome["success"] is False

    def test_restock(self):
        initial_qty = self.env.inventory["Chips"]
        outcome = self.env.step_action({"type": "restock", "item": "Chips", "quantity": 2})
        assert outcome["success"] is True
        assert self.env.inventory["Chips"] == initial_qty + 2

    def test_check_inventory(self):
        outcome = self.env.step_action({"type": "check_inventory"})
        assert outcome["success"] is True

    def test_status_transitions_to_restock_needed(self):
        self.env.inventory["Coke"] = 1
        self.env.step_action({"type": "idle", "reason": "test"})
        assert self.env.status == "restock_needed"

    def test_reset(self):
        self.env.step_action({"type": "dispense", "item": "Coke", "payment": 2})
        self.env.reset()
        state = self.env.observe()
        assert state["cash"] == cfg.INITIAL_CASH
        assert state["inventory"] == cfg.INITIAL_INVENTORY


# ── PlaybookManager ──────────────────────────────────────────────────────────

class TestPlaybookManager:
    def setup_method(self):
        # Fresh playbook file each test
        cfg.PLAYBOOK_PATH = os.path.join(_TMP, f"pb_{id(self)}.txt")
        from backend.playbook_manager import PlaybookManager
        self.pm = PlaybookManager()

    def test_empty_on_start(self):
        assert self.pm.count() == 0

    def test_add_bullet(self):
        b = self.pm.add_or_update("Always check inventory first.", "helpful")
        assert b.helpful == 1
        assert b.harmful == 0
        assert self.pm.count() == 1

    def test_deduplication(self):
        self.pm.add_or_update("Always check inventory first.", "helpful")
        self.pm.add_or_update("Always check inventory first.", "helpful")
        assert self.pm.count() == 1
        assert self.pm.bullets[0].helpful == 2

    def test_harmful_counter(self):
        self.pm.add_or_update("Give discounts freely.", "helpful")
        self.pm.add_or_update("Give discounts freely.", "harmful")
        assert self.pm.bullets[0].score == 0

    def test_render_within_budget(self):
        for i in range(5):
            self.pm.add_or_update(f"Strategy number {i}.", "helpful")
        rendered = self.pm.render(token_budget=4000)
        assert "STRATEGIES" in rendered

    def test_persistence(self):
        self.pm.add_or_update("Persist this bullet.", "helpful")
        from backend.playbook_manager import PlaybookManager
        pm2 = PlaybookManager()
        assert pm2.count() == 1
        assert "Persist this bullet" in pm2.bullets[0].text


# ── HallucinationGuard ───────────────────────────────────────────────────────

class TestHallucinationGuard:
    def setup_method(self):
        # Use mock LLM to avoid model loading
        import backend.utils as utils
        utils._use_mock = True
        from backend.agent import VendingAgent
        self.agent = VendingAgent()

    def _state(self, inventory=None):
        base = self.agent.env.observe()
        if inventory is not None:
            base["inventory"] = inventory
        return base

    def test_valid_action_passes(self):
        result = self.agent._hallucination_guard(
            {"type": "check_inventory"},
            self._state()
        )
        assert result["pass"] is True

    def test_unknown_action_blocked(self):
        result = self.agent._hallucination_guard(
            {"type": "teleport_item"},
            self._state()
        )
        assert result["pass"] is False

    def test_dispense_unknown_item_blocked(self):
        result = self.agent._hallucination_guard(
            {"type": "dispense", "item": "Soda"},
            self._state()
        )
        assert result["pass"] is False

    def test_dispense_zero_stock_blocked(self):
        inv = dict(cfg.INITIAL_INVENTORY)
        inv["Coke"] = 0
        result = self.agent._hallucination_guard(
            {"type": "dispense", "item": "Coke"},
            self._state(inventory=inv)
        )
        assert result["pass"] is False

    def test_dispense_in_stock_passes(self):
        result = self.agent._hallucination_guard(
            {"type": "dispense", "item": "Coke", "payment": 2},
            self._state()
        )
        assert result["pass"] is True


# ── Flask API ────────────────────────────────────────────────────────────────

class TestFlaskAPI:
    def setup_method(self):
        import backend.utils as utils
        utils._use_mock = True
        from backend.app import app, get_agent
        get_agent()  # warm up with mock
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_index(self):
        r = self.client.get("/")
        assert r.status_code == 200

    def test_api_state(self):
        r = self.client.get("/api/state")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert "env" in data
        assert "playbook" in data

    def test_api_step(self):
        r = self.client.post("/api/step",
                             data=json.dumps({"customer": "I want Coke"}),
                             content_type="application/json")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert "action" in data
        assert "outcome" in data

    def test_api_reset(self):
        r = self.client.post("/api/reset")
        assert r.status_code == 200
        assert json.loads(r.data)["ok"] is True

    def test_api_playbook(self):
        r = self.client.get("/api/playbook")
        assert r.status_code == 200
        assert isinstance(json.loads(r.data), list)

    def test_api_metrics(self):
        r = self.client.get("/api/metrics")
        assert r.status_code == 200
        assert isinstance(json.loads(r.data), list)
