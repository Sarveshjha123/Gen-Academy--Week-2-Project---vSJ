"""The brain. One place to create the LLM, so swapping provider = editing .env only ("LLM swappable")."""
import json
import re
from functools import lru_cache

from langchain_openai import ChatOpenAI

from src import config


@lru_cache(maxsize=1)
def get_llm():
    # Nebius speaks the same "language" as OpenAI, so we use ChatOpenAI with Nebius's address (base_url).
    # temperature=0 + seed = as repeatable as the provider allows. 8000 tokens so long briefs are not cut off
    # (reasoning models like gpt-oss also spend tokens "thinking" before they write).
    # Optional speed-up: REASONING_EFFORT=low in .env makes reasoning models (gpt-oss) think less → faster answers.
    extra = {"extra_body": {"reasoning_effort": config.REASONING_EFFORT}} if config.REASONING_EFFORT else {}
    return ChatOpenAI(model=config.CHAT_MODEL, api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL,
                      temperature=0, seed=42, max_tokens=8000, **extra)


def read_json(text, default):
    """LLMs sometimes wrap JSON in extra words. Grab the {...} part; if that fails, use a safe default."""
    match = re.search(r"\{.*\}", text or "", re.S)
    try:
        return json.loads(match.group(0)) if match else default
    except json.JSONDecodeError:
        return default
