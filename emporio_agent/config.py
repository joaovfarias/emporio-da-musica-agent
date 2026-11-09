"""Paths and settings."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
POLICIES_PDF = DATA_DIR / "store_policies.pdf"
CSV_TABLES = ("categories", "customers", "orders", "order_items", "products", "promotions")


@dataclass(frozen=True)
class Provider:
    base_url: str
    api_key_env: str
    default_model: str


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    api_key: str
    model: str


PROVIDERS = {
    "groq": Provider(
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        default_model="qwen/qwen3.8-27b",
    ),
    "gemini": Provider(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key_env="GEMINI_API_KEY",
        default_model="gemini-3.5-flash-lite",
    ),
}
DEFAULT_PROVIDER = "groq"


def llm_settings() -> LLMSettings:
    """Resolve the LLM connection from the environment, failing with an actionable message."""
    name = os.environ.get("LLM_PROVIDER") or DEFAULT_PROVIDER
    provider = PROVIDERS.get(name)
    if provider is None:
        raise ValueError(f"Unknown LLM_PROVIDER '{name}'. Choose one of: {', '.join(PROVIDERS)}.")
    api_key = os.environ.get(provider.api_key_env)
    if not api_key:
        raise ValueError(f"{provider.api_key_env} is not set. Add it to your .env file.")
    return LLMSettings(
        base_url=provider.base_url,
        api_key=api_key,
        model=os.environ.get("LLM_MODEL") or provider.default_model,
    )
