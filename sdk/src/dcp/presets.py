"""Ready-to-use dialogue templates (Phase 6.2a) — start from a working template, not a blank page.

Each preset is a **factory** returning a fresh, valid :class:`~dcp.schema.DialogueTemplate` you can
register as-is or adapt (change roles, personas, termination, orchestration mode). Use
:func:`list_presets` to enumerate and :func:`get_preset` to fetch one by name.

    from dcp import presets
    template = presets.get_preset("design_review")     # or presets.design_review()
"""

from __future__ import annotations

from collections.abc import Callable

from .errors import RegistryError
from .schema import (
    DialogueTemplate,
    Edge,
    Flow,
    HumanPolicy,
    OnTimeout,
    Orchestration,
    OrchestrationMode,
    ResponseRequirement,
    Role,
    RoleKind,
    TerminationPolicy,
)


def _flow(entry: str, *edges: tuple[str, str]) -> Flow:
    """Build a (possibly non-linear) flow graph (SPEC §2.6)."""
    return Flow(entry=entry, edges=[Edge(from_role=a, to_role=b) for a, b in edges])

_DEFAULT_HUMAN_POLICY = HumanPolicy(
    wait_window_seconds=120, on_timeout=OnTimeout.FINALIZE_PROVISIONAL)


def _agent(role_id: str, name: str, persona: str) -> Role:
    return Role(role_id=role_id, name=name, kind=RoleKind.AGENT, persona=persona,
                response_requirement=ResponseRequirement.REQUIRED)


def _human(role_id: str, name: str, persona: str,
           requirement: ResponseRequirement = ResponseRequirement.GATE) -> Role:
    return Role(role_id=role_id, name=name, kind=RoleKind.HUMAN, persona=persona,
                response_requirement=requirement)


def design_review() -> DialogueTemplate:
    """Two agents propose + critique a design; a human owner approves (gate)."""
    return DialogueTemplate(
        template_id="design-review", version="1.0.0", title="Design review",
        topic="design decision",
        goal="Converge on a design decision the owner approves, with risks noted.",
        termination_policy=TerminationPolicy(condition="owner approves", max_turns=12),
        orchestration=Orchestration(mode=OrchestrationMode.FLOW),
        # iterate proposer⇄critic, then critic may advance to the owner (branch)
        flow=_flow("proposer", ("proposer", "critic"), ("critic", "proposer"), ("critic", "owner")),
        human_policy_defaults=_DEFAULT_HUMAN_POLICY,
        roles=[
            _agent("proposer", "Proposer", "Propose a concrete design with rationale."),
            _agent("critic", "Critic", "Find weaknesses, risks, and missing assumptions."),
            _human("owner", "Owner", "Approve, reject, or request changes to the design."),
        ],
    )


def debate() -> DialogueTemplate:
    """An optimist vs. a skeptic; a human judge decides (gate)."""
    return DialogueTemplate(
        template_id="debate", version="1.0.0", title="Structured debate",
        topic="a contested question",
        goal="Surface the strongest case on each side, then reach a judged conclusion.",
        termination_policy=TerminationPolicy(condition="judge decides", max_turns=12),
        orchestration=Orchestration(mode=OrchestrationMode.FLOW),
        # optimist⇄skeptic exchange, then the skeptic's turn may hand to the judge (branch)
        flow=_flow("optimist", ("optimist", "skeptic"), ("skeptic", "optimist"),
                   ("skeptic", "judge")),
        human_policy_defaults=_DEFAULT_HUMAN_POLICY,
        roles=[
            _agent("optimist", "Optimist", "Argue for the proposal; surface upside."),
            _agent("skeptic", "Skeptic", "Argue against; surface risks and failure modes."),
            _human("judge", "Judge", "Weigh both sides and decide."),
        ],
    )


