#!/usr/bin/env python3
"""
OpenRouter model catalog fetcher with caching.

Fetches available models from OpenRouter's /api/v1/models endpoint,
caches the response for 1 hour, and returns models grouped by provider
with pricing information.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".hermes" / "cache"
_CACHE_FILE = _CACHE_DIR / "openrouter_models.json"
_CACHE_TTL = 3600  # 1 hour


def _fmt_price(price_str: str) -> str:
    """Convert '0.0000025' → '$2.50' per M tokens."""
    try:
        per_m = float(price_str) * 1_000_000
        if per_m == 0:
            return "free"
        if per_m < 0.01:
            return f"${per_m:.4f}"
        return f"${per_m:.2f}"
    except (ValueError, TypeError):
        return "?"


def _fetch_openrouter_models(api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch models from OpenRouter API, with 1-hour file cache.

    Returns list of model dicts with keys: id, name, provider, pricing, context_length.
    Returns empty list on failure.
    """
    key = api_key or os.getenv("OPENROUTER_API_KEY")
    if not key:
        return []

    # Check cache
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if _CACHE_FILE.exists():
            cache_age = time.time() - _CACHE_FILE.stat().st_mtime
            if cache_age < _CACHE_TTL:
                data = json.loads(_CACHE_FILE.read_text())
                logger.debug("Using cached OpenRouter models (%d models, %.0fs old)",
                             len(data), cache_age)
                return data
    except Exception:
        pass

    # Fetch from API
    try:
        req = Request(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        with urlopen(req, timeout=10) as resp:
            body = resp.read().decode()
            raw = json.loads(body)
    except (URLError, json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to fetch OpenRouter models: %s", exc)
        # Return stale cache if available
        try:
            if _CACHE_FILE.exists():
                return json.loads(_CACHE_FILE.read_text())
        except Exception:
            pass
        return []

    # Parse and filter
    models = []
    for m in raw.get("data", []):
        model_id = m.get("id", "")
        if not model_id or ":" in model_id:  # skip aliases like "openai:gpt-4o"
            continue
        pricing = m.get("pricing", {})
        models.append({
            "id": model_id,
            "name": m.get("name", model_id),
            "provider": _provider_display(model_id),
            "pricing_prompt": _fmt_price(pricing.get("prompt", "0")),
            "pricing_completion": _fmt_price(pricing.get("completion", "0")),
            "context_length": m.get("context_length", 0),
        })

    # Cache
    try:
        _CACHE_FILE.write_text(json.dumps(models))
        logger.debug("Cached %d OpenRouter models", len(models))
    except Exception:
        pass

    return models


def _provider_display(model_id: str) -> str:
    """Extract a readable provider name from a model ID.

    'anthropic/claude-sonnet-4' → 'Anthropic'
    'openai/gpt-4o' → 'OpenAI'
    'meta-llama/llama-4-maverick' → 'Meta'
    """
    if "/" not in model_id:
        return "Other"
    prefix = model_id.split("/")[0]
    # Map common prefixes to readable names
    provider_map = {
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "google": "Google",
        "meta-llama": "Meta",
        "deepseek": "DeepSeek",
        "mistralai": "Mistral",
        "qwen": "Qwen",
        "nousresearch": "Nous",
        "x-ai": "xAI",
        "nvidia": "NVIDIA",
        "minimax": "MiniMax",
        "cohere": "Cohere",
        "ai21": "AI21",
        "amazon": "Amazon",
        "baidu": "Baidu",
        "microsoft": "Microsoft",
        "perplexity": "Perplexity",
        "openrouter": "OpenRouter",
    }
    return provider_map.get(prefix, prefix.replace("-", " ").title())


def get_model_tree() -> List[Dict[str, Any]]:
    """Build a grouped model tree for the curses tree checklist.

    Returns list of group dicts:
        [{name, expanded, items: [{id, label, pricing, checked}]}]

    Includes both OpenRouter models (from API) and direct provider models.
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    seen_ids: set = set()

    # --- OpenRouter models (from API) ---
    if os.getenv("OPENROUTER_API_KEY"):
        or_models = _fetch_openrouter_models()
        for m in or_models:
            mid = m["id"]
            if mid in seen_ids:
                continue
            seen_ids.add(mid)
            provider = m["provider"]
            if provider not in groups:
                groups[provider] = []
            model_name = mid.split("/")[-1] if "/" in mid else mid
            groups[provider].append({
                "id": mid,
                "provider": "openrouter",
                "model": mid,
                "key": "OPENROUTER_API_KEY",
                "label": f"{model_name:<30s} ${m['pricing_prompt']:>6s}/${m['pricing_completion']:<6s} per M",
                "checked": False,
            })

    # --- Direct provider models ---
    direct_providers = [
        ("ANTHROPIC_API_KEY", "anthropic", "claude-sonnet-4-20250514", "Anthropic (direct)"),
        ("ANTHROPIC_API_KEY", "anthropic", "claude-opus-4-20250514", "Anthropic (direct)"),
        ("OPENAI_API_KEY", "openai", "gpt-4o", "OpenAI (direct)"),
        ("OPENAI_API_KEY", "openai", "gpt-4.1", "OpenAI (direct)"),
        ("DEEPSEEK_API_KEY", "deepseek", "deepseek-chat", "DeepSeek (direct)"),
        ("DEEPSEEK_API_KEY", "deepseek", "deepseek-reasoner", "DeepSeek (direct)"),
    ]
    for key_env, provider, model, group_name in direct_providers:
        if not os.getenv(key_env):
            continue
        mid = f"{provider}/{model}"
        if mid in seen_ids:
            continue
        seen_ids.add(mid)
        if group_name not in groups:
            groups[group_name] = []
        groups[group_name].append({
            "id": mid,
            "provider": provider,
            "model": model,
            "key": key_env,
            "label": f"{model:<30s}  (direct)",
            "checked": False,
        })

    # Sort groups and items
    sorted_groups = []
    for name in sorted(groups):
        items = sorted(groups[name], key=lambda i: i["label"])
        sorted_groups.append({
            "name": name,
            "expanded": False,
            "items": items,
        })

    return sorted_groups
