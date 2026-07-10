"""M1 — value-object validation (SPEC §4; §1.10 extension rule)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dcp import schema as s


def test_model_binding_no_credential_field() -> None:
    b = s.ModelBinding(provider="openai", model="gpt-x")
    assert b.provider == "openai" and b.model == "gpt-x"
    # a credential must never be accepted as a field (D8): extra keys are forbidden
    with pytest.raises(ValidationError):
        s.ModelBinding.model_validate(
            {"provider": "openai", "model": "gpt-x", "api_key": "sk-secret"}
        )


def test_model_binding_requires_nonempty() -> None:
    with pytest.raises(ValidationError):
        s.ModelBinding(provider="", model="gpt-x")


def test_semver_pattern_enforced() -> None:
    ok = s.TemplateRef(template_id="t", version="1.2.3")
    assert ok.version == "1.2.3"
    with pytest.raises(ValidationError):
        s.TemplateRef(template_id="t", version="v1")            # not semver
    with pytest.raises(ValidationError):
        s.TemplateRef(template_id="t", version="1.2")           # incomplete


def test_extra_top_level_fields_rejected() -> None:
    # SPEC §1.10: unknown top-level fields MUST be rejected.
    with pytest.raises(ValidationError):
        s.TerminationPolicy.model_validate({"condition": "done", "unknown": 1})


def test_termination_policy_bounds() -> None:
    s.TerminationPolicy(condition="c", max_turns=1, token_budget=1000)
    with pytest.raises(ValidationError):
        s.TerminationPolicy(condition="c", max_turns=0)         # ge=1


def test_human_policy_defaults() -> None:
    hp = s.HumanPolicy()
    assert hp.on_timeout is s.OnTimeout.FINALIZE_PROVISIONAL
    assert hp.wait_window_seconds is None
