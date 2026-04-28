# backend/utils.py — LLM loader with HuggingFace + proper error handling
# 
# This module handles loading the Qwen model from HuggingFace.
# If the model fails to load, it raises an error instead of silently
# falling back to a mock. Users can explicitly enable mock mode via
# the USE_MOCK environment variable for testing purposes.

import logging
import json
import re
import os
from config import MODEL_NAME, MAX_NEW_TOKENS, TEMPERATURE, DO_SAMPLE

log = logging.getLogger(__name__)

_model = None
_tokenizer = None
_use_mock = os.environ.get("USE_MOCK", "0").lower() in ("1", "true", "yes")


def load_model():
    """
    Load the HuggingFace model.
    
    Raises:
        RuntimeError: If the model cannot be loaded and USE_MOCK is not enabled.
    """
    global _model, _tokenizer, _use_mock
    if _model is not None:
        return
    
    # If mock mode is explicitly requested, skip loading real model
    if _use_mock:
        log.warning("Mock LLM mode enabled via USE_MOCK environment variable.")
        return
    
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch
        
        log.info("Loading tokenizer: %s", MODEL_NAME)
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        
        # Set pad_token if not already set (MODERATE 8 fix)
        if _tokenizer.pad_token is None:
            _tokenizer.pad_token = _tokenizer.eos_token
            _tokenizer.pad_token_id = _tokenizer.eos_token_id
        
        log.info("Loading model: %s (this may take a while on first run)", MODEL_NAME)
        _model = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            torch_dtype=torch.float32,
            device_map="cpu",
        )
        _model.eval()
        log.info("Model loaded successfully.")
        
    except ImportError as exc:
        log.error("Required package not installed: %s", exc)
        log.error("Please install dependencies: pip install -r requirements.txt")
        raise RuntimeError(f"Failed to load model due to missing dependency: {exc}") from exc
    except OSError as exc:
        log.error("Failed to download/load model from HuggingFace: %s", exc)
        log.error("Check your internet connection or set USE_MOCK=1 for testing.")
        raise RuntimeError(f"Failed to load model from HuggingFace: {exc}") from exc
    except Exception as exc:
        log.error("Unexpected error loading model: %s", exc)
        raise RuntimeError(f"Unexpected error loading model: {exc}") from exc


def check_model_loaded():
    """
    Verify that the model is loaded and ready.
    
    Raises:
        RuntimeError: If the model is not available.
    """
    if _use_mock:
        log.warning("Running in MOCK mode. LLM outputs will be canned responses.")
        return
    if _model is None:
        raise RuntimeError("Model not loaded. Call load_model() first.")
    log.info("Model check passed: %s is ready.", MODEL_NAME)


def generate(prompt: str, max_new_tokens: int = MAX_NEW_TOKENS) -> str:
    """
    Generate text from the LLM using proper chat template formatting.
    
    Args:
        prompt: The user prompt text.
        max_new_tokens: Maximum number of tokens to generate.
    
    Returns:
        Generated text string.
    
    Raises:
        RuntimeError: If the model is not loaded.
    """
    if _use_mock:
        return _mock_generate(prompt)
    
    if _model is None or _tokenizer is None:
        raise RuntimeError("Model not loaded. Ensure load_model() was called successfully.")
    
    try:
        import torch
        from transformers import AutoTokenizer
        
        # CRITICAL 3 fix: Use proper chat template for instruction-tuned models
        messages = [
            {"role": "system", "content": "You are an intelligent vending machine agent. Respond concisely with valid JSON actions."},
            {"role": "user", "content": prompt}
        ]
        
        # Apply chat template if available
        if hasattr(_tokenizer, 'apply_chat_template'):
            text = _tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        else:
            # Fallback to simple concatenation if template not available
            text = f"System: You are an intelligent vending machine agent.\n\nUser: {prompt}\n\nAssistant:"
        
        inputs = _tokenizer(text, return_tensors="pt").to(_model.device)
        
        with torch.no_grad():
            output_ids = _model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=TEMPERATURE,
                do_sample=DO_SAMPLE,
                pad_token_id=_tokenizer.pad_token_id,  # MODERATE 8 fix: use explicit pad_token_id
            )
        
        new_ids = output_ids[0][inputs["input_ids"].shape[1]:]
        return _tokenizer.decode(new_ids, skip_special_tokens=True)
        
    except Exception as exc:
        log.error("Generation error: %s", exc)
        raise RuntimeError(f"Generation failed: {exc}") from exc


def extract_json(text: str) -> dict | None:
    """
    Extract a JSON object from text using balanced brace matching.
    
    This is more robust than simple regex for multi-line JSON output.
    """
    # First try to find balanced braces using a stack-based approach
    start_idx = -1
    brace_count = 0
    
    for i, char in enumerate(text):
        if char == '{':
            if brace_count == 0:
                start_idx = i
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0 and start_idx != -1:
                # Found a complete balanced JSON object
                json_str = text[start_idx:i+1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass
                # If parsing failed, continue looking for other objects
                start_idx = -1
    
    # Fallback: try simple regex for edge cases
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
