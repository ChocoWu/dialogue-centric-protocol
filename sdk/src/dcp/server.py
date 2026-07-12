"""High-level facade (M8): assemble the DCP layers behind one small object.

``Server`` wires a :class:`~dcp.state.SqlStore`, a :class:`~dcp.registry.Registry`, and the model
providers so a user does not hand-assemble the state/participation/orchestration/registry layers.
It stays thin: catalog + hosting calls delegate to the Registry, and :meth:`Server.run` builds an
:class:`~dcp.orchestration.Orchestrator` for one instance (deriving each agent's provider from its
`model_binding`, else the orchestrator default) and runs — or resumes (D3) — it to a terminal state.
"""

from __future__ import annotations

from .authoring import TemplateGenerator
from .config import Config
from .errors import RegistryError
from .orchestration import ControlPolicy, HumanGateway, Orchestrator, OversightPolicy
from .provider import ModelProvider, build_provider, orchestrator_binding
from .registry import Authenticator, Registry
from .schema import (
    DialogueInstance,
    DialogueTemplate,
    Metadata,
    Participant,
    ServerInfo,
    TemplateRef,
    TerminationPolicy,
    Visibility,
)
from .state import SqlStore


class Server:
    """A single-node DCP host: catalogs, hosting ops, and a run/resume entry point."""

    def __init__(
        self,
        *,
        database_url: str | None = None,
        config: Config | None = None,
        authenticator: Authenticator | None = None,
        generator: TemplateGenerator | None = None,
    ) -> None:
        self.config = config or Config.from_env()
        self.store = SqlStore(database_url or self.config.database_url)
        self.registry = Registry(self.store, authenticator=authenticator, generator=generator)

    # --- catalog + hosting (delegate to the Registry) --------------------------------
    def register_template(self, template: DialogueTemplate) -> None:
        self.registry.register_template(template)

    def register_participant(self, participant: Participant) -> None:
        self.registry.register_participant(participant)

    def instantiate(
        self,
        template_ref: TemplateRef,
        *,
        owner: str,
        visibility: Visibility | None = None,
        instance_id: str | None = None,
        goal: str | None = None,
        brief: Metadata | None = None,
        termination: TerminationPolicy | None = None,
    ) -> DialogueInstance:
        return self.registry.instantiate(
            template_ref, owner=owner, visibility=visibility, instance_id=instance_id,
            goal=goal, brief=brief, termination=termination,
        )

    def server_info(self) -> ServerInfo:
        return self.registry.server_info()

    # --- run / resume ----------------------------------------------------------------
    async def run(
        self,
        instance_id: str,
        *,
        cast: dict[str, str],
        agent_providers: dict[str, ModelProvider] | None = None,
        orchestrator_provider: ModelProvider | None = None,
        oversight: OversightPolicy | None = None,
        human_gateway: HumanGateway | None = None,
        control_policy: ControlPolicy | None = None,
    ) -> DialogueInstance:
        """Run (or resume) ``instance_id`` to a terminal status (SPEC §2.6–§2.10, §2.9)."""
        inst = self.registry.restore(instance_id)
        template = self.registry.get_template(
            inst.template_ref.template_id, inst.template_ref.version
        )
        if template is None:
            raise RegistryError(f"template for instance {instance_id!r} is not registered")
        participants = {pid: self._require_participant(pid) for pid in set(cast.values())}
        provider = orchestrator_provider or build_provider(orchestrator_binding(self.config))
        orchestrator = Orchestrator(
            store=self.store,
            template=template,
            instance_id=instance_id,
            cast=cast,
            participants=participants,
            provider=provider,
            agent_providers=agent_providers,
            oversight=oversight,
            human_gateway=human_gateway,
            control_policy=control_policy,
        )
        return await orchestrator.run()

    # --- helpers ---------------------------------------------------------------------
    def _require_participant(self, participant_id: str) -> Participant:
        participant = self.registry.get_participant(participant_id)
        if participant is None:
            raise RegistryError(f"participant {participant_id!r} is not registered")
        return participant


__all__ = ["Server"]
