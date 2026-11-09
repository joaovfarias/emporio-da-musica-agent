"""Client for the configured LLM provider, through its OpenAI-compatible API."""
from openai import OpenAI

from emporio_agent.config import LLMSettings


def create_client(settings: LLMSettings) -> OpenAI:
    return OpenAI(base_url=settings.base_url, api_key=settings.api_key)
