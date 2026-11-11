"""The vending agent: one step of the ACE loop.

The loop is deliberately explicit, because the order matters:

1. **Perceive** — take the next customer request.
2. **Generate** — ask the backend for an action, with the playbook in context.
3. **Guard** — validate it structurally and semantically. A blocked action is
   never executed; a safe ``refuse`` is substituted so the simulation keeps
   running.
4. **Act** — apply the action to the environment and collect the reward.
5. **Credit** — bump ``helpful`` / ``harmful`` on the bullets that were used.
6. **Reflect** — distil lessons from the episode.
7. **Curate** — merge, deduplicate and prune the playbook.

Steps 6–7 are skipped in ``static`` and ``baseline`` modes.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from ace_vend.backends import Backend, BulletCandidate, Episode, get_backend
from ace_vend.config import Settings, get_settings
from ace_vend.environment import (
    Decision,
    Request,
    RequestStream,
    VendingEnvironment,
)
from ace_vend.guard import GuardResult, HallucinationGuard
from ace_vend.playbook import Playbook, static_playbook
from ace_vend.roles import Curator, Generator, Reflector

MODES = ("baseline", "static", "ace")

_DISCOUNT_RE = re.compile(r"(\d{1,2})\s*%")
_COMPLAINT_WORDS = ("ate my money", "broken", "fault", "refund", "stuck", "jammed")


class VendingAgent:
    """Owns the environment, the playbook, the guard and the three roles."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        backend: Optional[Backend] = None,
        playbook: Optional[Playbook] = None,
        guard: Optional[HallucinationGuard] = None,
        mode: str = "ace",
        seed: Optional[int] = None,
    ):
        self.settings = settings or get_settings()
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
        self.mode = mode

        self.seed = self.settings.seed if seed is None else seed
        self.env = VendingEnvironment(seed=self.seed)
        self.stream = RequestStream(seed=self.seed, catalog=self.env.catalog)

        self.playbook = playbook or self._initial_playbook()
        self.guard = guard or HallucinationGuard()
        self.backend = backend or get_backend(self.settings)

        self.generator = Generator(self.backend)
        self.reflector = Reflector(self.backend, rounds=self.settings.reflector_rounds)
        self.curator = Curator(self.playbook, every=self.settings.curator_every)

        self.episodes: List[Episode] = []
        self.records: List[dict] = []
        self.learned: List[dict] = []

    # ------------------------------------------------------------------ setup

    def _initial_playbook(self) -> Playbook:
        kwargs = dict(
            max_bullets=self.settings.max_bullets,
            token_budget=self.settings.bullet_token_budget,
            dedup_threshold=self.settings.dedup_threshold,
        )
        if self.mode == "static":
            return static_playbook(**kwargs)
        return Playbook(**kwargs)

    @property
    def curating(self) -> bool:
        return self.mode == "ace"

    def reset(self, seed: Optional[int] = None) -> None:
        if seed is not None:
            self.seed = seed
        self.env.reset()
        self.stream = RequestStream(seed=self.seed, catalog=self.env.catalog)
        self.guard.reset()
        if self.mode == "ace":
            self.curator.reset()
        else:
            # Static and baseline must not inherit a learned playbook.
            self.playbook = self._initial_playbook()
            self.curator = Curator(self.playbook, every=self.settings.curator_every)
        self.episodes.clear()
        self.records.clear()
        self.learned.clear()

    # ------------------------------------------------------------------- step

    def step(self, customer_text: Optional[str] = None) -> dict:
        request = (
            self.parse_customer_text(customer_text)
            if customer_text
            else self.stream.next()
        )
        self.env.begin_step(request)
        step_no = self.env.step + 1

        was_empty = bool(
            request.kind in ("buy", "discount")
            and request.sku
            and self.env.catalog[request.sku].stock == 0
        )

        proposed = self.generator.act(self.env, request, self.playbook)
        verdict: GuardResult = self.guard.check(proposed, self.env, step_no)

        if verdict.allowed and verdict.decision is not None:
            executed = verdict.decision
            outcome = self.env.apply(executed)
            allowed = True
        else:
            executed = None
            allowed = False
            reason = "; ".join(verdict.violations)[:180] or "invalid action"
            outcome = self.env.apply(
                Decision("refuse", {"reason": f"blocked by guard: {reason}"})
            )

        episode = Episode(
            step=step_no,
            request=request,
            proposed=proposed,
            executed=executed,
            allowed=allowed,
            violations=verdict.violations,
            outcome_message=outcome.message,
            event=outcome.event,
            reward=outcome.reward,
            stockout=was_empty,
        )
        self.episodes.append(episode)

        # Credit the bullets that shaped the decision.
        if proposed.used_tags:
            positive = allowed and outcome.ok
            self.curator.credit(proposed.used_tags, positive)

        # Reflect and curate only when the mode learns.
        new_bullets: List[dict] = []
        if self.curating and self.curator.should_curate(step_no):
            known = {b.id for b in self.playbook.bullets}
            candidates: List[BulletCandidate] = self.reflector.reflect(
                episode, self.env, self.playbook
            )
            touched, _evicted = self.curator.curate(candidates, step_no)
            # Only surface genuinely new bullets; a merge still updates the
            # existing bullet's counters but is not a new lesson.
            new_bullets = [b.to_dict() for b in touched if b.id not in known]
            for bullet in new_bullets:
                self.learned.append({"step": step_no, **bullet})

        record = {
            "step": step_no,
            "request": request.to_dict(),
            "proposed": proposed.to_dict(),
            "decision": executed.to_dict() if executed else None,
            "guard": verdict.to_dict(),
            "outcome": outcome.to_dict(),
            "allowed": allowed,
            "reward": round(outcome.reward, 2),
            "profit": self.env.profit,
            "cash": round(self.env.cash, 2),
            "learned": new_bullets,
        }
        self.records.append(record)
        self.env.record(
            {
                "step": step_no,
                "profit": self.env.profit,
                "cash": round(self.env.cash, 2),
                "revenue": round(self.env.revenue, 2),
                "spend": round(self.env.spend, 2),
                "stock": self.env.total_stock(),
                "bullets": len(self.playbook.bullets),
                "tokens": self.playbook.tokens,
            }
        )
        return record

    # ------------------------------------------------------------------ views

    def parse_customer_text(self, text: str) -> Request:
        """Turn free-text customer input from the UI into a Request."""
        text = (text or "").strip()
        lowered = text.lower()

        sku = None
        for key, product in self.env.catalog.items():
            if key in lowered or product.name.lower() in lowered:
                sku = key
                break

        if any(word in lowered for word in _COMPLAINT_WORDS):
            return Request(kind="complaint", text=text or "The machine is faulty.")

        if "discount" in lowered or "%" in lowered or "off" in lowered:
            match = _DISCOUNT_RE.search(lowered)
            pct = (int(match.group(1)) / 100.0) if match else 0.2
            pct = max(0.05, min(pct, 0.5))
            return Request(
                kind="discount",
                sku=sku,
                discount_pct=pct,
                text=text or "Can I get a discount?",
            )

        if sku:
            return Request(kind="buy", sku=sku, text=text)

        return Request(kind="browse", text=text or "What have you got?")

    def metrics(self) -> Dict[str, object]:
        env = self.env
        return {
            "mode": self.mode,
            "backend": getattr(self.backend, "name", "unknown"),
            "step": env.step,
            "profit": env.profit,
            "revenue": round(env.revenue, 2),
            "spend": round(env.spend, 2),
            "cash": round(env.cash, 2),
            "units_sold": env.units_sold,
            "requests": env.requests,
            "fulfilled": env.fulfilled,
            "refused": env.refused,
            "stockouts": env.stockouts,
            "service_rate": env.service_rate,
            "reports": env.reports,
            "guard": self.guard.stats(),
            "playbook": self.playbook.stats(),
        }

    def state(self) -> dict:
        return {
            "mode": self.mode,
            "seed": self.seed,
            "settings": self.settings.describe(),
            "environment": self.env.snapshot(),
            "playbook": self.playbook.to_dict(),
            "guard": self.guard.stats(),
            "metrics": self.metrics(),
            "records": self.records[-40:],
            "learned": self.learned[-20:],
        }
