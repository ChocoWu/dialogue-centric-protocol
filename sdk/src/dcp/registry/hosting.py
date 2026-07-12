"""Registry & Hosting layer (SPEC §3.4; D2/D4/D5/D6).

One **Registry** surface over two catalogs — templates and participants — plus the hosting ops
that create and admit into instances: ``instantiate``, ``grant_access``, ``join``, ``leave``,
``restore``. All state changes are appended to the authoritative log; the returned instance is a
full replay (D3), so ``join`` inherently replays the full history to the joiner (SPEC §2.5/§2.9).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from ..authoring import TemplateGenerator
from ..errors import AccessError, RegistryError
from ..participation.tiers import tier_allows
from ..plugins import available_plugins
from ..provider import available_providers
from ..schema import (
    AccessGrant,
    AccessTier,
    Capabilities,
    DialogueInstance,
    DialogueTemplate,
    Event,
    EventType,
    Metadata,
    Participant,
    ServerInfo,
    TemplateRef,
    TerminationPolicy,
    Visibility,
)
from ..state import InstanceHeader, Store, restore
from .auth import AnonymousAuthenticator, Authenticator

_DCP_VERSION = "0.2.0"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Registry:
    """Server-level host for templates, participants, and dialogue instances (SPEC §3.4)."""

    def __init__(
        self,
        store: Store,
        *,
        authenticator: Authenticator | None = None,
        dcp_version: str = _DCP_VERSION,
        generator: TemplateGenerator | None = None,
        capabilities: Capabilities | None = None,
    ) -> None:
        self._store = store
        self._auth = authenticator or AnonymousAuthenticator()
        self._dcp_version = dcp_version
        self._generator = generator
        # `auto_generate` reflects whether a generator is actually wired (SPEC §1.11/§2.2).
        self._capabilities = capabilities or Capabilities(auto_generate=generator is not None)

    # --- auth (D6) -------------------------------------------------------------------
    def authenticate(self, token: str | None) -> str:
        """Resolve a bearer token to a ``participant_id`` via the configured Authenticator."""
        return self._auth.authenticate(token)

    # --- server introspection (SPEC §1.11; D9) ---------------------------------------
    def server_info(self, env: Mapping[str, str] | None = None) -> ServerInfo:
        """Advertise version, capabilities, providers, installed plugins (no keys; SPEC §1.11)."""
        return ServerInfo(
            dcp_version=self._dcp_version,
            capabilities=self._capabilities,
            model_providers=available_providers(env),
            plugins=available_plugins(),
        )

    # --- template catalog (SPEC §2.1) ------------------------------------------------
    def register_template(self, template: DialogueTemplate) -> None:
        """Register a template; immutable per ``(id, version)`` (raises on changed re-register)."""
        self._store.register_template(template)

    def get_template(self, template_id: str, version: str) -> DialogueTemplate | None:
        return self._store.get_template(template_id, version)

    def list_templates(self) -> list[DialogueTemplate]:
        return self._store.list_templates()

    async def generate_template(
        self, query: str, *, constraints: str | None = None
    ) -> DialogueTemplate:
        """Auto-generate a **draft** template (SPEC §2.2; D10). Capability error if not enabled."""
        if self._generator is None:
            raise RegistryError(
                "server capability 'auto_generate' is not enabled (no generator configured)"
            )
        return await self._generator.generate(query, constraints=constraints)

    # --- participant catalog (D4) ----------------------------------------------------
    def register_participant(self, participant: Participant) -> None:
        self._store.register_participant(participant)

    def get_participant(self, participant_id: str) -> Participant | None:
        return self._store.get_participant(participant_id)

    def list_participants(self, *, discoverable_only: bool = False) -> list[Participant]:
        return self._store.list_participants(discoverable_only=discoverable_only)

    # --- hosting ---------------------------------------------------------------------
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
        """Create an instance in ``created`` owned by ``owner`` (SPEC §2.3, D5).

        ``goal`` overrides the template's (generic) goal with this run's concrete objective; the
        effective goal is ``instance.goal or template.goal``. ``termination`` likewise overrides the
        template's termination policy for this run (effective = ``instance.termination_policy or
        template.termination_policy``). ``brief`` is the concrete, per-run task input — what *this*
        occurrence is about (vs. the template, which defines the *kind* of dialogue). All are
        recorded in the instance-created event so they replay, and are surfaced at run time.
        """
        template = self._store.get_template(template_ref.template_id, template_ref.version)
        if template is None:
            raise RegistryError(
                f"unknown template {template_ref.template_id!r}@{template_ref.version}"
            )
        iid = instance_id or _new_id("dlg")
        vis = visibility or template.default_visibility or Visibility.PRIVATE
        now = datetime.now(UTC)
        self._store.create_instance(
            InstanceHeader(
                instance_id=iid, template_ref=template_ref, owner=owner,
                visibility=vis, dcp_version=self._dcp_version, created_at=now,
            )
        )
        created_payload: dict[str, object] = {"owner": owner}
        if goal:
            created_payload["goal"] = goal
        if brief:
            created_payload["brief"] = dict(brief)
        if termination is not None:
            created_payload["termination_policy"] = termination.model_dump(mode="json")
        self._emit(iid, EventType.INSTANCE_CREATED, **created_payload)
        # The owner holds the `own` tier and is seated on the roster from the start (D5).
        self._store.add_grant(AccessGrant(
            instance_id=iid, participant_id=owner, tier=AccessTier.OWN,
            granted_by=owner, granted_at=now,
        ))
        self._emit(iid, EventType.PARTICIPANT_JOINED, participant_id=owner,
                   tier=AccessTier.OWN.value)
        return restore(self._store, iid)

    def grant_access(
        self, instance_id: str, *, grantor: str, participant_id: str, tier: AccessTier
    ) -> None:
        """Admit/authorize ``participant_id`` at ``tier``; only an ``own`` holder may grant (D5)."""
        inst = restore(self._store, instance_id)
        if not self._holds(inst, grantor, AccessTier.OWN):
            raise AccessError(f"{grantor!r} lacks the 'own' tier required to grant access")
        self._store.add_grant(AccessGrant(
            instance_id=instance_id, participant_id=participant_id, tier=tier,
            granted_by=grantor, granted_at=datetime.now(UTC),
        ))
        if any(r.participant_id == participant_id for r in inst.roster):
            self._emit(instance_id, EventType.TIER_CHANGED,
                       participant_id=participant_id, tier=tier.value)

    def join(self, instance_id: str, *, participant_id: str) -> DialogueInstance:
        """Join subject to visibility + grant (SPEC §2.5); returns full replay for the joiner."""
        header = self._store.get_header(instance_id)
        if header is None:
            raise RegistryError(f"unknown instance {instance_id!r}")
        grant = self._store.get_grant(instance_id, participant_id)
        if header.visibility is Visibility.PUBLIC:
            tier = grant.tier if grant is not None else AccessTier.OBSERVE   # auto-observe
        else:                                                                # unlisted / private
            if grant is None:
                raise AccessError(
                    f"join to a {header.visibility.value} instance requires a grant"
                )
            tier = grant.tier
        self._emit(instance_id, EventType.PARTICIPANT_JOINED,
                   participant_id=participant_id, tier=tier.value)
        return restore(self._store, instance_id)                             # replay-to-joiner (D3)

    def leave(self, instance_id: str, *, participant_id: str) -> None:
        self._emit(instance_id, EventType.PARTICIPANT_LEFT, participant_id=participant_id)

    def get_instance(self, instance_id: str) -> DialogueInstance:
        """Full replay of one instance (alias of ``restore``, for the read/discovery surface)."""
        return restore(self._store, instance_id)

    def list_instances(self, *, caller: str | None = None) -> list[DialogueInstance]:
        """List instances the ``caller`` may see (SPEC §3.4): non-private, or owned/granted."""
        out: list[DialogueInstance] = []
        for iid in self._store.list_instances():
            inst = restore(self._store, iid)
            if inst.visibility is not Visibility.PRIVATE:
                out.append(inst)
            elif caller is not None and (
                inst.owner == caller or self._store.get_grant(iid, caller) is not None
            ):
                out.append(inst)
        return out

    def restore(self, instance_id: str) -> DialogueInstance:
        """Full-replay restore (D3/TBD-28) — the same path for rehydrate and joiner catch-up."""
        return restore(self._store, instance_id)

    # --- helpers ---------------------------------------------------------------------
    def _holds(self, inst: DialogueInstance, participant_id: str, tier: AccessTier) -> bool:
        for row in inst.roster:
            if row.participant_id == participant_id:
                return tier_allows(row.tier, tier)
        return False

    def _emit(self, instance_id: str, event_type: EventType, **payload: object) -> None:
        self._store.append(
            instance_id,
            Event(
                event_id=_new_id("evt"), instance_id=instance_id, type=event_type,
                payload=payload, created_at=datetime.now(UTC),
            ),
        )


__all__ = ["Registry"]
