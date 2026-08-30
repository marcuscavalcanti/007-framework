#!/usr/bin/env python3
"""Price sanitized token counts with Headroom's LiteLLM model database."""

import json
import sys
from importlib.metadata import version

import litellm
from headroom.pricing.litellm_pricing import pricing_lookup_candidates


def quote(item):
    model = item.get("model")
    candidate = next(
        (name for name in pricing_lookup_candidates(model) if name in litellm.model_cost),
        None,
    ) if isinstance(model, str) else None
    common = {
        "pricing_model": candidate,
        "pricing_source": "headroom/litellm",
        "pricing_version": f"headroom={version('headroom-ai')};litellm={version('litellm')}",
    }
    if candidate is None:
        return {"cost_usd": None, **common}
    try:
        prompt_cost, output_cost = litellm.cost_per_token(
            model=candidate,
            prompt_tokens=int(item.get("prompt_tokens") or 0),
            completion_tokens=int(item.get("completion_tokens") or 0),
            cache_read_input_tokens=int(item.get("cache_read_input_tokens") or 0),
            cache_creation_input_tokens=int(item.get("cache_creation_input_tokens") or 0),
        )
        one_hour = int(item.get("cache_creation_1h_input_tokens") or 0)
        if one_hour:
            info = litellm.model_cost[candidate]
            five_minute = info.get("cache_creation_input_token_cost")
            one_hour_rate = info.get("cache_creation_input_token_cost_above_1hr")
            thresholded = any(
                key.startswith("cache_creation_input_token_cost_above_")
                and key != "cache_creation_input_token_cost_above_1hr"
                for key in info
            )
            if five_minute is None or one_hour_rate is None or thresholded:
                return {"cost_usd": None, **common}
            prompt_cost += one_hour * (float(one_hour_rate) - float(five_minute))
        return {"cost_usd": round(float(prompt_cost) + float(output_cost), 6), **common}
    except (TypeError, ValueError):
        return {"cost_usd": None, **common}


def main():
    requests = json.load(sys.stdin)
    if not isinstance(requests, list):
        raise ValueError("pricing input must be a list")
    json.dump([quote(item) for item in requests], sys.stdout, separators=(",", ":"))


if __name__ == "__main__":
    main()
