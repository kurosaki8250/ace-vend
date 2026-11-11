"""The vending machine simulator.

This is the *world* the agent acts in. It is deliberately deterministic: given a
seed, the same sequence of customer requests is produced every time, which makes
the three-condition experiment in :mod:`ace_vend.experiment` a fair comparison —
every condition faces an identical stream of customers.

Economics
---------
* ``cash`` starts at :data:`STARTING_CASH` and moves with sales and restocking.
* ``profit = revenue - spend`` (restocking is the only cost).
* A request that cannot be served because the slot is empty is a **stockout**
  and is counted separately from a deliberate refusal.

Nothing here knows about LLMs, ACE or the guard. That separation is what makes
the simulator unit-testable on its own.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

STARTING_CASH = 40.0

# Actions the agent is allowed to emit. The guard enforces this list.
ACTIONS = ("dispense", "restock", "set_price", "report", "refuse")


@dataclass
class Product:
    sku: str
    name: str
    cost: float          # wholesale price paid per unit
    price: float         # retail price charged per unit
    stock: int
    capacity: int
    popularity: int      # relative demand weight

    def to_dict(self) -> dict:
        return {
            "sku": self.sku,
            "name": self.name,
            "cost": round(self.cost, 2),
            "price": round(self.price, 2),
            "stock": self.stock,
            "capacity": self.capacity,
            "popularity": self.popularity,
            "fill": round(self.stock / self.capacity, 3) if self.capacity else 0.0,
        }


def default_catalog() -> Dict[str, Product]:
    """A fresh catalog. Never share mutable product state between runs."""
    products = [
        Product("coke", "Coca-Cola", cost=0.55, price=1.50, stock=3, capacity=12, popularity=5),
        Product("water", "Water", cost=0.30, price=1.00, stock=3, capacity=12, popularity=4),
        Product("chips", "Chips", cost=0.60, price=1.25, stock=2, capacity=10, popularity=3),
        Product("candy", "Candy Bar", cost=0.45, price=1.10, stock=2, capacity=10, popularity=2),
        Product("coffee", "Cold Brew", cost=0.90, price=2.25, stock=2, capacity=8, popularity=3),
    ]
    return {p.sku: p for p in products}


@dataclass
class Request:
    """One customer arriving at the machine."""

    kind: str                     # buy | discount | browse | complaint
    text: str
    sku: Optional[str] = None
    discount_pct: float = 0.0

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "text": self.text,
            "sku": self.sku,
            "discount_pct": self.discount_pct,
        }


class RequestStream:
    """Deterministic customer generator.

    A fresh stream per run guarantees every condition sees the same customers.
    """

    BUY = 0.68
    DISCOUNT = 0.82
    BROWSE = 0.92
    # remainder -> complaint

    def __init__(self, seed: int = 42, catalog: Optional[Dict[str, Product]] = None):
        self.rng = random.Random(seed)
        self.catalog = catalog or default_catalog()
        self._skus = list(self.catalog)
        self._weights = [self.catalog[s].popularity for s in self._skus]

    def _pick_sku(self) -> str:
        return self.rng.choices(self._skus, weights=self._weights, k=1)[0]

    def next(self) -> Request:
        roll = self.rng.random()
        if roll < self.BUY:
            sku = self._pick_sku()
            name = self.catalog[sku].name
            return Request(kind="buy", sku=sku, text=f"I'd like a {name}, please.")
        if roll < self.DISCOUNT:
            sku = self._pick_sku()
            name = self.catalog[sku].name
            pct = self.rng.choice([0.1, 0.2, 0.3])
            return Request(
                kind="discount",
                sku=sku,
                discount_pct=pct,
                text=f"Any chance you'd knock {int(pct * 100)}% off the {name}?",
            )
        if roll < self.BROWSE:
            return Request(kind="browse", text="What have you got today?")
        return Request(kind="complaint", text="This machine ate my money earlier.")


@dataclass
class Decision:
    """A single action proposed by the agent."""

    action: str
    args: Dict[str, object] = field(default_factory=dict)
    reasoning: str = ""
    used_tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "args": dict(self.args),
            "reasoning": self.reasoning,
            "used_tags": list(self.used_tags),
        }


@dataclass
class Outcome:
    """What the world did with the decision."""

    ok: bool
    reward: float
    event: str          # sold | restocked | repriced | reported | refused | failed
    message: str
    revenue: float = 0.0
    spend: float = 0.0

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "reward": round(self.reward, 2),
            "event": self.event,
            "message": self.message,
            "revenue": round(self.revenue, 2),
            "spend": round(self.spend, 2),
        }


class VendingEnvironment:
    """Mutable world state plus the transition function."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.reset()

    # ------------------------------------------------------------------ reset

    def reset(self) -> None:
        self.catalog = default_catalog()
        self.cash = STARTING_CASH
        self.revenue = 0.0
        self.spend = 0.0
        self.salvage = 0.0
        self.units_sold = 0
        self.requests = 0
        self.fulfilled = 0
        self.refused = 0
        self.unserved = 0
        self.stockouts = 0
        self.reports = 0
        self.complaints = 0
        self.complaints_handled = 0
        self.step = 0
        self.history: List[dict] = []
        self.current_request: Optional[Request] = None

    # ------------------------------------------------------------- properties

    @property
    def profit(self) -> float:
        return round(self.revenue - self.spend + self.salvage, 2)

    @property
    def service_rate(self) -> float:
        return round(self.fulfilled / self.requests, 3) if self.requests else 0.0

    def total_stock(self) -> int:
        return sum(p.stock for p in self.catalog.values())

    def lowest_stock(self) -> int:
        return min(p.stock for p in self.catalog.values())

    # ---------------------------------------------------------------- observe

    def snapshot(self) -> dict:
        """Full state, safe to serialise to the browser."""
        return {
            "step": self.step,
            "cash": round(self.cash, 2),
            "revenue": round(self.revenue, 2),
            "spend": round(self.spend, 2),
            "salvage": round(self.salvage, 2),
            "profit": self.profit,
            "units_sold": self.units_sold,
            "requests": self.requests,
            "fulfilled": self.fulfilled,
            "refused": self.refused,
            "unserved": self.unserved,
            "stockouts": self.stockouts,
            "service_rate": self.service_rate,
            "reports": self.reports,
            "complaints": self.complaints,
            "complaints_handled": self.complaints_handled,
            "products": [p.to_dict() for p in self.catalog.values()],
            "history": list(self.history),
        }

    def prompt_state(self) -> str:
        """Compact textual state for a language model prompt."""
        lines = [
            f"Step {self.step} | cash ${self.cash:.2f} | profit ${self.profit:.2f}",
            "Inventory (sku: stock/capacity, cost, price):",
        ]
        for p in self.catalog.values():
            lines.append(
                f"  {p.sku}: {p.stock}/{p.capacity}, "
                f"cost ${p.cost:.2f}, price ${p.price:.2f}"
            )
        return "\n".join(lines)

    # --------------------------------------------------------------- apply

    def apply(self, decision: Decision) -> Outcome:
        """Execute a decision and return its economic outcome.

        The environment is defensive: it validates on its own even though the
        guard normally runs first, so a disabled guard cannot corrupt state.
        """
        self.step += 1
        action = decision.action
        args = decision.args or {}

        request = self.current_request
        sale_request = bool(request and request.kind in ("buy", "discount"))
        servable = bool(
            sale_request
            and request.sku
            and self.catalog[request.sku].stock > 0
        )
        fulfilled_before = self.fulfilled

        if action == "dispense":
            outcome = self._dispense(args)
        elif action == "restock":
            outcome = self._restock(args)
        elif action == "set_price":
            outcome = self._set_price(args)
        elif action == "report":
            outcome = self._report(args)
        elif action == "refuse":
            outcome = self._refuse(args)
        else:
            outcome = Outcome(False, 0.0, "failed", f"Unknown action '{action}'")

        # A sale request that did not end in a fulfilled sale is a lost sale.
        # It is a *stockout* only when the slot was already empty when the
        # customer arrived — that distinction is what makes the metric useful.
        if sale_request and self.fulfilled == fulfilled_before:
            self.unserved += 1
            if not servable:
                self.stockouts += 1

        return outcome

    def _dispense(self, args: dict) -> Outcome:
        sku = args.get("sku")
        product = self.catalog.get(sku)
        if product is None:
            return Outcome(False, 0.0, "failed", f"Unknown product '{sku}'")
        if product.stock <= 0:
            return Outcome(False, 0.0, "failed", f"{product.name} is out of stock")

        discount = float(args.get("discount_pct", 0.0) or 0.0)
        discount = max(0.0, min(discount, 0.5))
        revenue = round(product.price * (1.0 - discount), 2)

        product.stock -= 1
        self.units_sold += 1
        self.revenue = round(self.revenue + revenue, 2)
        self.cash = round(self.cash + revenue, 2)

        served = self._serves_request(sku)
        if served:
            self.fulfilled += 1

        note = f" (at {int(discount * 100)}% off)" if discount else ""
        return Outcome(
            True,
            revenue,
            "sold",
            f"Sold {product.name} for ${revenue:.2f}{note}",
            revenue=revenue,
        )

    def _restock(self, args: dict) -> Outcome:
        sku = args.get("sku")
        product = self.catalog.get(sku)
        if product is None:
            return Outcome(False, 0.0, "failed", f"Unknown product '{sku}'")

        try:
            qty = int(args.get("qty", 0))
        except (TypeError, ValueError):
            return Outcome(False, 0.0, "failed", "Restock quantity must be an integer")

        if qty <= 0:
            return Outcome(False, 0.0, "failed", "Restock quantity must be positive")

        space = product.capacity - product.stock
        if space <= 0:
            return Outcome(False, 0.0, "failed", f"{product.name} slot is already full")
        qty = min(qty, space)

        cost_total = round(product.cost * qty, 2)
        if cost_total > self.cash + 1e-9:
            return Outcome(
                False, 0.0, "failed",
                f"Not enough cash: need ${cost_total:.2f}, have ${self.cash:.2f}",
            )

        product.stock += qty
        self.spend = round(self.spend + cost_total, 2)
        self.cash = round(self.cash - cost_total, 2)
        return Outcome(
            True, -cost_total, "restocked",
            f"Restocked {qty}x {product.name} for ${cost_total:.2f}",
            spend=cost_total,
        )

    def _set_price(self, args: dict) -> Outcome:
        sku = args.get("sku")
        product = self.catalog.get(sku)
        if product is None:
            return Outcome(False, 0.0, "failed", f"Unknown product '{sku}'")
        try:
            price = round(float(args.get("price", 0.0)), 2)
        except (TypeError, ValueError):
            return Outcome(False, 0.0, "failed", "Price must be a number")
        if price <= 0:
            return Outcome(False, 0.0, "failed", "Price must be positive")
        if price < product.cost:
            return Outcome(
                False, 0.0, "failed",
                f"Price ${price:.2f} is below wholesale cost ${product.cost:.2f}",
            )
        old = product.price
        product.price = price
        return Outcome(True, 0.0, "repriced", f"{product.name} price ${old:.2f} -> ${price:.2f}")

    def _report(self, args: dict) -> Outcome:
        message = str(args.get("message", "")).strip()
        if not message:
            return Outcome(False, 0.0, "failed", "Empty report")
        self.reports += 1
        if self.complaints and self.complaints_handled < self.complaints:
            self.complaints_handled += 1
        return Outcome(True, 0.0, "reported", f"Reported to owner: {message}")

    def _refuse(self, args: dict) -> Outcome:
        reason = str(args.get("reason", "no reason given")).strip() or "no reason given"
        if self._pending_sale():
            self.refused += 1
        return Outcome(True, 0.0, "refused", f"Refused: {reason}")

    # ------------------------------------------------------------- internals

    def _serves_request(self, sku: str) -> bool:
        req = getattr(self, "current_request", None)
        return bool(req and req.sku == sku and req.kind in ("buy", "discount"))

    def _pending_sale(self) -> bool:
        req = getattr(self, "current_request", None)
        return bool(req and req.kind in ("buy", "discount"))

    def begin_step(self, request: Request) -> None:
        """Attach the customer request that the next decision responds to."""
        self.current_request = request
        if request.kind in ("buy", "discount"):
            self.requests += 1
        elif request.kind == "complaint":
            self.complaints += 1

    def liquidate(self, rate: float = 1.0) -> float:
        """Return unsold stock to the wholesaler at *rate* of cost.

        Without this, a finite-horizon run punishes any policy that keeps a
        buffer on the shelf, purely because the run ended. That is an artefact
        of the experiment, not a property of the policy, so the experiment
        neutralises it. The default recovers the full wholesale cost; pass
        ``rate=0.8`` to model a 20% restocking fee.
        """
        recovered = round(
            sum(p.stock * p.cost for p in self.catalog.values()) * rate, 2
        )
        for product in self.catalog.values():
            product.stock = 0
        self.salvage = recovered
        self.cash = round(self.cash + recovered, 2)
        return recovered

    def record(self, entry: dict) -> None:
        """Append a step record to the history used by the UI and charts."""
        self.history.append(entry)
