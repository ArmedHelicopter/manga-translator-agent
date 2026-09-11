"""Direct unit tests for new LLM providers.

Tests instantiate each provider, mock the HTTP client, and verify
that chat/chat_structured/vision/vision_structured calls produce
expected results and delegate to the correct model.

Providers tested:
- CohereProvider (Cohere SDK)
- GroqProvider (OpenAI-compatible, no vision)
- MistralProvider (OpenAI-compatible, vision)
- MimoProvider (OpenAI-compatible, vision + domain methods)
- GenericOpenAIProvider (OpenAI-compatible, auto vision detection)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ── Shared helpers ───────────────────────────────────────────────────────────────

def _make_openai_response(text: str, model: str = "test-model") -> MagicMock:
    """Create a mock OpenAI ChatCompletion response."""
    message = MagicMock()
    message.content = text

    choice = MagicMock()
    choice.message = message

    response = MagicMock()
    response.choices = [choice]
    response.model = model
    response.usage = MagicMock()
    response.usage.prompt_tokens = 10
    response.usage.completion_tokens = 20
    response.usage.total_tokens = 30

    return response


def _make_cohere_response(text: str) -> MagicMock:
    """Create a mock Cohere chat response."""
    response = MagicMock()
    response.text = text
    response.message = None
    response.prompt_tokens = 10
    response.completion_tokens = 20
    response.total_tokens = 30
    return response


# ── CohereProvider Tests ─────────────────────────────────────────────────────────

class TestCohereProvider:
    """Tests for CohereProvider."""

    @pytest.fixture
    def provider(self):
        """Create a CohereProvider with mocked SDK."""
        mock_cohere = MagicMock()
        mock_client = MagicMock()
        mock_cohere.Client.return_value = mock_client

        with patch.dict("sys.modules", {"cohere": mock_cohere}):
            from mga.providers.cohere_provider import CohereProvider
            p = CohereProvider(api_key="test-key")
            p._client = mock_client
            yield p

    def test_model_name(self, provider):
        assert provider.model_name == "command-a-plus-128k"

    def test_supports_vision_true(self):
        """Test that vision-capable model reports supports_vision=True."""
        mock_cohere = MagicMock()
        with patch.dict("sys.modules", {"cohere": mock_cohere}):
            from mga.providers.cohere_provider import CohereProvider
            p = CohereProvider(api_key="test-key", vision_model="command-a-plus-128k")
            assert p.supports_vision is True

    def test_supports_vision_false(self):
        """Test that non-vision model reports supports_vision=False."""
        mock_cohere = MagicMock()
        with patch.dict("sys.modules", {"cohere": mock_cohere}):
            from mga.providers.cohere_provider import CohereProvider
            p = CohereProvider(api_key="test-key", vision_model="command-r-4b-07-2024")
            assert p.supports_vision is False

    def test_chat(self, provider):
        """Test chat delegates to client.chat with text_model."""
        provider._client.chat.return_value = _make_cohere_response("Hello!")

        messages = [{"role": "user", "content": "Hi"}]
        result = provider.chat(messages)

        assert result == "Hello!"
        provider._client.chat.assert_called_once()
        call_kwargs = provider._client.chat.call_args
        assert call_kwargs[1]["model"] == "command-a-plus-128k"

    def test_chat_structured(self, provider):
        """Test chat_structured returns parsed JSON."""
        json_response = json.dumps({"key": "value"})
        provider._client.chat.return_value = _make_cohere_response(json_response)

        messages = [{"role": "system", "content": "Output JSON"}, {"role": "user", "content": "Hi"}]
        schema = {"type": "object", "properties": {"key": {"type": "string"}}}
        result = provider.chat_structured(messages, schema)

        assert result == {"key": "value"}
        call_kwargs = provider._client.chat.call_args[1]
        assert "response_format" in call_kwargs

    def test_vision_raises_for_non_vision_model(self, provider):
        """Test vision raises ProviderError for non-vision model."""
        from mga.exceptions import ProviderError
        # Default model is command-a-plus-128k which IS vision-capable
        # Create one with a non-vision model
        provider._vision_model = "command-r-4b-07-2024"

        with pytest.raises(ProviderError, match="does not support vision"):
            provider.vision([{"role": "user", "content": "Describe"}], [b"fake-img"])

    def test_cost_per_1k_tokens(self, provider):
        assert provider.cost_per_1k_tokens is not None
        assert provider.cost_per_1k_tokens > 0


# ── GroqProvider Tests ───────────────────────────────────────────────────────────

class TestGroqProvider:
    """Tests for GroqProvider."""

    @pytest.fixture
    def provider(self):
        """Create a GroqProvider with mocked OpenAI client."""
        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client

            from mga.providers.groq_provider import GroqProvider
            p = GroqProvider(api_key="test-key")
            p._client = mock_client
            yield p

    def test_model_name(self, provider):
        assert provider.model_name == "llama-3.3-70b-versatile"

    def test_supports_vision_false(self, provider):
        assert provider.supports_vision is False

    def test_chat(self, provider):
        """Test chat delegates to OpenAI chat.completions.create."""
        provider._client.chat.completions.create.return_value = _make_openai_response("Hello!")

        messages = [{"role": "user", "content": "Hi"}]
        result = provider.chat(messages)

        assert result == "Hello!"
        provider._client.chat.completions.create.assert_called_once()

    def test_chat_structured(self, provider):
        """Test chat_structured adds response_format and parses JSON."""
        json_text = json.dumps({"translation": "translated"})
        provider._client.chat.completions.create.return_value = _make_openai_response(json_text)

        messages = [{"role": "user", "content": "Translate"}]
        schema = {"type": "object"}
        result = provider.chat_structured(messages, schema)

        assert result == {"translation": "translated"}
        call_kwargs = provider._client.chat.completions.create.call_args[1]
        assert call_kwargs["response_format"] == {"type": "json_object"}

    def test_vision_raises_provider_error(self, provider):
        """Test vision always raises ProviderError."""
        from mga.exceptions import ProviderError
        with pytest.raises(ProviderError, match="does not support vision"):
            provider.vision([{"role": "user", "content": "Look"}], [b"img"])

    def test_vision_structured_raises_provider_error(self, provider):
        """Test vision_structured always raises ProviderError."""
        from mga.exceptions import ProviderError
        with pytest.raises(ProviderError, match="does not support vision"):
            provider.vision_structured([{"role": "user", "content": "Look"}], [b"img"], schema={"type": "object"})

    def test_cost_per_1k_tokens(self, provider):
        assert provider.cost_per_1k_tokens is not None

    def test_custom_model(self):
        """Test custom model configuration."""
        with patch("openai.OpenAI"):
            from mga.providers.groq_provider import GroqProvider
            p = GroqProvider(api_key="test", model="mixtral-8x7b-32768")
            assert p.model_name == "mixtral-8x7b-32768"


# ── MistralProvider Tests ────────────────────────────────────────────────────────

class TestMistralProvider:
    """Tests for MistralProvider."""

    @pytest.fixture
    def provider(self):
        """Create a MistralProvider with mocked OpenAI client."""
        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client

            from mga.providers.mistral_provider import MistralProvider
            p = MistralProvider(api_key="test-key")
            p._client = mock_client
            yield p

    def test_model_name(self, provider):
        assert provider.model_name == "mistral-large-latest"

    def test_supports_vision_true(self):
        """Test vision-capable model."""
        with patch("openai.OpenAI"):
            from mga.providers.mistral_provider import MistralProvider
            p = MistralProvider(api_key="test", vision_model="pixtral-12b-2409")
            assert p.supports_vision is True

    def test_supports_vision_false(self):
        """Test non-vision model."""
        with patch("openai.OpenAI"):
            from mga.providers.mistral_provider import MistralProvider
            p = MistralProvider(api_key="test", vision_model="mistral-small-latest")
            assert p.supports_vision is False

    def test_chat_uses_text_model(self, provider):
        """Test chat delegates to text_model, not vision_model."""
        provider._client.chat.completions.create.return_value = _make_openai_response("Bonjour")

        provider.chat([{"role": "user", "content": "Hi"}])

        call_kwargs = provider._client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "mistral-small-latest"  # text_model default

    def test_chat_structured(self, provider):
        """Test chat_structured returns parsed JSON."""
        provider._client.chat.completions.create.return_value = _make_openai_response('{"result": true}')

        result = provider.chat_structured(
            [{"role": "user", "content": "Check"}],
            schema={"type": "object"},
        )
        assert result == {"result": True}

    def test_timeout_passed_to_client_and_requests(self):
        """Mimo timeout config should bound provider calls."""
        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = _make_openai_response("ok")
            mock_openai_cls.return_value = mock_client

            from mga.providers.mimo_provider import MimoProvider
            provider = MimoProvider(api_key="test-key", timeout=7)
            provider.chat([{"role": "user", "content": "Hi"}])

        assert mock_openai_cls.call_args.kwargs["timeout"] == 7
        assert mock_client.chat.completions.create.call_args.kwargs["timeout"] == 7

    def test_vision_injects_images(self, provider):
        """Test vision injects images into messages."""
        provider._vision_model = "pixtral-12b-2409"  # Make it vision-capable
        provider._client.chat.completions.create.return_value = _make_openai_response("I see a cat")

        result = provider.vision(
            [{"role": "user", "content": "Describe"}],
            [b"\x89PNG\r\n"],
        )

        assert result == "I see a cat"
        call_kwargs = provider._client.chat.completions.create.call_args[1]
        # Messages should be modified with image injection
        messages = call_kwargs["messages"]
        last_msg = messages[-1]
        assert isinstance(last_msg["content"], list)
        assert any(part.get("type") == "image_url" for part in last_msg["content"])

    def test_vision_structured(self, provider):
        """Test vision_structured adds response_format and parses JSON."""
        provider._vision_model = "pixtral-12b-2409"
        provider._client.chat.completions.create.return_value = _make_openai_response('{"label": "cat"}')

        result = provider.vision_structured(
            [{"role": "user", "content": "Describe"}],
            [b"\x89PNG\r\n"],
            schema={"type": "object"},
        )
        assert result == {"label": "cat"}
        call_kwargs = provider._client.chat.completions.create.call_args[1]
        assert call_kwargs["response_format"] == {"type": "json_object"}

    def test_cost_per_1k_tokens(self, provider):
        assert provider.cost_per_1k_tokens is not None


# ── MimoProvider Tests ───────────────────────────────────────────────────────────

class TestMimoProvider:
    """Tests for MimoProvider."""

    @pytest.fixture
    def provider(self):
        """Create a MimoProvider with mocked OpenAI client."""
        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client

            from mga.providers.mimo_provider import MimoProvider
            p = MimoProvider(api_key="test-key")
            p._client = mock_client
            yield p

    def test_model_name(self, provider):
        assert provider.model_name == "mimo-v2.5-pro"

    def test_supports_vision_true(self, provider):
        assert provider.supports_vision is True

    def test_cost_per_1k_tokens_none(self, provider):
        assert provider.cost_per_1k_tokens is None

    def test_chat(self, provider):
        """Test chat delegates to OpenAI client."""
        provider._client.chat.completions.create.return_value = _make_openai_response("你好")

        result = provider.chat([{"role": "user", "content": "Hi"}])
        assert result == "你好"

    def test_chat_structured(self, provider):
        """Test chat_structured adds json_object format."""
        provider._client.chat.completions.create.return_value = _make_openai_response('{"text": "你好"}')

        result = provider.chat_structured(
            [{"role": "user", "content": "Translate"}],
            schema={"type": "object"},
        )
        assert result == {"text": "你好"}
        call_kwargs = provider._client.chat.completions.create.call_args[1]
        assert call_kwargs["response_format"] == {"type": "json_object"}

    def test_vision_injects_images(self, provider):
        """Test vision injects base64 image parts."""
        provider._client.chat.completions.create.return_value = _make_openai_response("manga text")

        result = provider.vision(
            [{"role": "user", "content": "Extract"}],
            [b"fake-image-bytes"],
        )
        assert result == "manga text"

    def test_vision_structured(self, provider):
        """Test vision_structured combines images + JSON format."""
        provider._client.chat.completions.create.return_value = _make_openai_response('{"bubbles": []}')

        result = provider.vision_structured(
            [{"role": "user", "content": "Extract"}],
            [b"fake-image-bytes"],
            schema={"type": "object"},
        )
        assert result == {"bubbles": []}


# ── GenericOpenAIProvider Tests ──────────────────────────────────────────────────

class TestGenericOpenAIProvider:
    """Tests for GenericOpenAIProvider."""

    def test_requires_base_url(self):
        """Test that GenericOpenAIProvider raises ProviderError without base_url."""
        from mga.exceptions import ProviderError
        with patch("openai.OpenAI"):
            from mga.providers.generic_provider import GenericOpenAIProvider
            with pytest.raises(ProviderError, match="requires base_url"):
                GenericOpenAIProvider(api_key="test")

    @pytest.fixture
    def provider(self):
        """Create a GenericOpenAIProvider with mocked OpenAI client."""
        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client

            from mga.providers.generic_provider import GenericOpenAIProvider
            p = GenericOpenAIProvider(
                api_key="test-key",
                base_url="https://api.example.com/v1",
                model="custom-model",
            )
            p._client = mock_client
            yield p

    def test_model_name(self, provider):
        assert provider.model_name == "custom-model"

    def test_supports_vision_explicit_true(self):
        """Test explicit vision support override."""
        with patch("openai.OpenAI"):
            from mga.providers.generic_provider import GenericOpenAIProvider
            p = GenericOpenAIProvider(
                api_key="test", base_url="https://api.example.com/v1",
                supports_vision=True,
            )
            assert p.supports_vision is True

    def test_supports_vision_explicit_false(self):
        """Test explicit vision disable override."""
        with patch("openai.OpenAI"):
            from mga.providers.generic_provider import GenericOpenAIProvider
            p = GenericOpenAIProvider(
                api_key="test", base_url="https://api.example.com/v1",
                supports_vision=False,
            )
            assert p.supports_vision is False

    def test_cost_per_1k_tokens_none(self, provider):
        assert provider.cost_per_1k_tokens is None

    def test_chat(self, provider):
        """Test chat delegates to OpenAI client."""
        provider._client.chat.completions.create.return_value = _make_openai_response("Response")

        result = provider.chat([{"role": "user", "content": "Hello"}])
        assert result == "Response"

    def test_chat_structured(self, provider):
        """Test chat_structured adds json_object format."""
        provider._client.chat.completions.create.return_value = _make_openai_response('{"ok": true}')

        result = provider.chat_structured(
            [{"role": "user", "content": "Check"}],
            schema={"type": "object"},
        )
        assert result == {"ok": True}

    def test_vision_injects_images(self, provider):
        """Test vision injects base64 images into messages."""
        provider._explicit_vision = True  # Skip auto-detect
        provider._client.chat.completions.create.return_value = _make_openai_response("I see text")

        result = provider.vision(
            [{"role": "user", "content": "Describe"}],
            [b"fake-image-bytes"],
        )
        assert result == "I see text"

    def test_vision_structured(self, provider):
        """Test vision_structured combines images + JSON format."""
        provider._explicit_vision = True
        provider._client.chat.completions.create.return_value = _make_openai_response('{"text": "hello"}')

        result = provider.vision_structured(
            [{"role": "user", "content": "Describe"}],
            [b"fake-image-bytes"],
            schema={"type": "object"},
        )
        assert result == {"text": "hello"}

    def test_vision_auto_detect_caches_result(self, provider):
        """Test that auto vision detection caches its result."""
        provider._explicit_vision = None
        provider._vision_detected = True  # Simulate previous detection

        assert provider.supports_vision is True
        # Should not call the API again

    def test_no_model_name_fallback(self):
        """Test model_name returns 'unknown' when no model set."""
        with patch("openai.OpenAI"):
            from mga.providers.generic_provider import GenericOpenAIProvider
            p = GenericOpenAIProvider(
                api_key="test",
                base_url="https://api.example.com/v1",
            )
            assert p.model_name == "unknown"
