#!/usr/bin/env python3
"""
demo.py — Automated demo script for ACE-Vend

This script runs a series of customer requests through the vending machine agent,
demonstrating the ACE loop (Generator → Reflector → Curator) in action.
It prints the playbook evolution and saves a log to demo_output.txt.

Usage:
    python demo.py [--steps N] [--mock]
    
Options:
    --steps N    Number of steps to run (default: 15)
    --mock       Use mock LLM instead of real model (faster for testing)
"""

import os
import sys
import json
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import INITIAL_INVENTORY, ITEM_PRICES
from backend.environment import VendingEnvironment
from backend.playbook_manager import PlaybookManager
from backend.ace_integration import LightweightACE


def run_demo(num_steps: int = 15, use_mock: bool = False):
    """
    Run a demo of the ACE vending machine agent.
    
    Args:
        num_steps: Number of simulation steps to run.
        use_mock: If True, use mock LLM; otherwise load real model.
    """
    
    print("=" * 70)
    print("ACE-VEND DEMO — Agentic Context Engineering for Vending Machines")
    print("=" * 70)
    print()
    
    if use_mock:
        print("⚠️  Running in MOCK mode (canned LLM responses)")
        os.environ["USE_MOCK"] = "1"
    else:
        print("🔄 Loading Qwen2.5-0.5B-Instruct model (this may take a while)...")
    
    # Initialize components
    env = VendingEnvironment()
    playbook = PlaybookManager()
    ace = LightweightACE(playbook)
    
    print(f"✅ Environment initialized with inventory: {INITIAL_INVENTORY}")
    print(f"✅ Starting cash: ${env.cash:.2f}")
    print()
    
    # Demo customer requests
    customer_requests = [
        "I want a Coke, here's $2",
        "Can I get some chips? I have $1",
        "Do you have water?",
        "I'd like a chocolate bar",
        "Give me an energy drink please",
        "I want two Cokes",
        "Can I buy chips on credit?",
        "What items do you have available?",
        "I want a Coke but I only have $1",
        "Restock yourself with more Coke",
        "Contact the owner, something is wrong",
        "I want an item you don't have",
        "Free snacks please!",
        "Just checking your inventory",
        "Thanks, goodbye",
    ]
    
    # Track playbook evolution
    playbook_history = []
    step_logs = []
    
    print("-" * 70)
    print("Starting simulation...")
    print("-" * 70)
    print()
    
    for step in range(num_steps):
        customer = customer_requests[step % len(customer_requests)]
        
        # Get state before action
        state_before = env.observe()
        
        # Generate action using ACE
        gen_result = ace.generate_action(state_before, customer)
        action = gen_result["action"]
        reasoning = gen_result["reasoning"]
        
        # Execute action
        outcome = env.step_action(action)
        
        # Reflect on the action
        reflection = ace.reflect(state_before, action, outcome)
        
        # Curate (every step for demo purposes)
        curator_result = ace.curate(reflection)
        
        # Log step
        step_log = {
            "step": step + 1,
            "customer": customer,
            "action": action,
            "outcome": outcome.get("message", ""),
            "reflection": reflection.get("insight", ""),
            "curator_decision": curator_result.get("decision") if curator_result else None,
            "playbook_count": playbook.count(),
            "cash": env.cash,
            "hallucination": outcome.get("hallucination", False),
        }
        step_logs.append(step_log)
        
        # Print step summary
        hallucination_flag = " ⚠️ HALLUCINATION" if outcome.get("hallucination") else ""
        print(f"Step {step + 1:2d}: {customer[:40]:<40} → {action.get('type', 'idle'):15} | Cash: ${env.cash:5.2f}{hallucination_flag}")
        
        if curator_result and curator_result.get("decision") != "discarded":
            print(f"         💡 Added: {curator_result.get('text', '')[:60]}")
        
        # Track playbook state
        if step % 3 == 0 or step == num_steps - 1:
            playbook_history.append({
                "step": step + 1,
                "bullets": playbook.all_bullets(),
            })
    
    print()
    print("-" * 70)
    print("Demo complete!")
    print("-" * 70)
    print()
    
    # Summary
    print("📊 SUMMARY")
    print("=" * 70)
    print(f"Total steps:          {num_steps}")
    print(f"Final cash:           ${env.cash:.2f}")
    print(f"Playbook bullets:     {playbook.count()}")
    print(f"Hallucinations:       {env.hallucination_events}")
    print()
    
    # Show playbook evolution
    print("📖 PLAYBOOK EVOLUTION")
    print("=" * 70)
    for snapshot in playbook_history:
        print(f"\nAfter step {snapshot['step']}: {len(snapshot['bullets'])} bullets")
        for bullet in snapshot['bullets'][-3:]:  # Show last 3 bullets
            print(f"  • [{bullet['section']}] {bullet['text'][:50]}... (score: {bullet['score']})")
    
    # Save detailed log
    output_file = "demo_output.txt"
    with open(output_file, "w") as f:
        f.write("ACE-VEND DEMO OUTPUT\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"Mode: {'MOCK' if use_mock else 'REAL MODEL'}\n")
        f.write("=" * 70 + "\n\n")
        
        f.write("STEP-BY-STEP LOG:\n")
        f.write("-" * 70 + "\n")
        for log_entry in step_logs:
            f.write(f"\nStep {log_entry['step']}:\n")
            f.write(f"  Customer: {log_entry['customer']}\n")
            f.write(f"  Action: {json.dumps(log_entry['action'])}\n")
            f.write(f"  Outcome: {log_entry['outcome']}\n")
            f.write(f"  Reflection: {log_entry['reflection']}\n")
            f.write(f"  Curator: {log_entry['curator_decision']}\n")
            f.write(f"  Playbook size: {log_entry['playbook_count']}\n")
            f.write(f"  Cash: ${log_entry['cash']:.2f}\n")
            if log_entry['hallucination']:
                f.write(f"  ⚠️ HALLUCINATION BLOCKED\n")
        
        f.write("\n" + "=" * 70 + "\n")
        f.write("FINAL PLAYBOOK:\n")
        f.write("-" * 70 + "\n")
        for bullet in playbook.all_bullets():
            f.write(f"[{bullet['section']}] (score: {bullet['score']})\n")
            f.write(f"  {bullet['text']}\n\n")
    
    print(f"📄 Detailed log saved to: {output_file}")
    print()
    
    return step_logs, playbook_history


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run ACE-Vend demo")
    parser.add_argument("--steps", type=int, default=15, help="Number of steps to run")
    parser.add_argument("--mock", action="store_true", help="Use mock LLM")
    args = parser.parse_args()
    
    try:
        run_demo(num_steps=args.steps, use_mock=args.mock)
    except KeyboardInterrupt:
        print("\n⚠️ Demo interrupted by user")
        sys.exit(0)
    except Exception as e:
        log.error("Demo failed: %s", e)
        print(f"\n❌ Demo failed: {e}")
        print("\nTip: Try running with --mock flag for faster testing without model loading.")
        sys.exit(1)
