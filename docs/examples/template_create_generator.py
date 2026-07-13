#!/usr/bin/env python3
"""Auto-generate a DialogueTemplate from a plain-English query (SPEC §2.2, D10).

Generation needs a real model, so configure a provider + model id first. `load_dotenv()` reads a
`.env` from the CURRENT WORKING DIRECTORY, so run from a directory that has one (or export the vars):

    DCP_MODEL_PROVIDER=openai      # or anthropic / transformers
    DCP_MODEL=gpt-5.4              # the model id for that provider (required — never guessed)
    OPENAI_API_KEY=sk-...          # the provider's key (ANTHROPIC_API_KEY for anthropic)

Run:
    python docs/examples/template_create_generator.py
"""
from __future__ import annotations

import asyncio

from dcp import Config, TemplateGenerator, build_provider, load_dotenv
from dcp.provider import available_providers, orchestrator_binding


async def main() -> None:
    load_dotenv()                       # reads .env from the current working directory
    config = Config.from_env()

    # Fail with actionable guidance instead of a raw traceback if the model isn't configured.
    configured = {p.provider for p in available_providers() if p.configured}
    if config.model_provider != "mock" and not config.model:
        raise SystemExit(
            f"DCP_MODEL is not set for provider {config.model_provider!r} — generation needs a "
            "model id.\nSet it in a .env in this directory (or your shell):\n"
            "  DCP_MODEL_PROVIDER=openai\n  DCP_MODEL=gpt-5.4\n  OPENAI_API_KEY=sk-..."
        )
    if config.model_provider not in configured:
        raise SystemExit(
            f"provider {config.model_provider!r} is not configured (missing key/endpoint/extra). "
            f"Configured: {sorted(configured)}"
        )

    provider = build_provider(orchestrator_binding(config))
    gen = TemplateGenerator(provider)
    draft = await gen.generate("Make a short brainstorming template for product names.")

    # `draft` is an UNREGISTERED DialogueTemplate — review/edit, then register + instantiate.
    print("Generated draft template (unregistered):")
    print(draft.model_dump(mode="json"))


if __name__ == "__main__":
    asyncio.run(main())
