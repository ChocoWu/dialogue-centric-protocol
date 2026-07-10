"""Anthropic-backed provider (D7). Anthropic Python SDK only; kept in its own module.

Uses ``messages.create`` for text and ``messages.parse`` (verified present in anthropic>=0.116)
for schema-validated output, per the claude-api reference. No ``thinking`` param is sent so the
provider works across model tiers; callers pick the model via the binding.
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from ..errors import ProviderError

M = TypeVar("M", bound=BaseModel)

_MAX_TOKENS = 4096


class AnthropicProvider:
    """A :class:`~dcp.provider.base.ModelProvider` backed by the Anthropic Messages API."""

    def __init__(
        self, model: str, *, api_key: str | None = None, client: Any | None = None
    ) -> None:
        self.model = model
        if client is not None:
            self._client: Any = client
        else:
            from anthropic import AsyncAnthropic  # lazy

            self._client = AsyncAnthropic(api_key=api_key)  # api_key=None -> ANTHROPIC_API_KEY env

    async def text(self, *, instructions: str, content: str) -> str:
        try:
            resp = await self._client.messages.create(
                model=self.model,
                max_tokens=_MAX_TOKENS,
                system=instructions,
                messages=[{"role": "user", "content": content}],
            )
            parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
            return str("".join(parts))
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"anthropic text call failed: {exc}") from exc

    async def structured(self, *, instructions: str, content: str, schema: type[M]) -> M:
        try:
            resp = await self._client.messages.parse(
                model=self.model,
                max_tokens=_MAX_TOKENS,
                system=instructions,
                messages=[{"role": "user", "content": content}],
                output_format=schema,
            )
            parsed = resp.parsed_output
            if parsed is None:
                raise ProviderError("anthropic returned no parsed structured output")
            return schema.model_validate(parsed.model_dump())
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"anthropic structured call failed: {exc}") from exc


__all__ = ["AnthropicProvider"]
