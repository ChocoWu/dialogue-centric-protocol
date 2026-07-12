"""Example DCP plugins — one of each kind, wired up via entry points in ``pyproject.toml``.

Install it (``pip install -e examples/plugin-example``) and DCP discovers these by name:

    >>> import dcp
    >>> dcp.available_plugins()
    {'dcp.control_policies': ['round_robin'], 'dcp.oversight_policies': ['no_shouting'],
     'dcp.templates': ['two_agent_debate'], 'dcp.providers': ['echo']}
    >>> Policy = dcp.load_plugin('dcp.control_policies', 'round_robin')
    >>> template = dcp.plugins.load_template('two_agent_debate')

Each component is a plain object implementing a DCP interface — nothing here is DCP-internal.
"""

from __future__ import annotations

from dcp.errors import ProviderError
from dcp.orchestration import (
    CheckOutcome,
    DialogueContext,
    OrchestratorAction,
    RubricOversight,
)
from dcp.schema import (
    Assessment,
    DialogueTemplate,
    Message,
    OrchestrationMode,
    Orchestration,
    ResponseRequirement,
    Role,
    RoleKind,
    TerminationPolicy,
    TerminationStatus,
)


class RoundRobinPolicy:
    """A custom orchestrator (ControlPolicy): each role speaks once, in template order, then stop.

    It uses no model at all — the decision is a pure function of the read-only DialogueContext.
    """

    async def decide(self, ctx: DialogueContext) -> OrchestratorAction:
        spoken = {m.role_id for m in ctx.messages}
        for role in ctx.roles:
            if role.role_id not in spoken:
                return OrchestratorAction(action="select_speaker", target_role_id=role.role_id)
        return OrchestratorAction(action="stop", status=TerminationStatus.DONE, reason="all spoke")


async def _no_shouting(*, role: Role, message: Message, transcript: str) -> Assessment | CheckOutcome:
    """A one-function rubric check: flag ALL-CAPS shouting so the orchestrator asks for a revision."""
    content = message.content
    if len(content) > 3 and content.isupper():
        return CheckOutcome(Assessment.WEAK, "please don't shout")
    return Assessment.OK


class NoShoutingOversight(RubricOversight):
    """A custom oversight policy built from one check (see RubricOversight, 6.1c)."""

    def __init__(self) -> None:
        super().__init__(safety=_no_shouting)


def two_agent_debate() -> DialogueTemplate:
    """A shareable template: an optimist vs. a skeptic, emergent (plan) orchestration."""
    return DialogueTemplate(
        template_id="two-agent-debate",
        version="1.0.0",
        title="Two-agent debate",
        goal="Explore both sides of a question and surface the strongest points.",
        termination_policy=TerminationPolicy(condition="both sides heard", max_turns=6),
        orchestration=Orchestration(mode=OrchestrationMode.PLAN),
        roles=[
            Role(role_id="optimist", name="Optimist", kind=RoleKind.AGENT,
                 persona="Argue for the proposal; surface upside and opportunity.",
                 response_requirement=ResponseRequirement.REQUIRED),
            Role(role_id="skeptic", name="Skeptic", kind=RoleKind.AGENT,
                 persona="Argue against; surface risks and failure modes.",
                 response_requirement=ResponseRequirement.REQUIRED),
        ],
    )


class EchoProvider:
    """A shareable agent (ModelProvider) — resolved by name via the ``dcp.providers`` entry point.

    A packaged agent is just a ``ModelProvider``: async ``text`` (agent contributions) and
    ``structured`` (decisions/oversight). This demo is text-only — a legitimate shape for an agent
    that only ever *speaks*, never orchestrates — so ``structured`` refuses rather than pretends.
    Once installed, ``ModelBinding(provider="echo", model=...)`` builds it (``build_provider``).
    """

    def __init__(self, model: str = "echo") -> None:
        self.model = model

    async def text(self, *, instructions: str, content: str) -> str:
        last = content.strip().splitlines()[-1] if content.strip() else "hello"
        return f"[{self.model}] {last}"

    async def structured(self, *, instructions: str, content: str, schema: type) -> object:
        raise ProviderError("EchoProvider is text-only; use it for agent turns, not decisions")


__all__ = ["RoundRobinPolicy", "NoShoutingOversight", "two_agent_debate", "EchoProvider"]
