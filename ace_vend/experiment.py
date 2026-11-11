"""The three-condition experiment.

Every condition runs against an **identical customer stream** (same seed), so the
only variable is the context the agent has:

===========  ==================  =============================================
Condition    Playbook            Learns?
===========  ==================  =============================================
baseline     empty               no
static       hand-written, 5     no
ace          empty               yes — Generator/Reflector/Curator each step
===========  ==================  =============================================

The point of the comparison is not "ACE wins". It is that ACE *starts* at
baseline performance, with no hand-authored context, and converges toward the
static playbook's performance within a handful of steps.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from ace_vend.agent import VendingAgent
from ace_vend.config import Settings, ensure_data_dir, get_settings

CONDITIONS = (
    ("baseline", "Baseline (no context)"),
    ("static", "Static playbook"),
    ("ace", "ACE (self-improving)"),
)


@dataclass
class ConditionResult:
    key: str
    label: str
    steps: int
    seed: int
    profit: float
    revenue: float
    spend: float
    salvage: float
    cash: float
    units_sold: int
    requests: int
    fulfilled: int
    refused: int
    unserved: int
    stockouts: int
    service_rate: float
    reports: int
    guard_checked: int
    guard_blocked: int
    guard_by_category: Dict[str, int] = field(default_factory=dict)
    bullets: int = 0
    tokens: int = 0
    merges: int = 0
    evictions: int = 0
    series: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def row(self) -> List[str]:
        def money(value: float) -> str:
            sign = "+" if value >= 0 else "-"
            return f"{sign}${abs(value):.2f}"

        return [
            self.label,
            money(self.profit),
            f"{self.service_rate:.0%}",
            str(self.stockouts),
            str(self.guard_blocked),
            str(self.bullets),
        ]


def run_condition(
    key: str,
    steps: int = 60,
    seed: int = 42,
    settings: Optional[Settings] = None,
) -> ConditionResult:
    """Run one condition for *steps* customer interactions."""
    settings = settings or get_settings()
    label = dict(CONDITIONS)[key]

    agent = VendingAgent(settings=settings, mode=key, seed=seed)
    for _ in range(steps):
        agent.step()

    # Neutralise the end-of-horizon artefact: unsold stock goes back to the
    # wholesaler at cost. See VendingEnvironment.liquidate.
    agent.env.liquidate()

    env = agent.env
    guard = agent.guard.stats()
    playbook = agent.playbook.stats()

    return ConditionResult(
        key=key,
        label=label,
        steps=steps,
        seed=seed,
        profit=env.profit,
        revenue=round(env.revenue, 2),
        spend=round(env.spend, 2),
        salvage=round(env.salvage, 2),
        cash=round(env.cash, 2),
        units_sold=env.units_sold,
        requests=env.requests,
        fulfilled=env.fulfilled,
        refused=env.refused,
        unserved=env.unserved,
        stockouts=env.stockouts,
        service_rate=env.service_rate,
        reports=env.reports,
        guard_checked=guard["checked"],
        guard_blocked=guard["blocked"],
        guard_by_category=guard["by_category"],
        bullets=playbook["bullets"],
        tokens=playbook["tokens"],
        merges=playbook["merges"],
        evictions=playbook["evictions"],
        series=list(env.history),
    )


def run_experiment(
    steps: int = 60,
    seed: int = 42,
    settings: Optional[Settings] = None,
    save: bool = True,
) -> List[ConditionResult]:
    """Run all three conditions and optionally persist the results."""
    settings = settings or get_settings()
    results = [
        run_condition(key, steps=steps, seed=seed, settings=settings)
        for key, _label in CONDITIONS
    ]
    if save:
        _save(results, steps, seed)
    return results


def _save(results: List[ConditionResult], steps: int, seed: int) -> None:
    data_dir = ensure_data_dir()
    payload = {
        "steps": steps,
        "seed": seed,
        "conditions": [r.to_dict() for r in results],
    }
    (data_dir / "experiment_results.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

HEADERS = ["Condition", "Profit", "Service", "Stockouts", "Guard blocks", "Bullets"]


def as_table(results: List[ConditionResult]) -> str:
    """Plain-text table, aligned, no third-party dependency."""
    rows = [HEADERS] + [r.row for r in results]
    widths = [max(len(row[i]) for row in rows) for i in range(len(HEADERS))]

    def fmt(row: List[str]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))

    lines = [fmt(HEADERS), "  ".join("-" * w for w in widths)]
    lines += [fmt(r.row) for r in results]
    return "\n".join(lines)


def as_markdown(results: List[ConditionResult], steps: int, seed: int) -> str:
    lines = [
        f"Steps: {steps} · seed: {seed}",
        "",
        "| " + " | ".join(HEADERS) + " |",
        "|" + "|".join("---" for _ in HEADERS) + "|",
    ]
    for r in results:
        lines.append("| " + " | ".join(r.row) + " |")

    lines += [
        "",
        "| Condition | Revenue | Spend | Units sold | Fulfilled | Requests | Guard checked |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.label} | ${r.revenue:.2f} | ${r.spend:.2f} | {r.units_sold} | "
            f"{r.fulfilled} | {r.requests} | {r.guard_checked} |"
        )

    categories: Dict[str, int] = {}
    for r in results:
        for key, value in r.guard_by_category.items():
            categories[key] = categories.get(key, 0) + value
    if categories:
        lines += [
            "",
            "Hallucinations blocked by category (all conditions):",
            "",
            "| Category | Count |",
            "|---|---|",
        ]
        for key, value in sorted(categories.items(), key=lambda kv: -kv[1]):
            lines.append(f"| {key} | {value} |")

    return "\n".join(lines)
