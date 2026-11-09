import os
import unittest
from unittest.mock import patch

from emporio_agent.config import PROVIDERS, llm_settings


class LLMSettingsTest(unittest.TestCase):
    def test_defaults_to_gemini(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test"}, clear=True):
            settings = llm_settings()
        self.assertEqual(settings.base_url, PROVIDERS["gemini"].base_url)
        self.assertEqual(settings.model, PROVIDERS["gemini"].default_model)

    def test_switches_provider_through_environment(self):
        env = {"LLM_PROVIDER": "groq", "GROQ_API_KEY": "test"}
        with patch.dict(os.environ, env, clear=True):
            settings = llm_settings()
        self.assertEqual(settings.base_url, PROVIDERS["groq"].base_url)
        self.assertEqual(settings.api_key, "test")

    def test_model_can_be_overridden(self):
        env = {"GEMINI_API_KEY": "test", "LLM_MODEL": "other-model"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(llm_settings().model, "other-model")

    def test_empty_model_falls_back_to_default(self):
        env = {"GEMINI_API_KEY": "test", "LLM_MODEL": ""}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(llm_settings().model, PROVIDERS["gemini"].default_model)

    def test_missing_key_names_the_variable(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "GEMINI_API_KEY"):
                llm_settings()

    def test_unknown_provider_is_rejected(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "nope"}, clear=True):
            with self.assertRaisesRegex(ValueError, "nope"):
                llm_settings()


if __name__ == "__main__":
    unittest.main()
