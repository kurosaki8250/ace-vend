# backend/agent.py — Main agent loop: perceive → think → act → reflect

import logging
from config import REPORT_EVERY_N_STEPS, ACE_MAX_ROUNDS, CURATOR_FREQUENCY
from backend.environment import VendingEnvironment
from backend.playbook_manager import PlaybookManager
from backend.ace_integration import OfficialACEWrapper

log = logging.getLogger(__name__)


class VendingAgent:
    """
    Orchestrates the perceive → generate → act → reflect → curate cycle.
    One call to step() runs a full cycle and returns a structured event dict
    consumed by the Flask SSE stream.
    """

    def __init__(self):
        self.env = VendingEnvironment()
        self.playbook = PlaybookManager()
        self.ace = OfficialACEWrapper(self.playbook)
        self._step_count = 0

    # ── Public API ───────────────────────────────────────────────────────────

    def step(self, customer_request: str = "") -> dict:
        """Run one full agent decision cycle. Returns an event dict."""
        state_before = self.env.observe()

        # Generate action
        gen_result = self.ace.generate_action(state_before, customer_request)
        action = gen_result["action"]
        reasoning = gen_result["reasoning"]

        # Hallucination guard: validate before execution
        guard_result = self._hallucination_guard(action, state_before)
        if not guard_result["pass"]:
            log.warning("HallucinationGuard blocked: %s", guard_result["reason"])
            action = {"type": "idle", "reason": f"Blocked: {guard_result['reason']}"}

        # Execute action
        outcome = self.env.step_action(action)
        self._step_count += 1

        # Reflect (ACE Reflector)
        reflection = self.ace.reflect(state_before, action, outcome)

        # Curate (ACE Curator) — every CURATOR_FREQUENCY steps
        curator_result = None
        if self._step_count % CURATOR_FREQUENCY == 0:
            curator_result = self.ace.curate(reflection)

        # Periodic owner report
        owner_report = None
        if self._step_count % REPORT_EVERY_N_STEPS == 0:
            owner_report = self._build_owner_report()

        return {
            "step": self.env.step,
            "state": self.env.observe(),
            "reasoning": reasoning,
            "action": action,
            "outcome": outcome,
            "hallucination": not guard_result["pass"],
            "reflection": reflection,
            "curator": curator_result,
            "playbook_count": self.playbook.count(),
            "owner_report": owner_report,
        }

    def get_state(self) -> dict:
        return {
            "env": self.env.observe(),
            "playbook": self.playbook.all_bullets(),
            "playbook_count": self.playbook.count(),
            "total_hallucinations": self.env.hallucination_events,
        }

    def reset(self):
        self.env.reset()
        self._step_count = 0
        log.info("Agent reset.")

    # ── Hallucination Guard ──────────────────────────────────────────────────

    def _hallucination_guard(self, action: dict, state: dict) -> dict:
        """
        Layer 1: structural — action must have a known type.
        Layer 2: semantic — dispense target must exist and be in stock.
        """
        valid_types = {
            "check_inventory", "dispense", "contact_owner",
            "contact_technician", "restock", "report_issue", "idle"
        }
        if action.get("type") not in valid_types:
            return {"pass": False, "reason": f"Unknown action type: {action.get('type')}"}

        if action.get("type") == "dispense":
            item = action.get("item", "")
            inventory = state.get("inventory", {})
            if item not in inventory:
                return {"pass": False, "reason": f"Item '{item}' not in inventory."}
            if inventory[item] <= 0:
                return {"pass": False, "reason": f"'{item}' is out of stock (qty=0)."}

        return {"pass": True, "reason": ""}

    # ── Owner Report ─────────────────────────────────────────────────────────

    def _build_owner_report(self) -> str:
        state = self.env.observe()
        low = state.get("low_stock", [])
        report = (
            f"[Step {self.env.step}] Owner Report — "
            f"Cash: ${state['cash']:.2f} | "
            f"Status: {state['status']} | "
            f"Hallucinations: {self.env.hallucination_events} | "
            f"Playbook bullets: {self.playbook.count()}"
        )
        if low:
            report += f" | LOW STOCK: {', '.join(low)}"
        return report
