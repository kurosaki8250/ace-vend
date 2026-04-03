# backend/app.py — Flask API + Server-Sent Events stream

import json
import logging
import queue
import threading
from flask import Flask, Response, jsonify, request, render_template

log = logging.getLogger(__name__)
app = Flask(
    __name__,
    template_folder="../frontend/templates",
    static_folder="../frontend/static",
)

_agent = None
_agent_lock = threading.Lock()
_event_queue: queue.Queue = queue.Queue(maxsize=200)


def get_agent():
    global _agent
    if _agent is None:
        with _agent_lock:
            if _agent is None:
                from backend.utils import load_model
                load_model()
                from backend.agent import VendingAgent
                _agent = VendingAgent()
    return _agent


def _push_event(data: dict):
    """Push a JSON event onto the SSE queue (drop if full)."""
    try:
        _event_queue.put_nowait(data)
    except queue.Full:
        pass


# ── SSE stream ───────────────────────────────────────────────────────────────

@app.route("/stream")
def stream():
    def event_generator():
        while True:
            try:
                data = _event_queue.get(timeout=30)
                yield f"data: {json.dumps(data)}\n\n"
            except queue.Empty:
                yield ": keep-alive\n\n"

    return Response(event_generator(), content_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── REST API ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    return jsonify(get_agent().get_state())


@app.route("/api/step", methods=["POST"])
def api_step():
    body = request.get_json(silent=True) or {}
    customer = body.get("customer", "")
    event = get_agent().step(customer_request=customer)
    _push_event({"type": "step", **event})
    return jsonify(event)


@app.route("/api/reset", methods=["POST"])
def api_reset():
    get_agent().reset()
    _push_event({"type": "reset"})
    return jsonify({"ok": True})


@app.route("/api/playbook")
def api_playbook():
    return jsonify(get_agent().playbook.all_bullets())


@app.route("/api/metrics")
def api_metrics():
    """Return time-series data for charts."""
    import sqlite3
    from config import DATABASE_PATH
    con = sqlite3.connect(DATABASE_PATH)
    rows = con.execute(
        "SELECT step, cash, hallucination FROM steps ORDER BY step"
    ).fetchall()
    con.close()
    return jsonify([{"step": r[0], "cash": r[1], "hallucination": r[2]} for r in rows])
