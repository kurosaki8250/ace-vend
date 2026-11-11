"""Configuration.

Everything is read from the environment (optionally via a ``.env`` file) with
sane defaults, so the project runs with zero configuration and no API key.

A tiny ``.env`` parser is included on purpose: it keeps the dependency list
short and makes the import path side-effect free.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def load_dotenv(path: Path) -> None:
    """Load ``KEY=value`` pairs from *path* without overwriting real env vars."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


load_dotenv(ROOT / ".env")


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name, "")
    return value.strip() if value.strip() else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    """Runtime settings. Construct directly in tests to avoid global state."""

    # Which decision backend to use: "offline" | "openai" | "ollama"
    backend: str = "offline"

    # OpenAI-compatible endpoint (works with any compatible gateway)
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"

    # Ollama endpoint
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    temperature: float = 0.2
    max_tokens: int = 400
    request_timeout: int = 60

    # Simulation
    seed: int = 42
    steps: int = 60

    # ACE playbook
    max_bullets: int = 24
    bullet_token_budget: int = 600
    dedup_threshold: float = 0.82
    curator_every: int = 1
    reflector_rounds: int = 1

    # Web UI
    host: str = "127.0.0.1"
    port: int = 5000

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            backend=_env_str("LLM_BACKEND", "offline").lower(),
            openai_api_key=_env_str("OPENAI_API_KEY", ""),
            openai_base_url=_env_str("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=_env_str("LLM_MODEL", "gpt-4o-mini"),
            ollama_url=_env_str("OLLAMA_URL", "http://localhost:11434"),
            ollama_model=_env_str("OLLAMA_MODEL", "qwen2.5:7b"),
            temperature=_env_float("LLM_TEMPERATURE", 0.2),
            max_tokens=_env_int("LLM_MAX_TOKENS", 400),
            request_timeout=_env_int("LLM_TIMEOUT", 60),
            seed=_env_int("SEED", 42),
            steps=_env_int("STEPS", 60),
            max_bullets=_env_int("MAX_BULLETS", 24),
            bullet_token_budget=_env_int("BULLET_TOKEN_BUDGET", 600),
            dedup_threshold=_env_float("DEDUP_THRESHOLD", 0.82),
            curator_every=_env_int("CURATOR_EVERY", 1),
            reflector_rounds=_env_int("REFLECTOR_ROUNDS", 1),
            host=_env_str("HOST", "127.0.0.1"),
            port=_env_int("PORT", 5000),
        )

    def describe(self) -> dict:
        """Safe-to-log view: never includes secrets."""
        return {
            "backend": self.backend,
            "model": self.model if self.backend != "offline" else "offline-heuristic",
            "seed": self.seed,
            "steps": self.steps,
            "max_bullets": self.max_bullets,
            "bullet_token_budget": self.bullet_token_budget,
            "dedup_threshold": self.dedup_threshold,
        }


def get_settings() -> Settings:
    """Fresh settings read from the environment."""
    return Settings.from_env()


def ensure_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR
