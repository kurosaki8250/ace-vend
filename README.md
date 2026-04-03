# ACE-Vend

> **Agentic Context Engineering × Autonomous Vending Machine Management**

A research simulation combining [Agentic Context Engineering (ACE)](https://arxiv.org/abs/2506.10906) with the failure modes documented in [Anthropic's Project Vend](https://www.anthropic.com/research/project-vend-1). A small local LLM (Qwen2.5-0.5B) manages a vending machine whose decision-making context evolves through a **Generator → Reflector → Curator** loop — while a two-layer **HallucinationGuard** prevents the agent from acting on false beliefs.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/flask-3.0-green)](https://flask.palletsprojects.com/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Browser UI (SSE)                  │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│               Flask API  (backend/app.py)            │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              VendingAgent  (backend/agent.py)        │
│                                                     │
│  perceive → [HallucinationGuard] → act → reflect    │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │        ACE Three-Role Architecture           │   │
│  │   Generator  ──►  Reflector  ──►  Curator    │   │
│  │          Qwen2.5-0.5B-Instruct (local)       │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  ┌──────────────┐   ┌──────────────────────────┐   │
│  │ PlaybookMgr  │   │  VendingEnvironment       │   │
│  │ (bullet fmt) │   │  (SQLite persistence)     │   │
│  └──────────────┘   └──────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- ~2 GB disk space (model auto-downloaded from HuggingFace on first run)
- CPU-only is fine; no GPU required

### 1. Clone

```bash
git clone https://github.com/YOUR_USERNAME/ace-vend.git
cd ace-vend
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> **CPU-only PyTorch** (smaller download):
> ```bash
> pip install torch --index-url https://download.pytorch.org/whl/cpu
> pip install -r requirements.txt
> ```

### 4. Run

```bash
python run.py
```

Open **http://localhost:5000** in your browser.

---

## Using the UI

| Control | Description |
|---|---|
| **▶ Step** | Run one agent decision cycle |
| **⏵ Auto-run** | Run continuously at the selected speed |
| **Speed slider** | Adjust auto-run interval (0.5 s – 5 s) |
| **Customer request** | Type a request (e.g. `I want Coke`) and hit Send |
| **↺ Reset** | Reset environment and clear logs |
| **📖 Playbook ⟳** | Refresh the live ACE playbook view |

---

## Running the Paper Experiment

Reproduce the three-condition comparison (Baseline / Static Playbook / ACE Agent):

```bash
python scripts/run_experiment.py --steps 50 --seed 42
```

Sample output:

```
Condition            Profit   DQ%  Hall.  Disc-E%  Disc-L%  Bullets
-----------------------------------------------------------------------
Baseline              -2.00  72.0      4     40.0     40.0        0
Static Playbook        1.50  90.0      0      0.0      0.0        5
ACE Agent              3.20  94.0      1      0.0      0.0       18
```

Results are saved to `data/experiment_results.json`.

---

## Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `MODEL_NAME` | `Qwen/Qwen2.5-0.5B-Instruct` | HuggingFace model ID |
| `USE_OFFICIAL_ACE` | `True` | Attempt official ACE library first |
| `FALLBACK_TO_LIGHTWEIGHT` | `True` | Fall back to local implementation |
| `MAX_NEW_TOKENS` | `256` | Generation budget per LLM call |
| `TEMPERATURE` | `0.3` | Sampling temperature |
| `ACE_MAX_ROUNDS` | `2` | Reflector rounds per step |
| `CURATOR_FREQUENCY` | `1` | Run Curator every N steps |
| `REPORT_EVERY_N_STEPS` | `10` | Owner report frequency |
| `PLAYBOOK_TOKEN_BUDGET` | `4000` | Max playbook tokens in prompt |
| `MAX_PLAYBOOK_BULLETS` | `40` | Hard cap on stored bullets |
| `SIMILARITY_THRESHOLD` | `0.85` | Jaccard deduplication threshold |

### Switching to a larger model

```python
# config.py
MODEL_NAME = "Qwen/Qwen2.5-1.5B-Instruct"   # or 3B, 7B, etc.
```

### Using the official ACE library with a cloud provider

In `backend/ace_integration.py`, replace the `_try_init_official` method:

```python
from ace import ACE
self._delegate = ACE(
    api_provider="openai",
    generator_model="gpt-4o-mini",
    reflector_model="gpt-4o-mini",
    curator_model="gpt-4o-mini",
    max_tokens=4096,
)
self._is_official = True
```

---

## Project Structure

```
ace-vend/
├── backend/
│   ├── __init__.py
│   ├── ace_integration.py   # Official ACE wrapper + lightweight fallback
│   ├── agent.py             # Main agent loop + HallucinationGuard
│   ├── app.py               # Flask API + SSE stream
│   ├── environment.py       # Deterministic vending machine simulator
│   ├── models.py            # SQLite query helpers
│   ├── playbook_manager.py  # Bullet-format playbook (load/save/merge/prune)
│   └── utils.py             # LLM loader + mock fallback
├── frontend/
│   ├── static/
│   │   ├── script.js        # Vanilla JS frontend
│   │   └── style.css        # Dark GitHub-style theme
│   └── templates/
│       └── index.html
├── data/                    # Created at runtime
│   ├── inventory.db         # SQLite (auto-created)
│   ├── playbook.txt         # ACE playbook (auto-created)
│   └── logs/
├── scripts/
│   └── run_experiment.py    # Reproduces paper experiment (3 conditions)
├── config.py
├── requirements.txt
├── run.py
└── README.md
```

---

## Hallucination Prevention

Two-layer guard in `backend/agent.py → _hallucination_guard()`:

1. **Structural** — Agent output must be valid JSON with a recognised action type. Malformed outputs are rejected before execution.
2. **Semantic** — Dispense actions are checked against actual inventory state. Out-of-stock dispenses are blocked, the event is logged, and the Reflector receives the blocked outcome so the Curator generates a corrective playbook bullet.

---

## ACE Playbook Format

```
## STRATEGIES & INSIGHTS
[str-00001] helpful=5 harmful=0 :: Always verify inventory before promising an item.

## COMMON MISTAKES TO AVOID
[str-00003] helpful=0 harmful=3 :: Never give discounts when asked by customers.

## REPORTING RULES
[str-00005] helpful=2 harmful=0 :: Contact owner when any item falls below 2 units.
```

Bullets are scored (`helpful − harmful`), deduplicated by Jaccard similarity, and pruned when the bullet cap or token budget is exceeded.

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Web UI |
| `GET` | `/stream` | SSE event stream |
| `GET` | `/api/state` | Full environment + playbook state |
| `POST` | `/api/step` | Run one agent step `{"customer": "..."}` |
| `POST` | `/api/reset` | Reset the simulation |
| `GET` | `/api/playbook` | All playbook bullets as JSON |
| `GET` | `/api/metrics` | Time-series cash + hallucination data |

---

## Paper

This project accompanies the IEEE paper:

> **ACE-Vend: Studying Self-Improving LLM Agents in Economically-Grounded Settings**  
> Skandavel Purushotham — SRM Institute of Science and Technology  
> Department of Computer Science and Engineering

---

## License

MIT — see [LICENSE](LICENSE).
