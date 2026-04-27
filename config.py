# config.py — central configuration for the ACE Vending Machine project

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(DATA_DIR, "logs")
MODELS_DIR = os.path.join(BASE_DIR, "models")

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_PATH = os.path.join(DATA_DIR, "inventory.db")

# ── Playbook ──────────────────────────────────────────────────────────────────
PLAYBOOK_PATH = os.path.join(DATA_DIR, "playbook.txt")
PLAYBOOK_TOKEN_BUDGET = 4000       # max tokens the playbook may occupy in prompt
MAX_PLAYBOOK_BULLETS = 40          # hard cap on stored bullets

# ── Language Model ─────────────────────────────────────────────────────────────
# Set USE_OFFICIAL_ACE=True to attempt the official ACE library.
# If the library is unavailable or the model is too small, the lightweight
# fallback ACE implementation is used automatically.
USE_OFFICIAL_ACE = True
FALLBACK_TO_LIGHTWEIGHT = True    # always fall back if official ACE fails

MODEL_NAME = "Qwen/Qwen2.5-0.5B-Instruct"   # HuggingFace model id
MAX_NEW_TOKENS = 256               # generation budget per call
TEMPERATURE = 0.3                  # low temp → more deterministic JSON
DO_SAMPLE = True

# ── ACE parameters ─────────────────────────────────────────────────────────────
ACE_MAX_ROUNDS = 2                 # reflector rounds per step
CURATOR_FREQUENCY = 1              # run curator every N steps
SIMILARITY_THRESHOLD = 0.85        # de-duplication threshold

# ── Simulation ─────────────────────────────────────────────────────────────────
REPORT_EVERY_N_STEPS = 10         # send owner report every N steps
AUTO_RUN_INTERVAL_MS = 2000       # ms between auto-run steps (frontend)
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000
FLASK_DEBUG = False

# ── Initial inventory ──────────────────────────────────────────────────────────
INITIAL_INVENTORY = {
    "Coke":        5,
    "Chips":       3,
    "Water":       4,
    "Chocolate":   2,
    "Energy Drink": 1,
}
ITEM_PRICES = {
    "Coke":        2,
    "Chips":       1,
    "Water":       1,
    "Chocolate":   2,
    "Energy Drink": 3,
}
INITIAL_CASH = 10
