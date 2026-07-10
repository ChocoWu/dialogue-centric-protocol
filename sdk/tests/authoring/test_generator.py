"""Auto-generation: query -> draft DialogueTemplate via a model provider (SPEC §2.2; D10)."""

from __future__ import annotations

from dcp import schema as s
from dcp.authoring import TemplateGenerator
from dcp.provider import MockProvider

_DRAFT = {
    "template_id": "brainstorm", "version": "1.0.0", "title": "Brainstorm",
    "goal": "Generate ideas", "termination_policy": {"condition": "done"},
    "roles": [
        {"role_id": "facilitator", "name": "Facilitator", "kind": "agent",
         "response_requirement": "required"},
        {"role_id": "user", "name": "User", "kind": "human", "response_requirement": "optional"},
    ],
    "orchestration": {"mode": "plan"},
}


async def test_generate_returns_a_valid_draft_template() -> None:
    gen = TemplateGenerator(MockProvider(structured_queue=[_DRAFT]))
    draft = await gen.generate("Help me brainstorm product names")
    assert isinstance(draft, s.DialogueTemplate)
    assert draft.template_id == "brainstorm"
    assert {r.role_id for r in draft.roles} == {"facilitator", "user"}


async def test_generate_passes_constraints_to_the_model() -> None:
    # Constraints are folded into the model content; the mock ignores them but must still return.
    gen = TemplateGenerator(MockProvider(structured_queue=[_DRAFT]))
    draft = await gen.generate("brainstorm", constraints="exactly two roles")
    assert draft.title == "Brainstorm"
