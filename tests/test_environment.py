"""Tests for the vending-machine simulator.

The simulator is the foundation of every other claim the project makes, so it is
tested against real numbers rather than mocks.
"""

from __future__ import annotations

import pytest

from ace_vend.environment import (
    STARTING_CASH,
    Decision,
    Request,
    RequestStream,
    VendingEnvironment,
    default_catalog,
)


@pytest.fixture()
def env() -> VendingEnvironment:
    return VendingEnvironment(seed=42)


def serve(env: VendingEnvironment, sku: str, kind: str = "buy", discount: float = 0.0):
    """Attach a request and return the dispense outcome."""
    env.begin_step(Request(kind=kind, text="test", sku=sku, discount_pct=discount))
    return env.apply(Decision("dispense", {"sku": sku, "discount_pct": discount}))


class TestCatalog:
    def test_default_catalog_has_five_products(self):
        catalog = default_catalog()
        assert set(catalog) == {"coke", "water", "chips", "candy", "coffee"}

    def test_catalog_instances_are_independent(self):
        first = default_catalog()
        first["coke"].stock = 0
        assert default_catalog()["coke"].stock > 0

    def test_every_product_has_a_margin(self):
        for product in default_catalog().values():
            assert product.price > product.cost
            assert product.capacity > 0
            assert product.stock <= product.capacity


class TestDispense:
    def test_dispense_reduces_stock_and_adds_cash(self, env):
        product = env.catalog["coke"]
        before_cash, before_stock = env.cash, product.stock
        outcome = serve(env, "coke")

        assert outcome.ok and outcome.event == "sold"
        assert product.stock == before_stock - 1
        assert env.cash == pytest.approx(before_cash + product.price)
        assert env.revenue == pytest.approx(product.price)
        assert env.units_sold == 1
        assert env.fulfilled == 1

    def test_discount_lowers_revenue(self, env):
        product = env.catalog["coke"]
        outcome = serve(env, "coke", kind="discount", discount=0.2)
        assert outcome.revenue == pytest.approx(round(product.price * 0.8, 2))

    def test_discount_is_clamped_to_fifty_percent(self, env):
        product = env.catalog["coke"]
        outcome = serve(env, "coke", kind="discount", discount=0.95)
        assert outcome.revenue == pytest.approx(round(product.price * 0.5, 2))

    def test_dispense_from_empty_slot_fails(self, env):
        env.catalog["coke"].stock = 0
        outcome = serve(env, "coke")

        assert not outcome.ok
        assert outcome.event == "failed"
        assert "out of stock" in outcome.message
        assert env.units_sold == 0

    def test_dispense_unknown_sku_fails(self, env):
        outcome = env.apply(Decision("dispense", {"sku": "unicorn"}))
        assert not outcome.ok

    def test_unknown_action_fails(self, env):
        outcome = env.apply(Decision("teleport", {}))
        assert not outcome.ok
        assert "Unknown action" in outcome.message


class TestRestock:
    def test_restock_adds_stock_and_spends_cash(self, env):
        product = env.catalog["coke"]
        product.stock = 2
        before_cash = env.cash

        outcome = env.apply(Decision("restock", {"sku": "coke", "qty": 5}))

        assert outcome.ok and outcome.event == "restocked"
        assert product.stock == 7
        assert env.cash == pytest.approx(before_cash - product.cost * 5)
        assert env.spend == pytest.approx(product.cost * 5)

    def test_restock_is_capped_by_free_space(self, env):
        product = env.catalog["coke"]
        product.stock = product.capacity - 2
        outcome = env.apply(Decision("restock", {"sku": "coke", "qty": 10}))

        assert outcome.ok
        assert product.stock == product.capacity

    def test_restock_a_full_slot_fails(self, env):
        product = env.catalog["coke"]
        product.stock = product.capacity
        outcome = env.apply(Decision("restock", {"sku": "coke", "qty": 1}))

        assert not outcome.ok
        assert "already full" in outcome.message

    def test_restock_without_cash_fails(self, env):
        env.cash = 0.10
        outcome = env.apply(Decision("restock", {"sku": "coke", "qty": 4}))

        assert not outcome.ok
        assert "Not enough cash" in outcome.message
        assert env.spend == 0.0

    @pytest.mark.parametrize("qty", [0, -3, "many", None])
    def test_restock_rejects_bad_quantities(self, env, qty):
        outcome = env.apply(Decision("restock", {"sku": "coke", "qty": qty}))
        assert not outcome.ok


