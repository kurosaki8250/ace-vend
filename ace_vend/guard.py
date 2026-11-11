"""The two-layer hallucination guard.

An LLM can fail in two distinct ways, and conflating them is why most "guard"
implementations miss things:

**Layer 1 — structural.** The output is not a well-formed action. Wrong shape,
unknown verb, wrong argument types, extra keys. Nothing here depends on world
state, so it is pure schema validation.

**Layer 2 — semantic.** The output *is* well-formed but asserts something that
is not true of the world: dispensing an item that is out of stock, restocking
past capacity, pricing below wholesale, or telling the owner a stock count that
contradicts the database. This is the interesting layer — it is where a model
"hallucinates" in a way that would otherwise cost real money.

Every rejection is categorised so the dashboard can show *which* kind of
hallucination was caught.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ace_vend.environment import ACTIONS, Decision
from ace_vend.parsing import extract_json

#: A discount deeper than this is treated as an implausible claim.
MAX_DISCOUNT = 0.5
#: A price more than this multiple of wholesale is treated as implausible.
MAX_MARKUP = 4.0

_KNOWN_ARGS = {
    "dispense": {"sku", "discount_pct"},
    "restock": {"sku", "qty"},
    "set_price": {"sku", "price"},
    "report": {"message"},
    "refuse": {"reason"},
}

_QUANTITY_BEFORE = re.compile(
    r"(\d+)\s*(?:x\s*)?(coke|water|chips|candy|coffee)\b", re.IGNORECASE
)
_QUANTITY_AFTER = re.compile(
    r"\b(coke|water|chips|candy|coffee)\b\D{0,20}?(\d+)\s*(?:units?|left|remaining|in stock)?",
    re.IGNORECASE,
)
_OUT_OF_STOCK_CLAIM = re.compile(
    r"\b(coke|water|chips|candy|coffee)\b\s+(?:is\s+)?(?:out of stock|empty|sold out)",
    re.IGNORECASE,
)


@dataclass
class GuardResult:
    """The guard's verdict on one candidate action."""

    allowed: bool
    decision: Optional[Decision] = None
    violations: List[str] = field(default_factory=list)
    layer: str = ""

    @property
    def blocked(self) -> bool:
        return not self.allowed

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "layer": self.layer,
            "violations": list(self.violations),
            "decision": self.decision.to_dict() if self.decision else None,
        }


