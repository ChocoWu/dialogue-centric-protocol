"""AgentDefinition — the D2 identity path: a shareable agent blueprint → a registered Participant.

DCP separates three levels (D2/D10): an **AgentDefinition** (shareable, no ``@id``: persona
defaults, capabilities, a bound provider) → a **Participant** (a server identity with an ``@id``) →
a **RosterEntry** (the per-instance relation of participant × role × tier). ``materialize`` /
``connect`` of a ``kind: agent`` component yield an :class:`AgentDefinition`; :meth:`to_participant`
performs the identity step.

An ``AgentDefinition`` also *acts as* a :class:`~dcp.provider.base.ModelProvider` (delegating to its
bound provider), so it drops straight into ``agent_providers`` — the provider is part of the
definition's capability, not per-dialogue runtime state.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from ..provider.base import ModelProvider
from ..schema import Participant, Role, RoleKind
from .manifest import AgentSpec, ComponentManifest, RoleDefaults

M = TypeVar("M", bound=BaseModel)


class AgentDefinition:
    """A shareable agent blueprint (D2); :meth:`to_participant` instantiates the identity."""

    def __init__(self, *, name: str, version: str, display_name: str, provider: ModelProvider,
                 profile: str = "", capabilities: tuple[str, ...] = (),
                 role_defaults: RoleDefaults | None = None) -> None:
        self.name = name                      # "namespace/name"
        self.version = version
        self.display_name = display_name
        self.profile = profile
        self.capabilities = capabilities
        self.role_defaults = role_defaults
        self.provider = provider
        self.model = getattr(provider, "model", name)     # ModelProvider.model

    # --- acts as a ModelProvider (delegates to the bound provider) ---------------------
    async def text(self, *, instructions: str, content: str) -> str:
        return await self.provider.text(instructions=instructions, content=content)

    async def structured(self, *, instructions: str, content: str, schema: type[M]) -> M:
        return await self.provider.structured(instructions=instructions, content=content,
                                              schema=schema)

    # --- the identity step (D2) --------------------------------------------------------
    def to_participant(self, participant_id: str, *, discoverable: bool = False) -> Participant:
        """Register this definition as a server ``Participant`` (assigns the ``@id``)."""
        return Participant(
            participant_id=participant_id, kind=RoleKind.AGENT, display_name=self.display_name,
            profile=self.profile, discoverable=discoverable,
            metadata={"component": self.name, "version": self.version,
                      "capabilities": list(self.capabilities)})

    def apply_role_defaults(self, role: Role) -> Role:
        """Materialize non-authoritative ``role_defaults`` into a ``Role`` before runtime (D8).

        Only fills a persona the role left empty — never overrides an existing ``Role.persona``.
        """
        if self.role_defaults is None or not self.role_defaults.persona or role.persona:
            return role
        return role.model_copy(update={"persona": self.role_defaults.persona})


def build_agent_definition(manifest: ComponentManifest, provider: ModelProvider) -> AgentDefinition:
    """Assemble an :class:`AgentDefinition` from an ``agent`` manifest + its bound provider."""
    c = manifest.component
    spec = manifest.spec
    return AgentDefinition(
        name=f"{c.namespace}/{c.name}", version=c.version, display_name=c.name,
        profile=manifest.metadata.description, capabilities=tuple(manifest.capabilities),
        role_defaults=spec.role_defaults if isinstance(spec, AgentSpec) else None,
        provider=provider)


__all__ = ["AgentDefinition", "build_agent_definition"]
