"""Flask API and web UI for the vending-machine agent.

The server is intentionally thin: all logic lives in :mod:`ace_vend.agent`. The
endpoints exist so the dashboard can drive the same code the CLI and the
experiment use.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Optional

from flask import Flask, Response, jsonify, render_template, request

from ace_vend.agent import MODES, VendingAgent
from ace_vend.config import Settings, get_settings
from ace_vend.experiment import as_markdown, as_table, run_experiment


def create_app(
    settings: Optional[Settings] = None,
    agent: Optional[VendingAgent] = None,
    mode: str = "ace",
) -> Flask:
    settings = settings or get_settings()
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.json.sort_keys = False

    lock = threading.Lock()
    state = {
        "agent": agent or VendingAgent(settings=settings, mode=mode),
        "version": 0,
    }

    def bump() -> None:
        state["version"] += 1

    # ---------------------------------------------------------------- pages

    @app.get("/")
    def index():
        return render_template("index.html", mode=state["agent"].mode)

    # ----------------------------------------------------------------- api

    @app.get("/api/state")
    def api_state():
        with lock:
            return jsonify(state["agent"].state())

    @app.get("/api/playbook")
    def api_playbook():
        with lock:
            return jsonify(state["agent"].playbook.to_dict())

    @app.get("/api/metrics")
    def api_metrics():
        with lock:
            return jsonify(state["agent"].metrics())

    @app.post("/api/step")
    def api_step():
        payload = request.get_json(silent=True) or {}
        customer = payload.get("customer")
        with lock:
            record = state["agent"].step(customer)
            bump()
            return jsonify({"record": record, "state": state["agent"].state()})

    @app.post("/api/reset")
    def api_reset():
        payload = request.get_json(silent=True) or {}
        seed = payload.get("seed")
        new_mode = payload.get("mode")
        with lock:
            if new_mode and new_mode != state["agent"].mode:
                if new_mode not in MODES:
                    return jsonify({"error": f"mode must be one of {MODES}"}), 400
                state["agent"] = VendingAgent(
                    settings=settings, mode=new_mode, seed=seed
                )
            else:
                state["agent"].reset(seed=seed)
            bump()
            return jsonify(state["agent"].state())

    @app.post("/api/mode")
    def api_mode():
        payload = request.get_json(silent=True) or {}
        new_mode = payload.get("mode", "")
        if new_mode not in MODES:
            return jsonify({"error": f"mode must be one of {MODES}"}), 400
        with lock:
            state["agent"] = VendingAgent(settings=settings, mode=new_mode)
            bump()
            return jsonify(state["agent"].state())

    @app.post("/api/experiment")
    def api_experiment():
        payload = request.get_json(silent=True) or {}
        steps = int(payload.get("steps", settings.steps))
        seed = int(payload.get("seed", settings.seed))
        steps = max(5, min(steps, 500))
        results = run_experiment(
            steps=steps, seed=seed, settings=settings, save=False
        )
        return jsonify(
            {
                "steps": steps,
                "seed": seed,
                "table": as_table(results),
                "markdown": as_markdown(results, steps, seed),
                "conditions": [r.to_dict() for r in results],
            }
        )

    @app.get("/api/stream")
    def api_stream():
        def generate():
            last = -1
            while True:
                version = state["version"]
                if version != last:
                    last = version
                    payload = json.dumps(state["agent"].state())
                    yield f"event: state\ndata: {payload}\n\n"
                else:
                    yield ": keep-alive\n\n"
                time.sleep(0.4)

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @app.get("/api/health")
    def api_health():
        return jsonify({"ok": True, "mode": state["agent"].mode})

    return app


def main(argv: Optional[list] = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="ACE-Vend web dashboard")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--mode", default="ace", choices=MODES)
    args = parser.parse_args(argv)

    settings = get_settings()
    app = create_app(settings=settings, mode=args.mode)
    host = args.host or settings.host
    port = args.port or settings.port

    print(f"ACE-Vend dashboard  ->  http://{host}:{port}  (mode: {args.mode})")
    print("Press Ctrl+C to stop.")
    app.run(host=host, port=port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
