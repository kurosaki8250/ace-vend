"""Decision backends: the agent's "brain".

Three implementations share one interface:

``OfflineBackend``
    A deterministic heuristic policy. It is the default so the project runs
    with **zero setup and no downloads**. It reads the same playbook the LLM
    would read — specifically the machine-readable ``tag`` on each bullet — so
    the self-improvement loop is real and measurable without a GPU.

``OpenAIBackend``
    Any OpenAI-compatible chat-completions endpoint. Reads the rendered bullet
    text, so it benefits from the same evolving context.

``OllamaBackend``
    A local model through Ollama's ``/api/chat``.

The offline backend is not a mock: it is a *surrogate*. Its baseline policy has
deliberate, realistic weaknesses (it only restocks once a slot is already empty,
it grants any discount a customer asks for, and it reports invented stock
counts). Those are exactly the failures the Reflector can learn from, so the
playbook measurably changes behaviour.

Both roles are implemented per backend:

* :meth:`Backend.decide` — the **Generator**.
* :meth:`Backend.reflect` — the **Reflector**.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Optional

from ace_vend.config import Settings
from ace_vend.environment import Decision, Product, Request, VendingEnvironment
from ace_vend.parsing import extract_json
from ace_vend.playbook import Playbook


@dataclass
class BulletCandidate:
    """A lesson proposed by the Reflector, before the Curator merges it."""

    text: str
    section: str = "STRATEGIES"
    tag: Optional[str] = None
    harmful: bool = False

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "section": self.section,
            "tag": self.tag,
            "harmful": self.harmful,
        }


@dataclass
class Episode:
    """Everything the Reflector needs to reason about one step."""

    step: int
    request: Request
    proposed: Optional[Decision]
    executed: Optional[Decision]
    allowed: bool
    violations: List[str]
    outcome_message: str
    event: str
    reward: float
    stockout: bool = False

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "request": self.request.to_dict(),
            "proposed": self.proposed.to_dict() if self.proposed else None,
            "executed": self.executed.to_dict() if self.executed else None,
            "allowed": self.allowed,
            "violations": list(self.violations),
            "outcome_message": self.outcome_message,
            "event": self.event,
            "reward": round(self.reward, 2),
            "stockout": self.stockout,
        }

    def as_text(self) -> str:
        request = self.request
        proposed = self.proposed.action if self.proposed else "none"
        executed = self.executed.action if self.executed else "none"
        return (
            f"Step {self.step}\n"
            f"Customer ({request.kind}): {request.text}\n"
            f"Proposed action: {proposed}\n"
            f"Guard allowed: {self.allowed}"
            + (f" (violations: {'; '.join(self.violations)})" if self.violations else "")
            + f"\nExecuted action: {executed}\n"
            f"Outcome: {self.outcome_message} (reward ${self.reward:.2f})"
        )


# --------------------------------------------------------------------------- #
# Backend interface
# --------------------------------------------------------------------------- #


class Backend:
    """Interface every decision backend implements."""

    name = "base"

    def decide(
        self,
        env: VendingEnvironment,
        request: Request,
        playbook: Playbook,
    ) -> Decision:  # pragma: no cover - interface
        raise NotImplementedError

    def reflect(
        self,
        episode: Episode,
        env: VendingEnvironment,
        playbook: Playbook,
    ) -> List[BulletCandidate]:  # pragma: no cover - interface
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Offline surrogate
# --------------------------------------------------------------------------- #


class OfflineBackend(Backend):
    """Deterministic policy that consumes playbook tags."""

    name = "offline"

    #: How many units a naive agent tries to buy at once.
    NAIVE_BATCH = 4
    #: Stock above this level after a restock is treated as overstock.
    OVERSTOCK_LEVEL = 8

    def __init__(self) -> None:
        self.name = "offline"

    # ------------------------------------------------------------- generate

    def decide(
        self,
        env: VendingEnvironment,
        request: Request,
        playbook: Playbook,
    ) -> Decision:
        knobs = playbook.knobs()
        used = self._used_tags(knobs)

        restock_threshold = int(knobs.get("restock_threshold", 0) or 0)
        restock_target = int(knobs.get("restock_target", 0) or 0)
        allow_discount = bool(knobs.get("allow_discount", True))
        capacity_aware = bool(knobs.get("capacity_aware", False))
        truthful_reports = bool(knobs.get("truthful_reports", False))

        if request.kind in ("buy", "discount"):
            product = env.catalog[request.sku]
            if product.stock > 0:
                discount = 0.0
                if request.kind == "discount" and allow_discount:
                    discount = request.discount_pct
                reason = f"{product.name} is in stock ({product.stock} left)."
                if discount:
                    reason += f" Granting the requested {discount:.0%} discount."
                return Decision(
                    "dispense",
                    {"sku": product.sku, "discount_pct": discount},
                    reasoning=reason,
                    used_tags=used,
                )

            qty = self._restock_qty(env, product, capacity_aware, restock_target)
            if qty > 0:
                return Decision(
                    "restock",
                    {"sku": product.sku, "qty": qty},
                    reasoning=f"{product.name} is empty; buying {qty} units to serve the queue.",
                    used_tags=used,
                )
            return Decision(
                "refuse",
                {"reason": f"{product.name} is out of stock and cash is too low to restock."},
                reasoning="Nothing can be sold and nothing can be restocked.",
                used_tags=used,
            )

        if request.kind == "browse":
            target = self._most_depleted(env, restock_threshold)
            if target is not None:
                qty = self._restock_qty(env, target, capacity_aware, restock_target)
                if qty > 0:
                    return Decision(
                        "restock",
                        {"sku": target.sku, "qty": qty},
                        reasoning=(
                            f"Idle moment: {target.name} is at {target.stock} units, "
                            f"at or below the {restock_threshold}-unit threshold."
                        ),
                        used_tags=used,
                    )
            return Decision(
                "report",
                {"message": self._inventory_report(env, truthful_reports)},
                reasoning="No sale to serve; sending the owner an inventory summary.",
                used_tags=used,
            )

        # complaint
        return Decision(
            "report",
            {"message": f"Customer complaint: {request.text}"},
            reasoning="Acknowledge the complaint and escalate it to the owner.",
            used_tags=used,
        )

    # -------------------------------------------------------------- reflect

    def reflect(
        self,
        episode: Episode,
        env: VendingEnvironment,
        playbook: Playbook,
    ) -> List[BulletCandidate]:
        lessons: List[BulletCandidate] = []

        if not episode.allowed:
            joined = " ".join(episode.violations).lower()
            if "stock is 0" in joined or "inventory" in joined or "out of stock" in joined:
                lessons.append(BulletCandidate(
                    "Never dispense a product with zero stock; verify inventory before acting.",
                    "MISTAKES", "verify_stock=true",
                ))
            if "capacity" in joined or "already full" in joined:
                lessons.append(BulletCandidate(
                    "Restock only up to the remaining slot capacity; never overfill.",
                    "MISTAKES", "capacity_aware=true",
                ))
            if "price" in joined or "discount" in joined or "wholesale" in joined:
                lessons.append(BulletCandidate(
                    "Never grant discounts; they destroy the margin on every sale.",
                    "MISTAKES", "allow_discount=false",
                ))
            if "stock-claim" in joined or "claims" in joined:
                lessons.append(BulletCandidate(
                    "Report only inventory counts read from live state; never invent a number.",
                    "REPORTING", "truthful_reports=true",
                ))
            if "json" in joined or "unknown action" in joined or "argument" in joined:
                lessons.append(BulletCandidate(
                    "Emit one JSON object with an allowed action and correctly typed arguments.",
                    "MISTAKES", None,
                ))
            if "cash" in joined or "afford" in joined:
                lessons.append(BulletCandidate(
                    "Never restock more than the cash balance can cover.",
                    "MISTAKES", "capacity_aware=true",
                ))

        request = episode.request
        outcome = episode.outcome_message.lower()

        if episode.stockout:
            lessons.append(BulletCandidate(
                "Restock any product at or below 4 units before serving the next customer.",
                "STRATEGIES", "restock_threshold=4",
            ))

        if (
            request.kind == "discount"
            and episode.event == "sold"
            and episode.executed is not None
            and float(episode.executed.args.get("discount_pct", 0) or 0) > 0
        ):
            lessons.append(BulletCandidate(
                "Never grant discounts; they destroy the margin on every sale.",
                "MISTAKES", "allow_discount=false",
            ))

        if episode.event == "restocked" and episode.executed is not None:
            sku = episode.executed.args.get("sku")
            product = env.catalog.get(sku) if isinstance(sku, str) else None
            if product is not None and product.stock > self.OVERSTOCK_LEVEL:
                lessons.append(BulletCandidate(
                    "Restock to about 8 units, not the full slot; unsold stock is dead capital.",
                    "STRATEGIES", "restock_target=8",
                ))

        if episode.event == "refused" and request.kind in ("buy", "discount"):
            product = env.catalog.get(request.sku or "")
            if product is not None and product.stock > 0:
                lessons.append(BulletCandidate(
                    "Serve the waiting customer before doing maintenance work.",
                    "STRATEGIES", None,
                ))

        if request.kind == "complaint" and episode.event != "reported":
            lessons.append(BulletCandidate(
                "Always acknowledge a customer complaint by reporting it to the owner.",
                "REPORTING", None,
            ))

        return lessons

    # ------------------------------------------------------------ internals

    @staticmethod
    def _used_tags(knobs: dict) -> List[str]:
        return [
            f"{key}={value}".lower()
            for key, value in knobs.items()
        ]

    def _restock_qty(
        self,
        env: VendingEnvironment,
        product: Product,
        capacity_aware: bool,
        restock_target: int = 0,
    ) -> int:
        space = product.capacity - product.stock
        if space <= 0:
            return 0

        if restock_target > 0:
            # A target level leaves room for demand without tying up cash in
            # stock that will never sell inside the run.
            wanted = max(0, restock_target - product.stock)
        else:
            # Naive agent: "the slot should be full", ignoring what is already
            # in it. The guard rejects the overfill, so the top-up never lands.
            wanted = product.capacity

        affordable = int(env.cash / product.cost) if product.cost else 0
        qty = min(wanted, affordable)
        if capacity_aware:
            qty = min(qty, space)
        return max(0, qty)

    @staticmethod
    def _most_depleted(env: VendingEnvironment, threshold: int) -> Optional[Product]:
        if threshold <= 0:
            return None
        candidates = [p for p in env.catalog.values() if p.stock <= threshold]
        if not candidates:
            return None
        return min(candidates, key=lambda p: (p.stock, -p.popularity))

    @staticmethod
    def _inventory_report(env: VendingEnvironment, truthful: bool) -> str:
        if truthful:
            parts = [f"{p.sku}: {p.stock}/{p.capacity}" for p in env.catalog.values()]
            return "Inventory — " + ", ".join(parts)
        # Deliberately stale: the naive agent reports what it remembers, not
        # what it can see. The guard catches the mismatch.
        return (
            "Inventory — coke: 5 units left, water: 5 units left, "
            "chips: 4 units left, candy: 4 units left, coffee: 3 units left"
        )


# --------------------------------------------------------------------------- #
# Language-model backends
# --------------------------------------------------------------------------- #

_SYSTEM = """You operate a vending machine for profit.