def brainstorm() -> DialogueTemplate:
    """A facilitator plus idea generators; the user may chime in (open mic)."""
    return DialogueTemplate(
        template_id="brainstorm", version="1.0.0", title="Brainstorm",
        topic="idea generation",
        goal="Generate a diverse set of ideas and shortlist the most promising.",
        termination_policy=TerminationPolicy(condition="shortlist produced", max_turns=15),
        orchestration=Orchestration(mode=OrchestrationMode.PLAN),
        allow_open_mic=True,
        human_policy_defaults=_DEFAULT_HUMAN_POLICY,
        roles=[
            _agent("facilitator", "Facilitator", "Frame prompts; keep ideas flowing and diverse."),
            _agent("divergent", "Divergent Thinker", "Produce bold, unconventional ideas."),
            _agent("pragmatist", "Pragmatist", "Ground ideas in feasibility and shortlist."),
            _human("user", "User", "Steer or add ideas.", ResponseRequirement.OPTIONAL),
        ],
    )


def red_team_review() -> DialogueTemplate:
    """An author's plan is stress-tested by a red-teamer + safety reviewer; a human signs off."""
    return DialogueTemplate(
        template_id="red-team-review", version="1.0.0", title="Red-team review",
        topic="risk review",
        goal="Stress-test a plan for failure modes and safety issues before sign-off.",
        termination_policy=TerminationPolicy(condition="reviewer signs off", max_turns=14),
        orchestration=Orchestration(mode=OrchestrationMode.FLOW),
        # author → red_teamer → safety; safety loops back to the author or advances to the approver
        flow=_flow("author", ("author", "red_teamer"), ("red_teamer", "safety"),
                   ("safety", "author"), ("safety", "approver")),
        human_policy_defaults=_DEFAULT_HUMAN_POLICY,
        roles=[
            _agent("author", "Author", "Present and defend the plan."),
            _agent("red_teamer", "Red Teamer", "Adversarially attack the plan; find how it breaks"),
            _agent("safety", "Safety Reviewer", "Assess safety, misuse, and compliance risks."),
            _human("approver", "Approver", "Sign off or block, given the review."),
        ],
    )


def research_companion() -> DialogueTemplate:
    """A student's research companion: scout + methodologist + writing coach, advisor signs off."""
    return DialogueTemplate(
        template_id="research-companion", version="1.0.0", title="Student research companion",
        topic="research guidance",
        goal="Help the student advance a research question into a grounded, well-argued direction.",
        termination_policy=TerminationPolicy(
            condition="advisor approves direction", max_turns=100),
        orchestration=Orchestration(mode=OrchestrationMode.FLOW),
        # scout → methodologist → coach → advisor, with loops back for more lit or another revision
        flow=_flow("scout", ("scout", "methodologist"), ("methodologist", "coach"),
                   ("methodologist", "scout"), ("coach", "advisor"), ("coach", "methodologist")),
        human_policy_defaults=_DEFAULT_HUMAN_POLICY,
        roles=[
            _agent("scout", "Literature Scout",
                   "Find and summarize relevant related work; cite sources."),
            _agent("methodologist", "Methodologist",
                   "Critique rigor, design, and threats to validity."),
            _agent("coach", "Writing Coach", "Sharpen the framing, clarity, and argument."),
            _human("advisor", "Advisor", "Approve or redirect the research direction."),
            _human("student", "Student", "Provide the question and react to guidance.",
                   ResponseRequirement.OPTIONAL),
        ],
    )


#: All built-in presets, by name.
PRESETS: dict[str, Callable[[], DialogueTemplate]] = {
    "design_review": design_review,
    "debate": debate,
    "brainstorm": brainstorm,
    "red_team_review": red_team_review,
    "research_companion": research_companion,
}


def list_presets() -> list[str]:
    """Names of the built-in presets, sorted."""
    return sorted(PRESETS)


def get_preset(name: str) -> DialogueTemplate:
    """Return a fresh template for preset ``name`` (raises ``RegistryError`` if unknown)."""
    factory = PRESETS.get(name)
    if factory is None:
        raise RegistryError(f"unknown preset {name!r}; available: {list_presets()}")
    return factory()


__all__ = [
    "PRESETS",
    "list_presets",
    "get_preset",
    "design_review",
    "debate",
    "brainstorm",
    "red_team_review",
    "research_companion",
]
