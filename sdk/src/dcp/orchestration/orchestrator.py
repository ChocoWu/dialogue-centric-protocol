"""The orchestration loop (SPEC §1.7, §2.6–§2.10; D3, TBD-25).

Drives a **serialized transcript**: at most one contribution per turn. Agents contribute via their
model provider; humans via a gateway (with timeout → provisional). Every step appends to the store's
append-only log; the returned instance is a full replay (D3). Provider decisions are structured
(plan mode) or follow the template ``flow`` (flow mode); oversight is pluggable.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime

from ..errors import OrchestrationError
from ..provider import ModelProvider, build_provider
from ..schema import (
    TERMINAL_STATUSES,
    DialogueInstance,
    DialogueTemplate,
    Event,
    EventType,
    Message,
    Metadata,
    OnTimeout,
    OrchestrationMode,
    Participant,
    PostOutcome,
    Readiness,
    RecommendedAction,
    ResponseRequirement,
    Role,
    RoleKind,
    TerminationStatus,
)
from ..state import Store, restore
from .actions import OrchestratorAction
from .context import DialogueContext
from .human import HumanGateway
from .oversight import DefaultOversight, OversightPolicy
from .policy import ControlPolicy, FlowPolicy, PlanPolicy, RecordsContextProjection


class Orchestrator:
    """Runs one dialogue instance to a terminal status, appending events/messages to ``store``."""

    def __init__(
        self,
        *,
        store: Store,
        template: DialogueTemplate,
        instance_id: str,
        cast: dict[str, str],                       # role_id -> participant_id
        participants: dict[str, Participant],       # participant_id -> Participant
        provider: ModelProvider,                    # orchestrator's model (decisions/oversight)
        agent_providers: dict[str, ModelProvider] | None = None,
        oversight: OversightPolicy | None = None,
        human_gateway: HumanGateway | None = None,
        control_policy: ControlPolicy | None = None,
        max_recovery_attempts: int = 3,
        max_revisions: int = 2,
    ) -> None:
        self.store = store
        self.template = template
        self.instance_id = instance_id
        self.cast = cast
        self.participants = participants
        self.provider = provider
        self.agent_providers = agent_providers or {}
        self.oversight = oversight or DefaultOversight()
        self.human_gateway = human_gateway
        # The "brain" (6.1b): default preserves prior behavior — FlowPolicy in flow mode, else Plan.
        self.control_policy = control_policy or (
            FlowPolicy() if template.orchestration.mode is OrchestrationMode.FLOW else PlanPolicy()
        )
        self._max_recovery = max_recovery_attempts       # bound on pre-action recovery/turn (D11)
        self._max_revisions = max_revisions              # bound on post-action revisions (D11)
        self._roles = {r.role_id: r for r in template.roles}
        self._max_turns = template.termination_policy.max_turns
        self._events = itertools.count()
        self._msg_seq = itertools.count()                # unique message ids (survive revisions)
        self._aux_seq = itertools.count()                # unique ids for pending-input/gate aux
        self._messages: list[Message] = []
        self._turn = 0
        self._steps = 0                                  # control steps (guards recovery loops)
        self._last_speaker: str | None = None

    # --- helpers ---------------------------------------------------------------------
    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _emit(self, event_type: EventType, **payload: object) -> None:
        self.store.append(
            self.instance_id,
            Event(
                event_id=f"evt_{next(self._events)}",
                instance_id=self.instance_id,
                type=event_type,
                payload=payload,
                created_at=self._now(),
            ),
        )

    def _transcript(self) -> str:
        return "\n".join(f"{m.role_id}: {m.content}" for m in self._messages)

    def _provider_for(self, participant: Participant) -> ModelProvider:
        if participant.participant_id in self.agent_providers:
            return self.agent_providers[participant.participant_id]
        if participant.model_binding is not None:      # per-agent binding (D8)
            prov = build_provider(participant.model_binding)
            self.agent_providers[participant.participant_id] = prov
            return prov
        return self.provider                            # inherit orchestrator default

    def _record_message(
        self, role: Role, participant_id: str, content: str, metadata: Metadata | None = None
    ) -> None:
        msg = Message(
            message_id=f"msg_{next(self._msg_seq)}",
            instance_id=self.instance_id,
            turn_id=self._turn,
            role_id=role.role_id,
            participant_id=participant_id,
            speaker_kind=role.kind,
            content=content,
            created_at=self._now(),
            metadata=metadata or {},
        )
        self.store.append(self.instance_id, msg)
        self._messages.append(msg)
        self._emit(EventType.CONTRIBUTION_RECORDED, message_id=msg.message_id, role_id=role.role_id)

    def _terminate(self, status: TerminationStatus, reason: str) -> None:
        self._emit(EventType.INSTANCE_TERMINATED, status=status.value, reason=reason)

    # --- open mic (SPEC §2.8) --------------------------------------------------------
    def submit_open_mic(self, input_id: str, content: str, from_participant: str) -> None:
        """Queue an unseated observer's interjection; stays pending until addressed (SPEC §2.8).

        Rejected unless the template opts in via ``allow_open_mic`` (§6).
        """
        if not self.template.allow_open_mic:
            raise OrchestrationError("open-mic is not enabled for this template (allow_open_mic)")
        self._emit(
            EventType.HUMAN_INPUT_PENDING,
            input_id=input_id, kind="open_mic", content=content, from_participant=from_participant,
        )

    def address_open_mic(self, input_id: str, addressed_by: str) -> None:
        self._emit(EventType.HUMAN_INPUT_ADDRESSED, input_id=input_id, addressed_by=addressed_by)

    # --- decisions -------------------------------------------------------------------
    async def _decide(self) -> OrchestratorAction:
        """Ask the control policy for the next action, over a read-only log-derived context."""
        ctx = DialogueContext.from_instance(
            restore(self.store, self.instance_id), self.template, self.provider
        )
        action = await self.control_policy.decide(ctx)
        self._record_projection_audits()
        return action

    def _record_projection_audits(self) -> None:
        """If the policy transmitted context off-box (a remote proxy), log what it sent (D12)."""
        policy = self.control_policy
        if isinstance(policy, RecordsContextProjection):
            for audit in policy.drain_projection_audits():
                self._emit(EventType.CONTEXT_PROJECTED, **dict(audit))

    # --- contribution ----------------------------------------------------------------
    async def _contribute(self, role: Role) -> tuple[TerminationStatus, str] | None:
        """Perform ``role``'s turn. Returns a terminal signal (e.g. gate timeout) or ``None``."""
        participant = self.participants[self.cast[role.role_id]]
        if role.kind is RoleKind.AGENT:
            provider = self._provider_for(participant)
            content = await provider.text(
                instructions=role.persona or role.name, content=self._transcript()
            )
            self._record_message(role, participant.participant_id, content)
            return None

        # human role
        if self.human_gateway is None:
            raise OrchestrationError(f"human role {role.role_id!r} requires a human_gateway")
        policy = role.human_policy or self.template.human_policy_defaults
        req = role.response_requirement

        if req is ResponseRequirement.OPTIONAL:
            reply = await self.human_gateway.request(role=role, policy=policy, blocking=False)
            if reply.content is not None:
                self._record_message(
                    role, participant.participant_id, reply.content, {"mode": "optional"}
                )
            return None

        gate_id = None
        if req is ResponseRequirement.GATE:
            gate_id = f"gate_{self._turn}"
            self._emit(EventType.GATE_OPENED, gate_id=gate_id, role_id=role.role_id)
        reply = await self.human_gateway.request(role=role, policy=policy, blocking=True)
        if reply.content is None:                       # timeout
            on_timeout = policy.on_timeout if policy is not None else OnTimeout.FINALIZE_PROVISIONAL
            if on_timeout is OnTimeout.FINALIZE_PROVISIONAL:
                return (TerminationStatus.PROVISIONAL, f"role {role.role_id!r} timed out")
            if gate_id is not None:
                self._emit(EventType.GATE_RESOLVED, gate_id=gate_id)
            return None
        self._record_message(
            role, participant.participant_id, reply.content,
            {"mode": req.value, "decision": reply.decision},
        )
        if gate_id is not None:
            self._emit(EventType.GATE_RESOLVED, gate_id=gate_id)
        return None

    # --- resume/bootstrap (SPEC §2.9; D3) --------------------------------------------
    def _hydrate(self, inst: DialogueInstance) -> None:
        """Seed in-memory run state from a restored instance so ``run`` can resume (D3)."""
        self._turn = inst.turn
        self._messages = list(inst.messages)
        self._last_speaker = inst.messages[-1].role_id if inst.messages else None
        self._events = itertools.count(len(inst.events))   # continue event ids past the log
        self._msg_seq = itertools.count(len(inst.messages))
        self._aux_seq = itertools.count(len(inst.events))

    def _bootstrap(self, inst: DialogueInstance) -> None:
        """Emit only the start/cast/join events not already in the log (idempotent resume)."""
        seen = {e.type for e in inst.events}
        if EventType.INSTANCE_STARTED not in seen:
            self._emit(EventType.INSTANCE_STARTED)
        if EventType.ROLES_CAST not in seen:
            self._emit(
                EventType.ROLES_CAST,
                roles=[{"role_id": rid, "participant_id": pid} for rid, pid in self.cast.items()],
            )
        seated = {r.participant_id for r in inst.roster}
        for pid in self.cast.values():
            if pid not in seated:
                self._emit(EventType.PARTICIPANT_JOINED, participant_id=pid, tier="speak")

    # --- control actions (SPEC §1.7; D11) --------------------------------------------
    def _resolve_role(self, role_id: str | None) -> Role:
        role = self._roles.get(role_id or "")
        if role is None:
            raise OrchestrationError(f"select_speaker for unknown role {role_id!r}")
        return role

    def _inject_context(self, role: Role, issues_text: str) -> None:
        """Recovery: add the missing context the pre-check flagged, then the candidate retries."""
        self._emit(
            EventType.CONTEXT_INJECTED, target_role_id=role.role_id,
            content=issues_text or "context injected", reason="pre-action recovery",
        )

    def _pick_verifier(self, speaker: Role) -> Role | None:
        """A verifier role for output verification: another cast agent role, if any."""
        for role in self.template.roles:
            if role.role_id != speaker.role_id and role.kind is RoleKind.AGENT \
                    and role.role_id in self.cast:
                return role
        return None

    def _human_role(self) -> Role | None:
        """A human role in the cast — the participant solicited for recovery input."""
        for role in self.template.roles:
            if role.kind is RoleKind.HUMAN and role.role_id in self.cast:
                return role
        return None

    async def _solicit_human(self, candidate: Role, reason: str) -> bool:
        """Recovery: ask a human for the missing input and inject it as context (SPEC §1.7).

        Returns True iff input arrived (candidate can retry); False if there is no gateway or the
        request timed out — in which case the pending request stays open for a later addresser.
        """
        if self.human_gateway is None:
            return False
        ask = self._human_role() or candidate
        policy = ask.human_policy or self.template.human_policy_defaults
        input_id = f"hi_{next(self._aux_seq)}"
        self._emit(EventType.HUMAN_INPUT_PENDING, input_id=input_id, kind="request_human",
                   role_id=candidate.role_id, reason=reason)
        reply = await self.human_gateway.request(role=ask, policy=policy, blocking=True)
        if reply.content is None:                        # timeout → leave pending
            return False
        self._emit(EventType.HUMAN_INPUT_ADDRESSED, input_id=input_id, addressed_by=ask.role_id)
        self._inject_context(candidate, reply.content)   # the human's input becomes context
        return True

    async def _wait_open_gate(self) -> bool:
        """Recovery: block until the instance's open gate(s) resolve (SPEC §1.7 ``wait_gate``).

        Returns True iff at least one open gate was resolved (candidate can retry); False if there
        is nothing to wait on or no gateway.
        """
        if self.human_gateway is None:
            return False
        inst = restore(self.store, self.instance_id)
        resolved = False
        for gate in inst.open_gates:
            role = self._roles.get(gate.role_id)
            if role is None:
                continue
            policy = role.human_policy or self.template.human_policy_defaults
            reply = await self.human_gateway.request(role=role, policy=policy, blocking=True)
            if reply.content is not None:
                self._emit(EventType.GATE_RESOLVED, gate_id=gate.gate_id, decision=reply.decision)
                resolved = True
        return resolved

    async def _assign_and_contribute(
        self, role: Role
    ) -> tuple[TerminationStatus, str] | None:
        """One serialized turn: assign, then contribute (each contribution is its own turn)."""
        self._turn += 1
        self._emit(EventType.TURN_ASSIGNED, target_role_id=role.role_id, turn=self._turn)
        return await self._contribute(role)

    # --- pre-action oversight + bounded recovery (SPEC §1.7) -------------------------
    async def _ensure_ready(self, role: Role) -> str | tuple[TerminationStatus, str]:
        """Verify readiness; recover until ready. Returns 'ready'/'redecide' or a terminal."""
        for _ in range(self._max_recovery + 1):
            pre = await self.oversight.pre(role=role, transcript=self._transcript())
            ready = (pre.readiness is Readiness.READY
                     and pre.recommended_action is RecommendedAction.SELECT_SPEAKER)
            pre = pre.model_copy(update={"recovered": not ready})
            # record the checked role so "rejected this turn" is log-derivable (DialogueContext)
            self._emit(EventType.PRE_ACTION_VERIFIED, role_id=role.role_id, **pre.model_dump())
            if ready:
                return "ready"
            issues = "; ".join(i.description for i in pre.issues)
            match pre.recommended_action:
                case RecommendedAction.INJECT_CONTEXT:
                    self._inject_context(role, issues)
                    continue                             # retry the same candidate
                case RecommendedAction.REQUEST_HUMAN:
                    if await self._solicit_human(role, issues):
                        continue                         # human input injected → retry candidate
                    return "redecide"
                case RecommendedAction.WAIT_GATE:
                    if await self._wait_open_gate():
                        continue                         # gate resolved → retry candidate
                    return "redecide"
                case RecommendedAction.STOP:
                    return (TerminationStatus.PROVISIONAL,
                            f"pre-action stop for {role.role_id!r}: {issues}")
                case _:                                  # choose_alternative
                    return "redecide"
        return (TerminationStatus.PROVISIONAL, f"recovery exhausted for role {role.role_id!r}")

    # --- post-action oversight + routing (SPEC §1.7) --------------------------------
    async def _verify_and_route(self, role: Role) -> tuple[TerminationStatus, str] | None:
        """Verify the last contribution and route on the outcome. Returns a terminal signal/None."""
        revisions = 0
        while True:
            last = self._messages[-1] if self._messages else None
            if last is None or last.turn_id != self._turn:
                return None
            post = await self.oversight.post(
                role=role, message=last, transcript=self._transcript()
            )
            escalated = post.outcome is PostOutcome.ESCALATE_GATE
            post = post.model_copy(update={"escalated": escalated})
            self._emit(EventType.POST_ACTION_VERIFIED, **post.model_dump())

            match post.outcome:
                case PostOutcome.CONTINUE:
                    return None
                case PostOutcome.STOP:
                    return (TerminationStatus.DONE, "post-action stop")
                case PostOutcome.REQUEST_REVISION:
                    if revisions >= self._max_revisions or self._over_turns():
                        return None                      # give up revising; accept + continue
                    revisions += 1
                    self._emit(EventType.REVISION_REQUESTED, message_id=last.message_id,
                               role_id=role.role_id, attempt=revisions)
                    term = await self._assign_and_contribute(role)   # same role revises (new turn)
                    if term is not None:
                        return term
                    continue                             # re-verify the revision
                case PostOutcome.REQUEST_VERIFICATION:
                    verifier = self._pick_verifier(role)
                    self._emit(EventType.VERIFICATION_REQUESTED, message_id=last.message_id,
                               verifier_role_id=verifier.role_id if verifier else None)
                    if verifier is not None and not self._over_turns():
                        self._last_speaker = role.role_id
                        term = await self._assign_and_contribute(verifier)
                        if term is not None:
                            return term
                    return None
                case PostOutcome.ESCALATE_GATE:
                    return await self._escalate_gate(role)

    async def _escalate_gate(self, role: Role) -> tuple[TerminationStatus, str] | None:
        """Open a human approval gate for a human role in the cast; else record the escalation."""
        approver = next((r for r in self.template.roles if r.kind is RoleKind.HUMAN
                         and r.role_id in self.cast), None)
        if approver is None or self.human_gateway is None:
            self._emit(EventType.GATE_OPENED, gate_id=f"gate_{self._turn}", role_id=role.role_id)
            return None                                  # no approver wired; leave gate open
        return await self._assign_and_contribute(approver)

    # --- run -------------------------------------------------------------------------
    def _over_turns(self) -> bool:
        return self._max_turns is not None and self._turn >= self._max_turns

    async def run(self) -> DialogueInstance:
        """Run (or resume) the instance to a terminal status (SPEC §2.6–§2.10, §1.7 oversight)."""
        inst = restore(self.store, self.instance_id)
        if inst.status in TERMINAL_STATUSES:
            return inst                                    # terminal is read-only (resume no-op)
        self._hydrate(inst)
        self._bootstrap(inst)
        step_budget = (self._max_turns or 50) * (self._max_recovery + 2) + 10

        while True:
            self._steps += 1
            if self._over_turns():
                self._terminate(TerminationStatus.STOPPED, "turn cap reached")
                break
            if self._steps > step_budget:                  # guards recovery/redecide loops
                self._terminate(TerminationStatus.PROVISIONAL, "step budget exhausted")
                break

            action = await self._decide()
            if action.action == "stop":
                self._terminate(action.status, action.reason or "orchestrator stop")
                break
            if action.action == "suspend":
                # pause WITHOUT terminating — instance stays non-terminal, resumes later (§2.9)
                self._emit(EventType.INSTANCE_SUSPENDED, reason=action.reason or "suspended")
                break
            role = self._resolve_role(action.target_role_id)

            ready = await self._ensure_ready(role)         # pre-action oversight + recovery
            if isinstance(ready, tuple):
                self._terminate(*ready)
                break
            if ready == "redecide":
                continue                                   # recovery asked for a new candidate

            term = await self._assign_and_contribute(role)
            if term is not None:
                self._terminate(*term)
                break

            routed = await self._verify_and_route(role)    # post-action oversight + routing
            if routed is not None:
                self._terminate(*routed)
                break
            self._last_speaker = role.role_id

        return restore(self.store, self.instance_id)


__all__ = ["Orchestrator"]
