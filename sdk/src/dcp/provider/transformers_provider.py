"""In-process open-source models via HuggingFace ``transformers`` — Qwen3 by default.

Unlike ``LocalProvider`` (which talks to an OpenAI-compatible *server* such as vLLM/Ollama), this
loads and runs the model **inside the Python process** with ``transformers`` + ``torch`` — no
server, no API, no key. It fits open-weights models like **Qwen3**; the Qwen3 chat template's
*thinking* mode is supported (off by default for short, deterministic control/oversight outputs).

Heavy deps (``transformers``, ``torch``) are opt-in: ``pip install "dcp[transformers]"``. Select it
with ``DCP_MODEL_PROVIDER=transformers`` and ``DCP_MODEL=Qwen/Qwen3-4B`` (any HF causal-LM repo id).

Structured output is obtained by instructing the model to emit JSON for the requested schema and
validating it (open models have no native structured-output API), so a capable instruct model is
recommended for orchestrator/oversight decisions.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from ..errors import ProviderError

M = TypeVar("M", bound=BaseModel)

#: A small, widely-available Qwen3 instruct model — a sensible default.
DEFAULT_MODEL = "Qwen/Qwen3-4B"

_Messages = list[dict[str, str]]
_Generate = Callable[[_Messages], str]


def _first_json(text: str) -> Any:
    """Extract and parse the first JSON object from model output (tolerating prose / <think>)."""
    body = text.split("</think>", 1)[1] if "</think>" in text else text
    start = body.find("{")
    if start == -1:
        raise ProviderError("model output contained no JSON object")
    try:
        obj, _ = json.JSONDecoder().raw_decode(body[start:])
    except json.JSONDecodeError as exc:
        raise ProviderError(f"could not parse JSON from model output: {exc}") from exc
    return obj


class TransformersProvider:
    """A :class:`~dcp.provider.base.ModelProvider` that runs an open-weights HF model in-process."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        enable_thinking: bool = False,
        max_new_tokens: int = 512,
        generate: _Generate | None = None,
    ) -> None:
        self.model = model
        self._enable_thinking = enable_thinking
        self._max_new_tokens = max_new_tokens
        self._generate_fn = generate            # injected for tests; else lazily built (real model)

    @staticmethod
    def _messages(instructions: str, content: str) -> _Messages:
        return [{"role": "system", "content": instructions},
                {"role": "user", "content": content}]

    def _generate(self, messages: _Messages) -> str:
        if self._generate_fn is None:
            self._generate_fn = self._build_generate()   # lazy: no torch import until first use
        return self._generate_fn(messages)

    def _build_generate(self) -> _Generate:
        try:
            import torch  # noqa: F401
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:  # pragma: no cover — exercised only without the extra installed
            raise ProviderError(
                "the transformers provider needs extra deps: pip install 'dcp[transformers]'"
            ) from exc
        tokenizer = AutoTokenizer.from_pretrained(self.model)
        model = AutoModelForCausalLM.from_pretrained(
            self.model, torch_dtype="auto", device_map="auto")
        enable_thinking, max_new = self._enable_thinking, self._max_new_tokens

        def _run(messages: _Messages) -> str:  # pragma: no cover — needs a real model
            try:
                prompt = tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True,
                    enable_thinking=enable_thinking)
            except TypeError:                          # template without a thinking switch
                prompt = tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True)
            inputs = tokenizer([prompt], return_tensors="pt").to(model.device)
            output = model.generate(**inputs, max_new_tokens=max_new)
            new_tokens = output[0][inputs.input_ids.shape[1]:]
            decoded: str = tokenizer.decode(new_tokens, skip_special_tokens=True)
            return decoded.split("</think>", 1)[-1].strip()

        return _run

    async def text(self, *, instructions: str, content: str) -> str:
        # model.generate is blocking → run off the event loop
        return await asyncio.to_thread(self._generate, self._messages(instructions, content))

    async def structured(self, *, instructions: str, content: str, schema: type[M]) -> M:
        schema_json = json.dumps(schema.model_json_schema())
        instr = (f"{instructions}\n\nReturn ONLY a JSON object (no prose, no markdown) matching "
                 f"this JSON Schema:\n{schema_json}")
        raw = await asyncio.to_thread(self._generate, self._messages(instr, content))
        try:
            return schema.model_validate(_first_json(raw))
        except ValidationError as exc:
            raise ProviderError(
                f"transformers structured output failed schema validation: {exc}") from exc


__all__ = ["TransformersProvider", "DEFAULT_MODEL"]
