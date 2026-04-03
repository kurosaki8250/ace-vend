#!/usr/bin/env python3
# run.py — Entry point for the ACE Vending Machine simulation

import logging
import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

from config import FLASK_HOST, FLASK_PORT, FLASK_DEBUG


def main():
    print("\n" + "=" * 60)
    print("  ACE Vending Machine — Simulation")
    print("  Agentic Context Engineering + Qwen2.5-0.5B")
    print("=" * 60)
    print(f"\n  Loading model … (first run may take 1–2 minutes)")
    print(f"  UI will be available at: http://localhost:{FLASK_PORT}\n")

    # Import here so model loading message appears first
    from backend.app import app, get_agent

    # initialise the agent (loads model)
    get_agent()

    print(f"\n  ✓ Agent ready. Starting Flask on port {FLASK_PORT} …\n")
    app.run(
        host=FLASK_HOST,
        port=FLASK_PORT,
        debug=FLASK_DEBUG,
        threaded=True,
        use_reloader=False,  # avoid double model load
    )


if __name__ == "__main__":
    main()
