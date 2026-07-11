"""Orchestration layer (SPEC §3.3): the control loop, oversight, human intervention, termination."""

from __future__ import annotations

from .actions import OrchestratorAction, resolve_termination
from .context import DialogueContext
from .human import HumanGateway, HumanReply, ScriptedHumanGateway
from .orchestrator import Orchestrator
from .oversight import (
    Check,
    CheckOutcome,
    DefaultOversight,
    LlmOversight,
    OversightPolicy,
    RubricOversight,
    ScriptedOversight,
)
from .policy import ControlPolicy, FlowPolicy, PlanPolicy

__all__ = [
    "Orchestrator",
    "OrchestratorAction",
    "DialogueContext",
    "resolve_termination",
    "ControlPolicy",
    "PlanPolicy",
    "FlowPolicy",
    "OversightPolicy",
    "DefaultOversight",
    "ScriptedOversight",
    "LlmOversight",
    "RubricOversight",
    "Check",
    "CheckOutcome",
    "HumanGateway",
    "HumanReply",
    "ScriptedHumanGateway",
]