Allowed actions (reply with exactly one JSON object):
  {"action": "dispense",  "args": {"sku": "<sku>", "discount_pct": <0.0-0.5>}}
  {"action": "restock",   "args": {"sku": "<sku>", "qty": <integer>}}
  {"action": "set_price", "args": {"sku": "<sku>", "price": <number>}}
  {"action": "report",    "args": {"message": "<max 280 chars>"}}
  {"action": "refuse",    "args": {"reason": "<text>"}}

Rules:
- Never dispense a product whose stock is 0.
- Never restock more than the free space in the slot.
- Never price or discount below wholesale cost.
- When you report inventory, use only the counts in the state below.

Reply with JSON only. No prose, no markdown fences."""

_REFLECT_SYSTEM = """You are the Reflector in an Agentic Context Engineering loop.

Read one episode from a vending-machine agent and propose at most 3 short,
general lessons that would improve future decisions.

Reply with a JSON array only:
[{"text": "<one sentence>", "section": "STRATEGIES|MISTAKES|REPORTING"}]

Do not restate the episode. Do not propose more than 3 lessons."""


class _ChatBackend(Backend):
    """Shared prompt construction and reflection parsing for LLM backends."""

    name = "chat"

    def _build_prompt(
        self,
        env: VendingEnvironment,
        request: Request,
        playbook: Playbook,
    ) -> str:
        return (
            f"PLAYBOOK\n{playbook.render()}\n\n"
            f"STATE\n{env.prompt_state()}\n\n"
            f"CUSTOMER ({request.kind}): {request.text}\n\n"
            "What is your single next action?"
        )

    def _parse_decision(self, raw: str) -> Decision:
        payload = extract_json(raw) or {}
        action = payload.get("action", "refuse")
        args = payload.get("args", {})
        if not isinstance(args, dict):
            args = {}
        reasoning = payload.get("reasoning", "")
        return Decision(
            action=str(action).strip().lower(),
            args=args,
            reasoning=reasoning if isinstance(reasoning, str) else "",
        )

    def _parse_lessons(self, raw: str) -> List[BulletCandidate]:
        text = raw.strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("["), text.rfind("]")
            if start == -1 or end <= start:
                return []
            try:
                payload = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return []
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            return []

        lessons: List[BulletCandidate] = []
        for item in payload[:3]:
            if not isinstance(item, dict):
                continue
            lesson = str(item.get("text", "")).strip()
            if not lesson:
                continue
            section = str(item.get("section", "STRATEGIES")).upper()
            if section not in ("STRATEGIES", "MISTAKES", "REPORTING"):
                section = "STRATEGIES"
            tag = item.get("tag")
            lessons.append(
                BulletCandidate(lesson, section, tag if isinstance(tag, str) else None)
            )
        return lessons


class OpenAIBackend(_ChatBackend):
    """Any OpenAI-compatible chat-completions endpoint."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.name = "openai"

    def _chat(self, system: str, user: str) -> str:
        import requests  # imported lazily so offline mode has no dependency

        if not self.settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Use LLM_BACKEND=offline or provide a key."
            )
        response = requests.post(
            f"{self.settings.openai_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": self.settings.temperature,
                "max_tokens": self.settings.max_tokens,
            },
            timeout=self.settings.request_timeout,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def decide(self, env, request, playbook) -> Decision:
        raw = self._chat(_SYSTEM, self._build_prompt(env, request, playbook))
        return self._parse_decision(raw)

    def reflect(self, episode, env, playbook) -> List[BulletCandidate]:
        raw = self._chat(_REFLECT_SYSTEM, episode.as_text())
        return self._parse_lessons(raw)


class OllamaBackend(_ChatBackend):
    """A local model served by Ollama."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.name = "ollama"

    def _chat(self, system: str, user: str) -> str:
        import requests

        response = requests.post(
            f"{self.settings.ollama_url.rstrip('/')}/api/chat",
            json={
                "model": self.settings.ollama_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {"temperature": self.settings.temperature},
            },
            timeout=self.settings.request_timeout,
        )
        response.raise_for_status()
        return response.json().get("message", {}).get("content", "")

    def decide(self, env, request, playbook) -> Decision:
        raw = self._chat(_SYSTEM, self._build_prompt(env, request, playbook))
        return self._parse_decision(raw)

    def reflect(self, episode, env, playbook) -> List[BulletCandidate]:
        raw = self._chat(_REFLECT_SYSTEM, episode.as_text())
        return self._parse_lessons(raw)


def get_backend(settings: Settings):
    """Construct the backend named by ``settings.backend``."""
    name = (settings.backend or "offline").lower()
    if name in ("openai", "openai-compatible", "api"):
        return OpenAIBackend(settings)
    if name == "ollama":
        return OllamaBackend(settings)
    return OfflineBackend()
