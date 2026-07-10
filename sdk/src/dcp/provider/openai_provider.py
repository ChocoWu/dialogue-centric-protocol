"""OpenAI-backed provider (D7). OpenAI Python SDK only; kept in its own module.

Uses ``chat.completions.create`` for text and the GA structured-outputs
``chat.completions.parse`` (verified present in openai>=2) for schema-validated output.
Client construction is lazy so importing this module needs no key/network; tests inject a stub.
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from ..errors import ProviderError

M = TypeVar("M", bound=BaseModel)


class OpenAIProvider:
    """A :class:`~dcp.provider.base.ModelProvider` backed by OpenAI chat completions."""

    def __init__(
        self, model: str, *, api_key: str | None = None, client: Any | None = None
    ) -> None:
        self.model = model
        if client is not None:
            self._client: Any = client
        else:
            from openai import AsyncOpenAI  # lazy: no import cost / key check until used

            self._client = AsyncOpenAI(api_key=api_key)  # api_key=None -> OPENAI_API_KEY env

    def _messages(self, instructions: str, content: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": instructions},
            {"role": "user", "content": content},
        ]

    async def text(self, *, instructions: str, content: str) -> str:
        try:
            resp = await self._client.chat.completions.create(
                model=self.model, messages=self._messages(instructions, content)
            )
            return str(resp.choices[0].message.content or "")
        except Exception as exc:  # noqa: BLE001 — normalize any SDK/transport error
            raise ProviderError(f"openai text call failed: {exc}") from exc

    async def structured(self, *, instructions: str, content: str, schema: type[M]) -> M:
        try:
            resp = await self._client.chat.completions.parse(
                model=self.model,
                messages=self._messages(instructions, content),
                response_format=schema,
            )
            parsed = resp.choices[0].message.parsed
            if parsed is None:
                raise ProviderError("openai returned no parsed structured output")
            return schema.model_validate(parsed.model_dump())
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"openai structured call failed: {exc}") from exc


__all__ = ["OpenAIProvider"]
