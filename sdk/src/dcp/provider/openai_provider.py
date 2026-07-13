"""OpenAI-backed provider (D7). OpenAI Python SDK only; kept in its own module.

Uses ``chat.completions.create`` for text and the GA structured-outputs
``chat.completions.parse`` (verified present in openai>=2) for schema-validated output.
Client construction is lazy so importing this module needs no key/network; tests inject a stub.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from ..errors import ProviderError

M = TypeVar("M", bound=BaseModel)

#: Structured decoding is non-deterministic: a model may emit valid JSON followed by trailing prose
#: (which the strict parser rejects wholesale) or no parsed object at all. A single such hiccup must
#: not terminate a whole dialogue, so a structured call salvages the leading JSON object and,
#: failing that, retries a bounded number of times.
_STRUCTURED_ATTEMPTS = 4


def _is_strict_schema_error(exc: Exception) -> bool:
    """True if OpenAI rejected the schema for *strict* structured output.

    Strict mode requires every object to be closed (``additionalProperties: false``), which a schema
    with an open ``dict`` field (e.g. a model's ``metadata``) can never satisfy. Such a schema will
    fail every strict attempt, so the caller must switch to a non-strict request rather than retry.
    """
    msg = str(exc)
    return "response_format" in msg and ("Invalid schema" in msg or "additionalProperties" in msg)


def _salvage_first_json(exc: ValidationError, schema: type[M]) -> M | None:
    """Recover a schema instance from a parse that failed only on **trailing** characters.

    Some models emit a valid JSON object then extra prose/JSON; the strict parser rejects the whole
    string. The rejected raw text rides along on the ``ValidationError``, so decode just its leading
    JSON value (``raw_decode`` stops at the first complete one) and validate that. Returns ``None``
    if nothing salvageable is found — the caller then retries or fails.
    """
    for err in exc.errors():
        raw = err.get("input")
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            obj, _ = json.JSONDecoder().raw_decode(raw.strip())
            return schema.model_validate(obj)
        except (ValueError, ValidationError):
            continue
    return None


class OpenAIProvider:
    """A :class:`~dcp.provider.base.ModelProvider` backed by OpenAI chat completions."""

    def __init__(
        self, model: str, *, api_key: str | None = None, base_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model
        if client is not None:
            self._client: Any = client
        else:
            from openai import AsyncOpenAI  # lazy: no import cost / key check until used

            # api_key=None -> OPENAI_API_KEY env; base_url=None -> the OpenAI default endpoint
            self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

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
        messages = self._messages(instructions, content)
        last: Exception | None = None
        for _ in range(_STRUCTURED_ATTEMPTS):    # retry non-deterministic parse failures (bounded)
            try:
                resp = await self._client.chat.completions.parse(
                    model=self.model, messages=messages, response_format=schema,
                )
                parsed = resp.choices[0].message.parsed
                if parsed is None:
                    raise ProviderError("openai returned no parsed structured output")
                return schema.model_validate(parsed.model_dump())
            except ValidationError as exc:       # often just trailing chars — salvage the JSON
                salvaged = _salvage_first_json(exc, schema)
                if salvaged is not None:
                    return salvaged
                last = exc
            except Exception as exc:  # noqa: BLE001 — normalize + retry any SDK/parse error
                if _is_strict_schema_error(exc):     # schema can't be strict → non-strict, no retry
                    return await self._structured_non_strict(messages, schema)
                last = exc
        raise ProviderError(
            f"openai structured call failed after {_STRUCTURED_ATTEMPTS} attempts: {last}"
        ) from last

    async def _structured_non_strict(
        self, messages: list[dict[str, str]], schema: type[M]
    ) -> M:
        """Fallback for schemas OpenAI can't run in strict mode (open ``dict`` fields).

        Request a **non-strict** ``json_schema`` (which allows open objects), then decode the
        leading JSON object ourselves (tolerating trailing prose) and validate it against the model.
        """
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema(),
                            "strict": False},
        }
        try:
            resp = await self._client.chat.completions.create(
                model=self.model, messages=messages, response_format=response_format,
            )
            raw = str(resp.choices[0].message.content or "").strip()
            if not raw:
                raise ProviderError("openai returned empty structured content")
            obj, _ = json.JSONDecoder().raw_decode(raw)
            return schema.model_validate(obj)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"openai structured (non-strict) call failed: {exc}") from exc


__all__ = ["OpenAIProvider"]
