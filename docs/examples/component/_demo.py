"""Shared demo harness: a tiny 2-agent dialogue driven by whatever ControlPolicy you hand it.

Both ``run_local.py`` and ``run_remote.py`` call :func:`run_with` — the *only* difference between
them is how the policy was obtained (materialized locally vs. connected remotely).
"""

from __future__ import annotations

from dcp import Server
from dcp import schema as s
from dcp.orchestration import ControlPolicy
from dcp.provider import MockProvider

TEMPLATE = s.DialogueTemplate(
    template_id="round-robin-demo",
    version="1.0.0",
    title="Round-robin demo",
    goal="Let each agent contribute once, in order.",
    termination_policy=s.TerminationPolicy(condition="both spoke", max_turns=6),
    roles=[
        s.Role(role_id="proposer", name="Proposer", kind=s.RoleKind.AGENT,
               persona="Proposes a product name.",
               response_requirement=s.ResponseRequirement.REQUIRED),
        s.Role(role_id="critic", name="Critic", kind=s.RoleKind.AGENT,
               persona="Reacts to the proposal.",
               response_requirement=s.ResponseRequirement.REQUIRED),
    ],
)


async def run_with(control_policy: ControlPolicy) -> s.DialogueInstance:
    """Register, instantiate, and run the demo dialogue under ``control_policy`` (key-free)."""
    server = Server(database_url="sqlite:///:memory:")
    server.register_template(TEMPLATE)
    for pid in ("proposer", "critic"):
        server.register_participant(
            s.Participant(participant_id=pid, kind=s.RoleKind.AGENT, display_name=pid.title()))
    server.instantiate(s.TemplateRef(template_id="round-robin-demo", version="1.0.0"),
                       owner="proposer", instance_id="demo")
    return await server.run(
        "demo",
        cast={"proposer": "proposer", "critic": "critic"},
        orchestrator_provider=MockProvider(),          # fallback only; the policy makes the decisions
        agent_providers={
            "proposer": MockProvider(texts=["I propose 'Northstar'."]),
            "critic": MockProvider(texts=["'Northstar' is clear and low-risk. +1."]),
        },
        control_policy=control_policy,                 # ← the component under test
    )
