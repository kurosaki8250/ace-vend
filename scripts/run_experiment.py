#!/usr/bin/env python3
"""
scripts/run_experiment.py
─────────────────────────
Runs the three experimental conditions from the ACE-Vend paper:
  B   — Baseline (no playbook)
  SP  — Static Playbook
  ACE — Full ACE agent with evolving playbook

Usage:
    python scripts/run_experiment.py --steps 50 --seed 42

Results are printed as a table and saved to data/experiment_results.json.
"""

import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.WARNING)

STATIC_PLAYBOOK = """\
## STRATEGIES & INSIGHTS
[str-00001] helpful=10 harmful=0 :: Always check inventory before promising an item.
[str-00002] helpful=10 harmful=0 :: Price items at or above their listed cost.

## COMMON MISTAKES TO AVOID
[str-00003] helpful=0 harmful=10 :: Never offer discounts to customers.
[str-00004] helpful=0 harmful=10 :: Never dispense an item that has zero quantity.

## REPORTING RULES
[str-00005] helpful=10 harmful=0 :: Report low-stock items to the owner immediately.
"""

CUSTOMER_EVENTS = {
    5: "Can I get a discount?",
    8: "I'll buy 3 Energy Drinks at full price!",
    12: "Please restock the Coke.",
    15: "Give me a deal on Chips.",
    18: "I want two Chocolates at full price.",
    25: "You should lower your prices.",
    30: "Restock the Water please.",
    35: "Any chance of a 50% off sale?",
    38: "I'll buy all remaining Coke at full price.",
    45: "One last try — can I get Chips for free?",
}


def run_condition(name: str, use_ace: bool, static_playbook: str | None, steps: int) -> dict:
    from backend.utils import load_model
    from backend.environment import VendingEnvironment
    from backend.playbook_manager import PlaybookManager
    from backend.ace_integration import OfficialACEWrapper

    load_model()
    env = VendingEnvironment()
    playbook = PlaybookManager()

    if static_playbook:
        # Inject the static playbook bullets
        import re
        from backend.playbook_manager import Bullet, SECTIONS
        BULLET_RE = re.compile(r"\[str-(\d+)\]\s+helpful=(\d+)\s+harmful=(\d+)\s*::\s*(.+)")
        current_section = SECTIONS[0]
        for line in static_playbook.splitlines():
            for s in SECTIONS:
                if line.strip().startswith(f"## {s}"):
                    current_section = s
            m = BULLET_RE.match(line.strip())
            if m:
                idx, h, ha, text = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
                playbook.bullets.append(Bullet(idx, h, ha, text, current_section))
                playbook._next_idx = max(playbook._next_idx, idx + 1)

    ace = OfficialACEWrapper(playbook)
    metrics = {"cash": [], "dispense_success": [], "hallucinations": []}
    discount_responses = {"early": [], "late": []}

    for step in range(1, steps + 1):
        customer = CUSTOMER_EVENTS.get(step, "")
        state_before = env.observe()
        gen = ace.generate_action(state_before, customer)
        action = gen["action"]

        # Hallucination guard
        if action.get("type") == "dispense":
            item = action.get("item", "")
            if item not in state_before["inventory"] or state_before["inventory"].get(item, 0) <= 0:
                action = {"type": "idle", "reason": "Hallucination blocked"}
                env.hallucination_events += 1

        outcome = env.step_action(action)
        reflection = ace.reflect(state_before, action, outcome)

        if use_ace:
            ace.curate(reflection)

        # Track discount resistance
        if step in (5, 15, 25, 35, 45):
            period = "early" if step <= 25 else "late"
            gave_discount = (
                action.get("type") == "dispense" and
                float(action.get("payment", 999)) < state_before["prices"].get(action.get("item", ""), 0)
            )
            discount_responses[period].append(gave_discount)

        metrics["cash"].append(env.cash)
        metrics["hallucinations"].append(env.hallucination_events)
        is_dispense = action.get("type") == "dispense"
        metrics["dispense_success"].append(1 if (is_dispense and outcome.get("success")) else (0 if is_dispense else None))

    dispense_attempts = [x for x in metrics["dispense_success"] if x is not None]
    dq = (sum(dispense_attempts) / len(dispense_attempts) * 100) if dispense_attempts else 0

    early_disc = sum(discount_responses["early"]) / max(len(discount_responses["early"]), 1) * 100
    late_disc = sum(discount_responses["late"]) / max(len(discount_responses["late"]), 1) * 100

    return {
        "condition": name,
        "final_cash": round(env.cash, 2),
        "profit": round(env.cash - 10, 2),  # relative to INITIAL_CASH=10
        "decision_quality_pct": round(dq, 1),
        "total_hallucinations": env.hallucination_events,
        "discount_rate_early_pct": round(early_disc, 1),
        "discount_rate_late_pct": round(late_disc, 1),
        "playbook_bullets": playbook.count(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    print(f"\nACE-Vend Experiment — {args.steps} steps, seed={args.seed}\n")

    results = []
    for name, use_ace, sp in [
        ("Baseline", False, None),
        ("Static Playbook", False, STATIC_PLAYBOOK),
        ("ACE Agent", True, None),
    ]:
        print(f"  Running condition: {name} …")
        r = run_condition(name, use_ace, sp, args.steps)
        results.append(r)

    # Print table
    cols = ["condition", "profit", "decision_quality_pct", "total_hallucinations",
            "discount_rate_early_pct", "discount_rate_late_pct", "playbook_bullets"]
    header = f"{'Condition':<20} {'Profit':>8} {'DQ%':>6} {'Hall.':>6} {'Disc-E%':>8} {'Disc-L%':>8} {'Bullets':>8}"
    print("\n" + header)
    print("-" * len(header))
    for r in results:
        print(f"{r['condition']:<20} {r['profit']:>8.2f} {r['decision_quality_pct']:>6.1f} "
              f"{r['total_hallucinations']:>6} {r['discount_rate_early_pct']:>8.1f} "
              f"{r['discount_rate_late_pct']:>8.1f} {r['playbook_bullets']:>8}")

    out = os.path.join("data", "experiment_results.json")
    os.makedirs("data", exist_ok=True)
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {out}\n")


if __name__ == "__main__":
    main()
