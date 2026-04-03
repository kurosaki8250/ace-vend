# backend/ace_integration.py — Official ACE wrapper + lightweight fallback
#
# The official ACE library (pip install ace-python) requires a cloud API
# provider. When running locally with a HuggingFace model, we fall back
# to LightweightACE, which implements the same three-role architecture
# (Generator → Reflector → Curator) with identical playbook format.

import logging
import re
from config import (
    USE_OFFICIAL_ACE, FALLBACK_TO_LIGHTWEIGHT,
    ACE_MAX_ROUNDS, PLAYBOOK_TOKEN_BUDGET
)
from backend.utils import generate, extract_json
from backend.playbook_manager import PlaybookManager, SECTIONS

log = logging.getLogger(__name__)

# ── Prompt templates ─────────────────────────────────────────────────────────

GENERATOR_TEMPLATE = """\
You are the manager of a vending machine. Manage it profitably and honestly.

## ACE PLAYBOOK
{playbook}

## CURRENT STATE
{state}

## CUSTOMER REQUEST
{customer}

Respond with exactly two lines:
REASONING: <one sentence>
ACTION: {{"type": "<action>", ...}}

Valid action types: check_inventory, dispense, contact_owner, contact_technician, restock, report_issue, idle
For dispense include "item" and "payment". For restock include "item" and "quantity".
"""

REFLECTOR_TEMPLATE = """\
You are the ACE Reflector. Evaluate the agent's last action.

STATE BEFORE: {state_before}
ACTION: {action}
OUTCOME: {outcome}

Respond with exactly three lines:
LABEL: <helpful|harmful|neutral>
INSIGHT: <one sentence what was learned>
SECTION: <strategies|mistakes|reporting>
"""


# ── Lightweight ACE ──────────────────────────────────────────────────────────

class LightweightACE:
    """
    Three-role ACE implementation for local HuggingFace models.
    Generator → Reflector → Curator pipeline.
    """

    def __init__(self, playbook: PlaybookManager):
        self.playbook = playbook

    # ── Generator ────────────────────────────────────────────────────────────

    def generate_action(self, state: dict, customer: str = "") -> dict:
        import json
        playbook_text = self.playbook.render(PLAYBOOK_TOKEN_BUDGET)
        prompt = GENERATOR_TEMPLATE.format(
            playbook=playbook_text or "(empty — build it up!)",
            state=json.dumps(state, indent=2),
            customer=customer or "None",
        )
        raw = generate(prompt)
        log.debug("Generator raw output: %s", raw[:200])

        # Parse ACTION line
        action = None
        for line in raw.splitlines():
            if line.strip().startswith("ACTION:"):
                json_part = line.split("ACTION:", 1)[1].strip()
                action = extract_json(json_part)
                break
        if action is None:
            action = extract_json(raw)
        if action is None:
            log.warning("Generator produced no valid JSON; defaulting to idle.")
            action = {"type": "idle", "reason": "Parse failure."}

        # Extract reasoning
        reasoning = ""
        for line in raw.splitlines():
            if line.strip().startswith("REASONING:"):
                reasoning = line.split("REASONING:", 1)[1].strip()
                break

        return {"action": action, "reasoning": reasoning, "raw": raw}

    # ── Reflector ────────────────────────────────────────────────────────────

    def reflect(self, state_before: dict, action: dict, outcome: dict) -> dict:
        import json
        prompt = REFLECTOR_TEMPLATE.format(
            state_before=json.dumps(state_before, indent=2),
            action=json.dumps(action),
            outcome=json.dumps(outcome),
        )
        raw = generate(prompt)
        log.debug("Reflector raw output: %s", raw[:200])

        label, insight, section = "neutral", "", SECTIONS[0]
        for line in raw.splitlines():
            ls = line.strip()
            if ls.startswith("LABEL:"):
                label = ls.split(":", 1)[1].strip().lower()
                if label not in ("helpful", "harmful", "neutral"):
                    label = "neutral"
            elif ls.startswith("INSIGHT:"):
                insight = ls.split(":", 1)[1].strip()
            elif ls.startswith("SECTION:"):
                raw_section = ls.split(":", 1)[1].strip().lower()
                if "mistake" in raw_section:
                    section = SECTIONS[1]
                elif "report" in raw_section:
                    section = SECTIONS[2]
                else:
                    section = SECTIONS[0]

        return {"label": label, "insight": insight, "section": section, "raw": raw}

    # ── Curator (deterministic) ───────────────────────────────────────────────

    def curate(self, reflection: dict) -> dict | None:
        """Merge Reflector output into the playbook as a delta bullet."""
        insight = reflection.get("insight", "").strip()
        if not insight:
            return None
        label = reflection.get("label", "neutral")
        section = reflection.get("section", SECTIONS[0])
        bullet = self.playbook.add_or_update(insight, label, section)
        return {"bullet_idx": bullet.idx, "score": bullet.score, "text": bullet.text}


# ── Official ACE Wrapper ─────────────────────────────────────────────────────

class OfficialACEWrapper:
    """
    Wraps the official `ace` library if available; transparently falls back
    to LightweightACE when the library is missing or a local model is in use.
    """

    def __init__(self, playbook: PlaybookManager):
        self._delegate = None
        self._is_official = False
        self._playbook = playbook
        if USE_OFFICIAL_ACE:
            self._try_init_official()
        if self._delegate is None and FALLBACK_TO_LIGHTWEIGHT:
            log.info("Using LightweightACE fallback.")
            self._delegate = LightweightACE(playbook)

    def _try_init_official(self):
        try:
            from ace import ACE  # noqa: F401 — optional dependency
            # Official ACE requires an API provider; swap in credentials here:
            # self._delegate = ACE(api_provider="openai", ...)
            log.warning("Official ACE library found but no API provider configured. Falling back.")
        except ImportError:
            log.info("Official ACE library not installed; using lightweight implementation.")

    # Delegate all calls to whichever implementation is active

    def generate_action(self, state: dict, customer: str = "") -> dict:
        return self._delegate.generate_action(state, customer)

    def reflect(self, state_before: dict, action: dict, outcome: dict) -> dict:
        return self._delegate.reflect(state_before, action, outcome)

    def curate(self, reflection: dict) -> dict | None:
        return self._delegate.curate(reflection)
