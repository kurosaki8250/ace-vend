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

        # MAJOR 4 fix: Improved JSON extraction for multi-line output
        # Parse ACTION line by reading all lines until another label or end
        action = None
        lines = raw.splitlines()
        in_action_block = False
        action_lines = []
        
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("ACTION:"):
                in_action_block = True
                # Get any JSON on the same line after ACTION:
                json_part = stripped.split("ACTION:", 1)[1].strip()
                if json_part:
                    action_lines.append(json_part)
            elif in_action_block:
                # Check if we've hit another label (end of ACTION block)
                if any(stripped.startswith(lbl) for lbl in ["REASONING:", "LABEL:", "INSIGHT:", "REFLECTION:"]):
                    break
                # Continue collecting action lines
                action_lines.append(stripped)
        
        # Try to parse the collected action lines
        if action_lines:
            action_text = "\n".join(action_lines)
            action = extract_json(action_text)
        
        # Fallback: try extracting from entire raw output
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

    # ── Curator (LLM-based) ───────────────────────────────────────────────────

    def curate(self, reflection: dict) -> dict | None:
        """
        MAJOR 5 fix: Curator is now an LLM call that critiques and synthesizes.
        
        The Curator receives the reflection and current playbook, and decides
        whether to add, modify, or discard the insight. It checks for contradictions
        with existing bullets and resolves them.
        """
        from backend.utils import generate
        
        insight = reflection.get("insight", "").strip()
        if not insight:
            return None
        
        label = reflection.get("label", "neutral")
        section = reflection.get("section", SECTIONS[0])
        
        # Get current playbook text for context
        playbook_text = self.playbook.render(PLAYBOOK_TOKEN_BUDGET)
        
        # Build curator prompt
        curator_prompt = f"""You are the ACE Curator. Your job is to decide whether to add a new insight to the playbook.

CURRENT PLAYBOOK:
{playbook_text or "(empty)"}

NEW INSIGHT TO EVALUATE:
- Label: {label}
- Section: {section}
- Content: {insight}

Respond with exactly two lines:
DECISION: <add|discard|modify>
REASON: <one sentence explaining your decision>

Guidelines:
- ADD if the insight is novel and doesn't contradict existing bullets.
- DISCARD if it contradicts a higher-scored bullet or is redundant.
- MODIFY if it needs refinement to align with existing knowledge.
"""
        
        try:
            raw_response = generate(curator_prompt, max_new_tokens=64)
            log.debug("Curator raw output: %s", raw_response[:200])
            
            # Parse decision
            decision = "add"  # default
            reason = ""
            for line in raw_response.splitlines():
                ls = line.strip()
                if ls.startswith("DECISION:"):
                    decision = ls.split(":", 1)[1].strip().lower()
                elif ls.startswith("REASON:"):
                    reason = ls.split(":", 1)[1].strip()
            
            # Apply decision
            if decision == "discard":
                log.info("Curator discarded insight: %s (reason: %s)", insight[:50], reason)
                return {"bullet_idx": None, "score": None, "text": insight, "decision": "discarded", "reason": reason}
            
            elif decision == "modify":
                # For modify, we still add but with lower initial score
                log.info("Curator modified insight: %s (reason: %s)", insight[:50], reason)
                # Add with helpful=0 to start (will need validation)
                bullet = self.playbook.add_or_update(insight, "neutral", section)
                return {"bullet_idx": bullet.idx, "score": bullet.score, "text": bullet.text, "decision": "modified", "reason": reason}
            
            else:  # add
                log.info("Curator added insight: %s", insight[:50])
                bullet = self.playbook.add_or_update(insight, label, section)
                return {"bullet_idx": bullet.idx, "score": bullet.score, "text": bullet.text, "decision": "added", "reason": reason}
                
        except Exception as exc:
            log.error("Curator LLM call failed (%s), falling back to deterministic add", exc)
            # Fallback to deterministic behavior
            bullet = self.playbook.add_or_update(insight, label, section)
            return {"bullet_idx": bullet.idx, "score": bullet.score, "text": bullet.text, "decision": "added (fallback)"}


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