class HallucinationGuard:
    """Validates candidate actions against schema and world state."""

    def __init__(self, max_discount: float = MAX_DISCOUNT, max_markup: float = MAX_MARKUP):
        self.max_discount = max_discount
        self.max_markup = max_markup
        self.counts: Counter = Counter()
        self.checked = 0
        self.blocked = 0
        self.log: List[dict] = []

    # ------------------------------------------------------------------ API

    def check(self, raw, env, step: int = 0) -> GuardResult:
        """Validate *raw* (dict, JSON string, or Decision) against *env*."""
        self.checked += 1

        decision, violations = self._structural(raw)
        if violations or decision is None:
            return self._reject("structural", violations, step)

        semantic = self._semantic(decision, env)
        if semantic:
            return self._reject("semantic", semantic, step)

        return GuardResult(allowed=True, decision=decision)

    def reset(self) -> None:
        self.counts.clear()
        self.checked = 0
        self.blocked = 0
        self.log.clear()

    def stats(self) -> dict:
        return {
            "checked": self.checked,
            "blocked": self.blocked,
            "rate": round(self.blocked / self.checked, 3) if self.checked else 0.0,
            "by_category": dict(self.counts),
        }

    # ---------------------------------------------------------- structural

    def _structural(self, raw):
        violations: List[str] = []

        if isinstance(raw, Decision):
            payload = {
                "action": raw.action,
                "args": dict(raw.args),
                "reasoning": raw.reasoning,
                "used_tags": list(raw.used_tags),
            }
        elif isinstance(raw, dict):
            payload = raw
        else:
            parsed = extract_json(raw)
            if parsed is None:
                return None, ["output is not a JSON object"]
            payload = parsed

        action = payload.get("action")
        if not isinstance(action, str) or not action:
            return None, ["missing 'action' field"]
        action = action.strip().lower()
        if action not in ACTIONS:
            return None, [f"unknown action '{action}' (expected one of {', '.join(ACTIONS)})"]

        args = payload.get("args")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return None, ["'args' must be an object"]

        allowed = _KNOWN_ARGS[action]
        extra = set(args) - allowed
        if extra:
            violations.append(f"unexpected argument(s) for '{action}': {', '.join(sorted(extra))}")

        if action == "dispense":
            violations += self._require_sku(args)
            discount = args.get("discount_pct", 0.0)
            if discount is None:
                discount = 0.0
            if not isinstance(discount, (int, float)) or isinstance(discount, bool):
                violations.append("'discount_pct' must be a number")
            elif not 0.0 <= float(discount) <= 1.0:
                violations.append("'discount_pct' must be between 0 and 1")

        elif action == "restock":
            violations += self._require_sku(args)
            qty = args.get("qty")
            if not isinstance(qty, int) or isinstance(qty, bool):
                violations.append("'qty' must be an integer")
            elif not 1 <= qty <= 999:
                violations.append("'qty' must be between 1 and 999")

        elif action == "set_price":
            violations += self._require_sku(args)
            price = args.get("price")
            if not isinstance(price, (int, float)) or isinstance(price, bool):
                violations.append("'price' must be a number")
            elif price <= 0:
                violations.append("'price' must be positive")

        elif action == "report":
            message = args.get("message")
            if not isinstance(message, str) or not message.strip():
                violations.append("'message' must be a non-empty string")
            elif len(message) > 280:
                violations.append("'message' must be at most 280 characters")

        elif action == "refuse":
            reason = args.get("reason", "")
            if reason is not None and not isinstance(reason, str):
                violations.append("'reason' must be a string")
            elif isinstance(reason, str) and len(reason) > 200:
                violations.append("'reason' must be at most 200 characters")

        if violations:
            return None, violations

        reasoning = payload.get("reasoning", "")
        used_tags = payload.get("used_tags", [])
        return (
            Decision(
                action=action,
                args=dict(args),
                reasoning=reasoning if isinstance(reasoning, str) else "",
                used_tags=[t for t in used_tags if isinstance(t, str)]
                if isinstance(used_tags, list)
                else [],
            ),
            [],
        )

    @staticmethod
    def _require_sku(args: dict) -> List[str]:
        sku = args.get("sku")
        if not isinstance(sku, str) or not sku.strip():
            return ["'sku' must be a non-empty string"]
        return []

    # ------------------------------------------------------------ semantic

    def _semantic(self, decision: Decision, env) -> List[str]:
        action = decision.action
        args = decision.args
        catalog = env.catalog
        violations: List[str] = []

        sku = args.get("sku")
        product = catalog.get(sku) if isinstance(sku, str) else None
        if action in ("dispense", "restock", "set_price") and product is None:
            violations.append(f"unknown product '{sku}'")
            return violations

        if action == "dispense":
            if product.stock <= 0:
                violations.append(
                    f"dispense '{product.sku}' but stock is 0 "
                    "(inventory hallucination)"
                )
            discount = float(args.get("discount_pct", 0.0) or 0.0)
            if discount > self.max_discount:
                violations.append(
                    f"discount {discount:.0%} exceeds the {self.max_discount:.0%} ceiling"
                )
            elif discount > 0 and product.price * (1 - discount) < product.cost:
                violations.append(
                    f"discount {discount:.0%} would sell below wholesale cost"
                )

        elif action == "restock":
            space = product.capacity - product.stock
            if space <= 0:
                violations.append(
                    f"restock '{product.sku}' but its slot is already full "
                    f"({product.stock}/{product.capacity})"
                )
            else:
                qty = int(args.get("qty", 0))
                if qty > space:
                    violations.append(
                        f"restock {qty} units of '{product.sku}' but only "
                        f"{space} fit (capacity hallucination)"
                    )
                elif product.cost * qty > env.cash + 1e-9:
                    violations.append(
                        f"restock costs ${product.cost * qty:.2f} but only "
                        f"${env.cash:.2f} is available"
                    )

        elif action == "set_price":
            price = float(args.get("price", 0.0))
            if price < product.cost:
                violations.append(
                    f"price ${price:.2f} is below wholesale cost ${product.cost:.2f}"
                )
            elif price > product.cost * self.max_markup:
                violations.append(
                    f"price ${price:.2f} is implausibly high "
                    f"(>{self.max_markup:.0f}x wholesale)"
                )

        elif action == "report":
            violations += self._check_claims(str(args.get("message", "")), env)

        return violations

    def _check_claims(self, message: str, env) -> List[str]:
        """Catch reports that assert a stock count contradicting the database."""
        violations: List[str] = []
        text = message.lower()

        for match in _QUANTITY_BEFORE.finditer(text):
            qty, sku = int(match.group(1)), match.group(2).lower()
            violations += self._compare_claim(sku, qty, env)

        for match in _QUANTITY_AFTER.finditer(text):
            sku, qty = match.group(1).lower(), int(match.group(2))
            violations += self._compare_claim(sku, qty, env)

        for match in _OUT_OF_STOCK_CLAIM.finditer(text):
            sku = match.group(1).lower()
            product = env.catalog.get(sku)
            if product is not None and product.stock > 0:
                violations.append(
                    f"report claims '{sku}' is out of stock but it has "
                    f"{product.stock} units"
                )

        return violations

    @staticmethod
    def _compare_claim(sku: str, qty: int, env) -> List[str]:
        product = env.catalog.get(sku)
        if product is None or product.stock == qty:
            return []
        return [
            f"report claims {qty} units of '{sku}' but live stock is "
            f"{product.stock} (stock-claim hallucination)"
        ]

    # ------------------------------------------------------------- internal

    def _reject(self, layer: str, violations: List[str], step: int) -> GuardResult:
        self.blocked += 1
        unique: List[str] = []
        for violation in violations:
            if violation not in unique:
                unique.append(violation)
        for violation in unique:
            self.counts[self._category(violation, layer)] += 1
        entry = {"step": step, "layer": layer, "violations": unique}
        self.log.append(entry)
        if len(self.log) > 200:
            self.log = self.log[-200:]
        return GuardResult(allowed=False, decision=None, violations=unique, layer=layer)

    @staticmethod
    def _category(violation: str, layer: str) -> str:
        text = violation.lower()
        if "stock-claim" in text or "claims" in text:
            return "stock_claim"
        if "inventory" in text or "out of stock" in text or "stock is 0" in text:
            return "inventory"
        if "capacity" in text or "already full" in text:
            return "capacity"
        if "price" in text or "discount" in text or "wholesale" in text:
            return "pricing"
        if "cash" in text or "afford" in text or "available" in text:
            return "affordability"
        return "structural" if layer == "structural" else "semantic"
