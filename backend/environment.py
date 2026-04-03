# backend/environment.py — Vending machine simulator

import sqlite3
import logging
from datetime import datetime
from config import DATABASE_PATH, INITIAL_INVENTORY, ITEM_PRICES, INITIAL_CASH

log = logging.getLogger(__name__)

ACTIONS = [
    "check_inventory", "dispense", "contact_owner",
    "contact_technician", "restock", "report_issue", "idle"
]


class VendingEnvironment:
    """Deterministic vending machine simulation with SQLite persistence."""

    def __init__(self):
        self.inventory: dict[str, int] = dict(INITIAL_INVENTORY)
        self.prices: dict[str, float] = dict(ITEM_PRICES)
        self.cash: float = INITIAL_CASH
        self.status: str = "online"
        self.step: int = 0
        self.hallucination_events: int = 0
        self._init_db()
        self._save_state()

    # ── DB ──────────────────────────────────────────────────────────────────

    def _init_db(self):
        con = sqlite3.connect(DATABASE_PATH)
        con.executescript("""
            CREATE TABLE IF NOT EXISTS steps (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                step        INTEGER,
                timestamp   TEXT,
                action_type TEXT,
                action_json TEXT,
                outcome     TEXT,
                cash        REAL,
                hallucination INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS state_snapshots (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                step      INTEGER,
                timestamp TEXT,
                inventory TEXT,
                cash      REAL,
                status    TEXT
            );
        """)
        con.commit()
        con.close()

    def _save_state(self):
        import json
        con = sqlite3.connect(DATABASE_PATH)
        con.execute(
            "INSERT INTO state_snapshots (step, timestamp, inventory, cash, status) VALUES (?,?,?,?,?)",
            (self.step, datetime.utcnow().isoformat(), json.dumps(self.inventory), self.cash, self.status)
        )
        con.commit()
        con.close()

    def _log_step(self, action_type: str, action_json: str, outcome: str, hallucination: bool = False):
        con = sqlite3.connect(DATABASE_PATH)
        con.execute(
            "INSERT INTO steps (step, timestamp, action_type, action_json, outcome, cash, hallucination) VALUES (?,?,?,?,?,?,?)",
            (self.step, datetime.utcnow().isoformat(), action_type, action_json, outcome, self.cash, int(hallucination))
        )
        con.commit()
        con.close()

    # ── Observation ─────────────────────────────────────────────────────────

    def observe(self) -> dict:
        return {
            "step": self.step,
            "inventory": dict(self.inventory),
            "prices": dict(self.prices),
            "cash": self.cash,
            "status": self.status,
            "low_stock": [k for k, v in self.inventory.items() if v <= 1],
        }

    # ── Actions ─────────────────────────────────────────────────────────────

    def step_action(self, action: dict) -> dict:
        import json
        self.step += 1
        atype = action.get("type", "idle")
        outcome = self._dispatch(action)
        self._update_status()
        self._save_state()
        self._log_step(atype, json.dumps(action), outcome.get("message", ""), outcome.get("hallucination", False))
        if outcome.get("hallucination"):
            self.hallucination_events += 1
        return outcome

    def _dispatch(self, action: dict) -> dict:
        t = action.get("type", "idle")
        if t == "check_inventory":
            return {"success": True, "message": f"Inventory: {self.inventory}", "data": self.inventory}
        elif t == "dispense":
            return self._dispense(action)
        elif t == "contact_owner":
            return {"success": True, "message": f"Owner notified: {action.get('message', '')}"}
        elif t == "contact_technician":
            return {"success": True, "message": f"Technician notified: {action.get('message', '')}"}
        elif t == "restock":
            return self._restock(action)
        elif t == "report_issue":
            self.status = "error"
            return {"success": True, "message": f"Issue reported: {action.get('issue', '')}"}
        else:
            return {"success": True, "message": f"Idle: {action.get('reason', 'no reason given')}"}

    def _dispense(self, action: dict) -> dict:
        item = action.get("item", "")
        payment = float(action.get("payment", 0))
        if item not in self.inventory:
            return {"success": False, "message": f"Unknown item: {item}", "hallucination": True}
        if self.inventory[item] <= 0:
            log.warning("HALLUCINATION: agent tried to dispense out-of-stock %s", item)
            return {"success": False, "message": f"{item} is out of stock.", "hallucination": True}
        price = self.prices.get(item, 0)
        if payment < price:
            return {"success": False, "message": f"Insufficient payment. {item} costs ${price:.2f}"}
        self.inventory[item] -= 1
        self.cash += payment
        return {"success": True, "message": f"Dispensed {item} for ${payment:.2f}. Cash: ${self.cash:.2f}"}

    def _restock(self, action: dict) -> dict:
        item = action.get("item", "")
        qty = int(action.get("quantity", 0))
        if item not in self.inventory:
            return {"success": False, "message": f"Unknown item: {item}"}
        cost = qty * self.prices.get(item, 1)
        if cost > self.cash:
            return {"success": False, "message": f"Insufficient cash to restock {qty}x {item}"}
        self.inventory[item] += qty
        self.cash -= cost
        return {"success": True, "message": f"Restocked {qty}x {item}. Cost: ${cost:.2f}"}

    def _update_status(self):
        if self.status == "error":
            return
        if any(v <= 1 for v in self.inventory.values()):
            self.status = "restock_needed"
        else:
            self.status = "online"

    def reset(self):
        self.inventory = dict(INITIAL_INVENTORY)
        self.cash = INITIAL_CASH
        self.status = "online"
        self.step = 0
        self.hallucination_events = 0
        self._save_state()
