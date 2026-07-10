"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class LLMProvider(ABC):
    """Base class for all LLM provider implementations.

    Concrete providers must implement the chat and vision methods.
    The structured variants accept a JSON schema and return parsed dicts.
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier."""

    @property
    @abstractmethod
    def supports_vision(self) -> bool:
        """Whether this provider supports vision/image inputs."""

    @property
    @abstractmethod
    def cost_per_1k_tokens(self) -> Optional[float]:
        """Cost per 1000 tokens in USD, or None if unknown."""

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        """Send a chat completion request."""

    @abstractmethod
    def chat_structured(
        self,
        messages: List[Dict[str, Any]],
        schema: Dict[str, Any],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Send a chat completion request with structured output."""

    @abstractmethod
    def vision(
        self,
        messages: List[Dict[str, Any]],
        images: List[bytes],
        **kwargs: Any,
    ) -> str:
        """Send a vision completion request with images."""

    @abstractmethod
    def vision_structured(
        self,
        messages: List[Dict[str, Any]],
        images: List[bytes],
        schema: Dict[str, Any],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Send a vision completion request with structured output."""