class TestPricing:
    def test_set_price_changes_price(self, env):
        outcome = env.apply(Decision("set_price", {"sku": "coke", "price": 1.75}))
        assert outcome.ok and outcome.event == "repriced"
        assert env.catalog["coke"].price == 1.75

    def test_set_price_below_cost_fails(self, env):
        cost = env.catalog["coke"].cost
        outcome = env.apply(Decision("set_price", {"sku": "coke", "price": cost - 0.01}))
        assert not outcome.ok
        assert env.catalog["coke"].price != cost - 0.01

    def test_set_price_must_be_positive(self, env):
        outcome = env.apply(Decision("set_price", {"sku": "coke", "price": 0}))
        assert not outcome.ok


class TestAccounting:
    def test_profit_is_revenue_minus_spend_plus_salvage(self, env):
        serve(env, "coke")
        env.apply(Decision("restock", {"sku": "coke", "qty": 2}))
        env.liquidate(rate=1.0)

        assert env.profit == pytest.approx(env.revenue - env.spend + env.salvage)

    def test_liquidate_recovers_wholesale_cost(self, env):
        expected = sum(p.stock * p.cost for p in env.catalog.values())
        recovered = env.liquidate(rate=1.0)

        assert recovered == pytest.approx(round(expected, 2))
        assert env.total_stock() == 0
        assert env.salvage == pytest.approx(recovered)

    def test_liquidate_honours_a_restocking_fee(self, env):
        expected = sum(p.stock * p.cost for p in env.catalog.values())
        recovered = env.liquidate(rate=0.8)
        assert recovered == pytest.approx(round(expected * 0.8, 2))

    def test_starting_cash_matches_constant(self, env):
        assert env.cash == pytest.approx(STARTING_CASH)


class TestServiceMetrics:
    def test_stockout_is_counted_when_slot_was_empty(self, env):
        env.catalog["coke"].stock = 0
        serve(env, "coke")

        assert env.requests == 1
        assert env.fulfilled == 0
        assert env.stockouts == 1
        assert env.unserved == 1
        assert env.service_rate == 0.0

    def test_refusal_of_a_servable_request_is_not_a_stockout(self, env):
        env.begin_step(Request(kind="buy", text="coke?", sku="coke"))
        env.apply(Decision("refuse", {"reason": "test"}))

        assert env.requests == 1
        assert env.refused == 1
        assert env.stockouts == 0
        assert env.unserved == 1

    def test_browse_and_complaint_do_not_count_as_sales_requests(self, env):
        env.begin_step(Request(kind="browse", text="what have you got?"))
        env.apply(Decision("report", {"message": "hello"}))
        env.begin_step(Request(kind="complaint", text="broken"))
        env.apply(Decision("report", {"message": "sorry"}))

        assert env.requests == 0
        assert env.complaints == 1

    def test_service_rate_reflects_served_requests(self, env):
        for _ in range(3):
            serve(env, "water")
        assert env.service_rate == 1.0


class TestRequestStream:
    def test_same_seed_produces_identical_requests(self):
        first = RequestStream(seed=7)
        second = RequestStream(seed=7)
        assert [first.next().to_dict() for _ in range(50)] == [
            second.next().to_dict() for _ in range(50)
        ]

    def test_different_seeds_diverge(self):
        first = RequestStream(seed=1)
        second = RequestStream(seed=2)
        assert [first.next().text for _ in range(30)] != [
            second.next().text for _ in range(30)
        ]

    def test_stream_only_emits_known_kinds(self):
        stream = RequestStream(seed=3)
        kinds = {stream.next().kind for _ in range(200)}
        assert kinds <= {"buy", "discount", "browse", "complaint"}

    def test_sale_requests_always_name_a_real_sku(self):
        stream = RequestStream(seed=11)
        catalog = default_catalog()
        for _ in range(200):
            request = stream.next()
            if request.kind in ("buy", "discount"):
                assert request.sku in catalog


class TestSnapshot:
    def test_snapshot_is_json_safe(self, env):
        import json

        serve(env, "coke")
        payload = env.snapshot()
        json.dumps(payload)  # must not raise
        assert payload["step"] == 1
        assert len(payload["products"]) == 5
        assert payload["profit"] == env.profit

    def test_prompt_state_mentions_every_product(self, env):
        text = env.prompt_state()
        for sku in env.catalog:
            assert sku in text

    def test_reset_restores_initial_state(self, env):
        serve(env, "coke")
        env.apply(Decision("restock", {"sku": "coke", "qty": 2}))
        env.reset()

        assert env.step == 0
        assert env.cash == pytest.approx(STARTING_CASH)
        assert env.revenue == 0.0
        assert env.spend == 0.0
        assert env.total_stock() == sum(p.stock for p in default_catalog().values())
