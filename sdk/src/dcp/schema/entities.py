"""Core DCP entities (SPEC §1, §4). The authoritative machine-readable contract.

Design provenance: ``protocol_design.md`` + owner decisions D1–D8 (SPEC §0.1). No design
element is borrowed from any reference protocol.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from .base import DCPModel, FrozenDCPModel
from .enums import EventType, InstanceStatus, ResponseRequirement, RoleKind, Visibility
from .values import (
    Budget,
    Flow,
    Gate,
    HumanPolicy,
    ModelBinding,
    NonEmptyStr,
    Orchestration,
    PendingInput,
    RoleBinding,
    RosterEntry,
    SemVer,
    TemplateRef,
    TerminationPolicy,
)

#: Open, typed extension map (SPEC §1.10). Explicit — never arbitrary extra top-level fields.
Metadata = dict[str, object]


class Role(DCPModel):
    """A dialogue-local identity defined by a template, filled by casting (SPEC §1.4)."""

    role_id: NonEmptyStr
    name: NonEmptyStr
    kind: RoleKind
    persona: str = ""
    response_requirement: ResponseRequirement = ResponseRequirement.OPTIONAL
    binding: RoleBinding = Field(default_factory=RoleBinding)
    human_policy: HumanPolicy | None = None


class Participant(DCPModel):
    """A server-level persistent identity, human or agent (SPEC §1.5; D4/D8)."""

    participant_id: NonEmptyStr
    kind: RoleKind
    display_name: NonEmptyStr
    profile: str = ""
    auth: str | None = None                     # credential reference (SPEC §1.6); not the secret
    discoverable: bool = False
    model_binding: ModelBinding | None = None   # agent-only (D8)
    metadata: Metadata = Field(default_factory=dict)

    @model_validator(mode="after")
    def _model_binding_agents_only(self) -> Participant:
        if self.kind is RoleKind.HUMAN and self.model_binding is not None:
            raise ValueError("model_binding is only valid on agent-kind participants (D8)")
        return self


class DialogueTemplate(DCPModel):
    """Reusable, registerable dialogue definition (SPEC §1.2/§4.1; D1). Immutable per version."""

    template_id: NonEmptyStr
    version: SemVer
    title: NonEmptyStr
    topic: str = ""
    goal: str = ""
    termination_policy: TerminationPolicy
    roles: list[Role] = Field(default_factory=list)
    flow: Flow | None = None
    orchestration: Orchestration = Field(default_factory=Orchestration)
    human_policy_defaults: HumanPolicy | None = None
    default_visibility: Visibility | None = None
    allow_open_mic: bool = False        # opt-in to observer interjections (SPEC §2.8, §6)
    metadata: Metadata = Field(default_factory=dict)


class Message(FrozenDCPModel):
    """A finalized, immutable contribution to the transcript (SPEC §1.8/§4.6)."""

    message_id: NonEmptyStr
    instance_id: NonEmptyStr
    turn_id: int
    role_id: NonEmptyStr
    participant_id: NonEmptyStr
    speaker_kind: RoleKind
    content: str
    created_at: datetime
    metadata: Metadata = Field(default_factory=dict)


class Event(FrozenDCPModel):
    """A protocol-level process record; substrate for restore/replay (SPEC §1.9/§4.6; D3)."""

    event_id: NonEmptyStr
    instance_id: NonEmptyStr
    type: EventType
    payload: Metadata = Field(default_factory=dict)
    created_at: datetime


class DialogueInstance(DCPModel):
    """A running occurrence created from a template, carrying all runtime state
    (SPEC §1.3/§4.2; D1). Authoritative state is replayable from ``messages`` + ``events`` (D3)."""

    instance_id: NonEmptyStr
    template_ref: TemplateRef
    owner: NonEmptyStr                          # participant_id (D5)
    visibility: Visibility = Visibility.PRIVATE
    dcp_version: SemVer
    status: InstanceStatus = InstanceStatus.CREATED
    turn: int = 0
    roster: list[RosterEntry] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    open_gates: list[Gate] = Field(default_factory=list)
    pending_inputs: list[PendingInput] = Field(default_factory=list)
    budget: Budget = Field(default_factory=Budget)
    metadata: Metadata = Field(default_factory=dict)


__all__ = [
    "Metadata",
    "Role",
    "Participant",
    "DialogueTemplate",
    "Message",
    "Event",
    "DialogueInstance",
]
