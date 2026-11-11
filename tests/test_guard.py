"""Tests for the two-layer hallucination guard.

Every test here corresponds to a real failure mode: a malformed action
(structural) or a well-formed action that asserts something false (semantic).
"""

from __future__ import annotations

import pytest

from ace_vend.environment import Decision, VendingEnvironment
from ace_vend.guard import HallucinationGuard


@pytest.fixture()
def env() -> VendingEnvironment:
    return VendingEnvironment(seed=42)


@pytest.fixture()
def guard() -> HallucinationGuard:
    return HallucinationGuard()


class TestStructuralLayer:
    def test_non_json_is_rejected(self, guard, env):
        result = guard.check("I think we should restock the coke.", env)
        assert not result.allowed
        assert result.layer == "structural"
        assert "JSON" in result.violations[0]

    def test_missing_action_is_rejected(self, guard, env):
        result = guard.check({"args": {"sku": "coke"}}, env)
        assert not result.allowed
        assert "action" in result.violations[0]

    def test_unknown_action_is_rejected(self, guard, env):
        result = guard.check({"action": "embezzle", "args": {}}, env)
        assert not result.allowed
        assert "unknown action" in result.violations[0]

    def test_args_must_be_an_object(self, guard, env):
        result = guard.check({"action": "dispense", "args": ["coke"]}, env)
        assert not result.allowed
        assert "'args' must be an object" in result.violations[0]

    def test_unexpected_argument_is_rejected(self, guard, env):
        result = guard.check(
            {"action": "dispense", "args": {"sku": "coke", "free": True}}, env
        )
        assert not result.allowed
        assert any("unexpected argument" in v for v in result.violations)

    def test_missing_sku_is_rejected(self, guard, env):
        result = guard.check({"action": "dispense", "args": {}}, env)
        assert not result.allowed
        assert any("sku" in v for v in result.violations)

    def test_restock_quantity_must_be_an_integer(self, guard, env):
        result = guard.check({"action": "restock", "args": {"sku": "coke", "qty": "4"}}, env)
        assert not result.allowed
        assert any("integer" in v for v in result.violations)

    def test_discount_must_be_a_fraction(self, guard, env):
        result = guard.check(
            {"action": "dispense", "args": {"sku": "coke", "discount_pct": 30}}, env
        )
        assert not result.allowed
        assert any("between 0 and 1" in v for v in result.violations)

    def test_empty_report_is_rejected(self, guard, env):
        result = guard.check({"action": "report", "args": {"message": "  "}}, env)
        assert not result.allowed

    def test_overlong_report_is_rejected(self, guard, env):
        result = guard.check({"action": "report", "args": {"message": "x" * 300}}, env)
        assert not result.allowed
        assert any("280" in v for v in result.violations)

    def test_json_inside_a_markdown_fence_is_accepted(self, guard, env):
        raw = '```json\n{"action": "refuse", "args": {"reason": "out of stock"}}\n```'
        result = guard.check(raw, env)
        assert result.allowed
        assert result.decision.action == "refuse"

    def test_decision_object_is_accepted(self, guard, env):
        result = guard.check(Decision("refuse", {"reason": "nope"}), env)
        assert result.allowed


class TestSemanticLayer:
    def test_dispense_from_empty_slot_is_blocked(self, guard, env):
        env.catalog["coke"].stock = 0
        result = guard.check({"action": "dispense", "args": {"sku": "coke"}}, env)

        assert not result.allowed
        assert result.layer == "semantic"
        assert any("inventory" in v for v in result.violations)
        assert guard.counts["inventory"] == 1

    def test_dispense_of_unknown_product_is_blocked(self, guard, env):
        result = guard.check({"action": "dispense", "args": {"sku": "unicorn"}}, env)
        assert not result.allowed
        assert any("unknown product" in v for v in result.violations)

    def test_discount_below_cost_is_blocked(self, guard, env):
        # Coke costs $0.55 and sells for $1.50: a 70% discount is below cost.
        result = guard.check(
            {"action": "dispense", "args": {"sku": "coke", "discount_pct": 0.7}}, env
        )
        assert not result.allowed
        assert any("ceiling" in v or "below wholesale" in v for v in result.violations)

    def test_small_discount_is_allowed(self, guard, env):
        result = guard.check(
            {"action": "dispense", "args": {"sku": "coke", "discount_pct": 0.1}}, env
        )
        assert result.allowed

    def test_overfill_is_blocked(self, guard, env):
        product = env.catalog["coke"]
        space = product.capacity - product.stock
        result = guard.check(
            {"action": "restock", "args": {"sku": "coke", "qty": space + 1}}, env
        )
        assert not result.allowed
        assert any("capacity" in v for v in result.violations)
        assert guard.counts["capacity"] == 1

    def test_restock_of_a_full_slot_is_blocked(self, guard, env):
        env.catalog["coke"].stock = env.catalog["coke"].capacity
        result = guard.check({"action": "restock", "args": {"sku": "coke", "qty": 1}}, env)
        assert not result.allowed
        assert any("already full" in v for v in result.violations)

    def test_unaffordable_restock_is_blocked(self, guard, env):
        env.cash = 0.10
        result = guard.check({"action": "restock", "args": {"sku": "coke", "qty": 2}}, env)
        assert not result.allowed
        assert any("available" in v for v in result.violations)
        assert guard.counts["affordability"] == 1

    def test_affordable_restock_is_allowed(self, guard, env):
        result = guard.check({"action": "restock", "args": {"sku": "water", "qty": 3}}, env)
        assert result.allowed

    def test_price_below_cost_is_blocked(self, guard, env):
        result = guard.check({"action": "set_price", "args": {"sku": "coke", "price": 0.10}}, env)
        assert not result.allowed
        assert any("below wholesale" in v for v in result.violations)

    def test_implausible_markup_is_blocked(self, guard, env):
        result = guard.check({"action": "set_price", "args": {"sku": "coke", "price": 99.0}}, env)
        assert not result.allowed
        assert any("implausibly high" in v for v in result.violations)

    def test_reasonable_price_is_allowed(self, guard, env):
        result = guard.check({"action": "set_price", "args": {"sku": "coke", "price": 1.75}}, env)
        assert result.allowed


class TestStockClaimChecks:
    def test_invented_count_is_blocked(self, guard, env):
        env.catalog["coke"].stock = 3
        result = guard.check(
            {"action": "report", "args": {"message": "coke: 5 units left"}}, env
        )
        assert not result.allowed
        assert any("stock-claim" in v for v in result.violations)
        assert guard.counts["stock_claim"] == 1

    def test_correct_count_is_allowed(self, guard, env):
        env.catalog["coke"].stock = 3
        result = guard.check(
            {"action": "report", "args": {"message": "coke: 3 units left"}}, env
        )
        assert result.allowed

    def test_false_out_of_stock_claim_is_blocked(self, guard, env):
        env.catalog["water"].stock = 4
        result = guard.check(
            {"action": "report", "args": {"message": "water is out of stock"}}, env
        )
        assert not result.allowed
        assert any("out of stock" in v for v in result.violations)

    def test_reports_without_numbers_are_allowed(self, guard, env):
        result = guard.check(
            {"action": "report", "args": {"message": "Customer complained; escalating."}},
            env,
        )
        assert result.allowed

    def test_the_naive_inventory_report_is_blocked(self, guard, env):
        # The offline baseline emits this fixed, stale string. Against a fresh
        # machine it contradicts live state, so the guard must catch it.
        message = (
            "Inventory — coke: 5 units left, water: 5 units left, "
            "chips: 4 units left, candy: 4 units left, coffee: 3 units left"
        )
        result = guard.check({"action": "report", "args": {"message": message}}, env)
        assert not result.allowed
        assert len(result.violations) >= 1

    def test_a_truthful_generated_report_is_allowed(self, guard, env):
        message = "Inventory — " + ", ".join(
            f"{p.sku}: {p.stock}/{p.capacity}" for p in env.catalog.values()
        )
        result = guard.check({"action": "report", "args": {"message": message}}, env)
        assert result.allowed, result.violations


class TestStatistics:
    def test_stats_track_checked_and_blocked(self, guard, env):
        guard.check({"action": "refuse", "args": {"reason": "x"}}, env)
        env.catalog["coke"].stock = 0
        guard.check({"action": "dispense", "args": {"sku": "coke"}}, env)

        stats = guard.stats()
        assert stats["checked"] == 2
        assert stats["blocked"] == 1
        assert stats["rate"] == pytest.approx(0.5)
        assert stats["by_category"]["inventory"] == 1

    def test_reset_clears_everything(self, guard, env):
        guard.check({"action": "dispense", "args": {"sku": "coke"}}, env)
        guard.reset()
        stats = guard.stats()
        assert stats["checked"] == 0
        assert stats["blocked"] == 0
        assert stats["by_category"] == {}

    def test_log_is_bounded(self, guard, env):
        env.catalog["coke"].stock = 0
        for _ in range(260):
            guard.check({"action": "dispense", "args": {"sku": "coke"}}, env)
        assert len(guard.log) <= 200
        assert guard.blocked == 260

    def test_violations_are_deduplicated(self, guard, env):
        env.catalog["coke"].stock = 0
        result = guard.check({"action": "dispense", "args": {"sku": "coke"}}, env)
        assert len(result.violations) == len(set(result.violations))
