# backend/utils.py — LLM loader with HuggingFace + mock fallback

import logging
import json
import re
from config import MODEL_NAME, MAX_NEW_TOKENS, TEMPERATURE, DO_SAMPLE

log = logging.getLogger(__name__)

_model = None
_tokenizer = None
_use_mock = False


def load_model():
    """Load the HuggingFace model; fall back to mock if unavailable."""
    global _model, _tokenizer, _use_mock
    if _model is not None:
        return
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch
        log.info("Loading tokenizer: %s", MODEL_NAME)
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        log.info("Loading model: %s (this may take a while on first run)", MODEL_NAME)
        _model = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            torch_dtype=torch.float32,
            device_map="cpu",
        )
        _model.eval()
        log.info("Model loaded successfully.")
    except Exception as exc:
        log.warning("Could not load model (%s). Using mock LLM.", exc)
        _use_mock = True


def generate(prompt: str, max_new_tokens: int = MAX_NEW_TOKENS) -> str:
    """Generate text from the LLM or the mock fallback."""
    if _use_mock:
        return _mock_generate(prompt)
    try:
        import torch
        inputs = _tokenizer(prompt, return_tensors="pt")
        with torch.no_grad():
            output_ids = _model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=TEMPERATURE,
                do_sample=DO_SAMPLE,
                pad_token_id=_tokenizer.eos_token_id,
            )
        new_ids = output_ids[0][inputs["input_ids"].shape[1]:]
        return _tokenizer.decode(new_ids, skip_special_tokens=True)
    except Exception as exc:
        log.error("Generation error: %s", exc)
        return _mock_generate(prompt)


def extract_json(text: str) -> dict | None:
    """Extract the first JSON object found in text."""
    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


# ── Mock LLM ────────────────────────────────────────────────────────────────

_MOCK_ACTIONS = [
    '{"type": "check_inventory"}',
    '{"type": "dispense", "item": "Coke", "payment": 2}',
    '{"type": "dispense", "item": "Chips", "payment": 1}',
    '{"type": "idle", "reason": "No customer requests pending."}',
    '{"type": "contact_owner", "message": "All systems nominal. Cash balance: $10."}',
]
_mock_idx = 0


def _mock_generate(prompt: str) -> str:
    global _mock_idx
    action = _MOCK_ACTIONS[_mock_idx % len(_MOCK_ACTIONS)]
    _mock_idx += 1
    if "REFLECT" in prompt or "LABEL" in prompt:
        return "LABEL: helpful\nINSIGHT: Always verify inventory before dispensing.\nSECTION: strategies"
    return f"REASONING: Proceeding with standard operation.\nACTION: {action}"
