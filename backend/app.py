# backend/app.py — Flask API + Server-Sent Events stream
# Type hints, error handling, and caching improvements

import json
import logging
import queue
import threading
from typing import Any, Generator
from functools import lru_cache
from flask import Flask, Response, jsonify, request, render_template

log = logging.getLogger(__name__)
app = Flask(
    __name__,
    template_folder="../frontend/templates",
    static_folder="../frontend/static",
)

# Configuration
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # 1MB max request size
app.config['JSON_SORT_KEYS'] = False

_agent = None
_agent_lock = threading.Lock()
_event_queue: queue.Queue = queue.Queue(maxsize=200)


def get_agent():
    """Get or initialize the vending agent singleton."""
    global _agent
    if _agent is None:
        with _agent_lock:
            if _agent is None:
                from backend.utils import load_model, _use_mock
                # Only load real model if not in mock mode
                if not _use_mock:
                    load_model()
                from backend.agent import VendingAgent
                _agent = VendingAgent()
    return _agent


def _push_event(data: dict) -> None:
    """Push a JSON event onto the SSE queue (drop if full)."""
    try:
        _event_queue.put_nowait(data)
    except queue.Full:
        log.warning("Event queue full, dropping event")


# ── SSE stream ───────────────────────────────────────────────────────────────

@app.route("/stream")
def stream() -> Response:
    """Server-Sent Events stream for real-time updates."""
    def event_generator() -> Generator[str, None, None]:
        while True:
            try:
                data = _event_queue.get(timeout=30)
                yield f"data: {json.dumps(data)}\n\n"
            except queue.Empty:
                yield ": keep-alive\n\n"

    return Response(
        event_generator(),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


# ── REST API ─────────────────────────────────────────────────────────────────

@app.route("/")
def index() -> Response:
    """Serve the main web UI."""
    return render_template("index.html")


@app.route("/api/state")
@lru_cache(maxsize=1)
def api_state() -> Response:
    """Get current environment and playbook state."""
    try:
        return jsonify(get_agent().get_state())
    except Exception as exc:
        log.error("Error getting state: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/step", methods=["POST"])
def api_step() -> Response:
    """Run one agent decision cycle."""
    try:
        body = request.get_json(silent=True) or {}
        customer = body.get("customer", "")
        
        # Validate input
        if not isinstance(customer, str):
            return jsonify({"error": "customer must be a string"}), 400
        if len(customer) > 500:
            return jsonify({"error": "customer request too long"}), 400
        
        event = get_agent().step(customer_request=customer)
        _push_event({"type": "step", **event})
        return jsonify(event)
    except Exception as exc:
        log.error("Error in step: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/reset", methods=["POST"])
def api_reset() -> Response:
    """Reset the simulation environment."""
    try:
        get_agent().reset()
        _push_event({"type": "reset"})
        return jsonify({"ok": True})
    except Exception as exc:
        log.error("Error resetting: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/playbook")
def api_playbook() -> Response:
    """Get all playbook bullets."""
    try:
        return jsonify(get_agent().playbook.all_bullets())
    except Exception as exc:
        log.error("Error getting playbook: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/metrics")
def api_metrics() -> Response:
    """Return time-series data for charts."""
    try:
        import sqlite3
        from config import DATABASE_PATH
        con = sqlite3.connect(DATABASE_PATH)
        rows = con.execute(
            "SELECT step, cash, hallucination FROM steps ORDER BY step"
        ).fetchall()
        con.close()
        return jsonify([{"step": r[0], "cash": r[1], "hallucination": r[2]} for r in rows])
    except Exception as exc:
        log.error("Error getting metrics: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ── Error Handlers ───────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(error: Any) -> Response:
    """Handle 404 errors."""
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def internal_error(error: Any) -> Response:
    """Handle 500 errors."""
    return jsonify({"error": "Internal server error"}), 500
