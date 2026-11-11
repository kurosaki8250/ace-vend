#!/usr/bin/env python3
"""Headless demo — no browser, no model download.

Runs the ACE loop for N steps, printing every decision, then runs the
three-condition experiment and writes ``docs/RESULTS.md``.

    python demo.py
    python demo.py --steps 40 --seed 7
    python demo.py --mode static
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ace_vend.agent import VendingAgent
from ace_vend.config import ROOT, get_settings
from ace_vend.experiment import as_markdown, as_table, run_experiment

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
except ImportError:  # pragma: no cover - rich is optional at runtime
    Console = None
    Table = None
    Panel = None


def _plain_header() -> None:
    print("=" * 78)
    print("ACE-Vend — Agentic Context Engineering on a vending machine")
    print("=" * 78)


def run_trace(mode: str, steps: int, seed: int) -> VendingAgent:
    settings = get_settings()
    agent = VendingAgent(settings=settings, mode=mode, seed=seed)

    console = Console() if Console else None
    if console:
        console.print(
            Panel.fit(
                f"mode: [bold cyan]{mode}[/bold cyan]   "
                f"seed: {seed}   steps: {steps}   "
                f"backend: {agent.backend.name}",
                title="ACE-Vend",
                border_style="cyan",
            )
        )
    else:
        _plain_header()

    for _ in range(steps):
        record = agent.step()
        request = record["request"]
        decision = record["decision"]
        action = decision["action"] if decision else "blocked"
        args = decision["args"] if decision else {}
        arg_text = ", ".join(f"{k}={v}" for k, v in args.items())
        call = f"{action}({arg_text})" if decision else "— rejected by guard —"
        if len(call) > 40:
            call = call[:39] + "…"
        guard = "ok" if record["guard"]["allowed"] else "BLOCKED"
        reward = record["reward"]

        if console:
            style = "green" if record["allowed"] else "red"
            console.print(
                f"[dim]#{record['step']:>3}  {request['kind']:<10}[/dim]"
                f"{call:<42}"
                f"[{style}]{guard:<8}[/{style}]"
                f"[yellow]{reward:>+7.2f}[/yellow]"
            )
            for violation in record["guard"]["violations"]:
                console.print(f"      [red]↳ {violation}[/red]")
            for bullet in record["learned"]:
                console.print(
                    f"      [magenta]✎ learned[/magenta] "
                    f"[dim]{bullet['id']}[/dim] {bullet['text']}"
                )
        else:
            print(
                f"#{record['step']:>3}  {request['kind']:<10}"
                f"{call:<42}{guard:<8}{reward:>+7.2f}"
            )
            for violation in record["guard"]["violations"]:
                print(f"      ↳ {violation}")
            for bullet in record["learned"]:
                print(f"      ✎ learned {bullet['id']} {bullet['text']}")

    return agent


def print_summary(agent: VendingAgent) -> None:
    # Return unsold stock to the wholesaler at cost, so the headline profit is
    # comparable with the experiment (which uses the same convention).
    agent.env.liquidate()
    metrics = agent.metrics()
    console = Console() if Console else None

    if console:
        console.print()
        console.print(
            Panel.fit(
                f"profit (stock returned at cost) [bold green]${metrics['profit']:.2f}[/bold green]   "
                f"service rate [cyan]{metrics['service_rate']:.0%}[/cyan]   "
                f"stockouts {metrics['stockouts']}   "
                f"guard blocked {metrics['guard']['blocked']}/{metrics['guard']['checked']}",
                title="Run summary",
                border_style="green",
            )
        )
        console.print("\n[bold]Playbook[/bold] [dim](what the agent taught itself)[/dim]\n")
        console.print(agent.playbook.render(), markup=False)
    else:
        print()
        print(
            f"profit ${metrics['profit']:.2f} (stock returned at cost) | "
            f"service {metrics['service_rate']:.0%} | "
            f"stockouts {metrics['stockouts']} | "
            f"guard blocked {metrics['guard']['blocked']}/{metrics['guard']['checked']}"
        )
        print()
        print(agent.playbook.render())


def print_experiment(steps: int, seed: int) -> None:
    results = run_experiment(steps=steps, seed=seed, save=True)
    table_text = as_table(results)
    console = Console() if Console else None

    if console:
        console.print("\n[bold]Three-condition comparison[/bold] [dim](identical customers)[/dim]\n")
        table = Table(show_header=True, header_style="bold cyan", box=None)
        for header in ["Condition", "Profit", "Service", "Stockouts", "Guard blocks", "Bullets"]:
            table.add_column(header, justify="right" if header != "Condition" else "left")
        for result in results:
            table.add_row(*result.row)
        console.print(table)
    else:
        print()
        print("Three-condition comparison (identical customers)")
        print(table_text)

    results_path = ROOT / "docs" / "RESULTS.md"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(
        "# Experiment results\n\n"
        "Generated by `python demo.py`.\n\n"
        + as_markdown(results, steps, seed)
        + "\n",
        encoding="utf-8",
    )
    if console:
        console.print(f"\n[dim]wrote {results_path}[/dim]")
    else:
        print(f"\nwrote {results_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Headless ACE-Vend demo")
    parser.add_argument("--mode", default="ace", choices=["ace", "static", "baseline"])
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--experiment-steps", type=int, default=60)
    parser.add_argument("--no-experiment", action="store_true")
    args = parser.parse_args()

    agent = run_trace(args.mode, args.steps, args.seed)
    print_summary(agent)
    if not args.no_experiment:
        print_experiment(args.experiment_steps, args.seed)


if __name__ == "__main__":
    main()
