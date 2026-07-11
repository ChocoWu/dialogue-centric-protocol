"""Phase 6.1e — guard that the example plugin package actually works end-to-end.

The example lives at repo-root ``examples/plugin-example``; we prepend its ``src`` to the path (no
install, no venv mutation) and drive its custom control policy + oversight through the Orchestrator.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest

from dcp import schema as s
from dcp.orchestration import Orchestrator
from dcp.provider import MockProvider
from dcp.state import InstanceHeader, SqlStore

_EXAMPLE_SRC = Path(__file__).resolve().parents[2] / "examples" / "plugin-example" / "src"
_TS = datetime(2026, 7, 11, tzinfo=UTC)


@pytest.fixture
def example(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    if not _EXAMPLE_SRC.is_dir():
        pytest.skip(f"example package not found at {_EXAMPLE_SRC}")
    monkeypatch.syspath_prepend(str(_EXAMPLE_SRC))
    import dcp_plugin_example  # noqa: PLC0415  (import inside fixture is intentional)

    return dcp_plugin_example


def _orch(ex: ModuleType, agent_texts: dict[str, list[str]]) -> Orchestrator:
    tmpl = ex.two_agent_debate()
    assert isinstance(tmpl, s.DialogueTemplate)
    store = SqlStore()
    store.create_instance(InstanceHeader(
        instance_id="dlg", template_ref=s.TemplateRef(template_id=tmpl.template_id,
                                                       version=tmpl.version),
        owner="@o", visibility=s.Visibility.PRIVATE, dcp_version="0.2.0", created_at=_TS))
    return Orchestrator(
        store=store, template=tmpl, instance_id="dlg",
        cast={"optimist": "optimist", "skeptic": "skeptic"},
        participants={r: s.Participant(participant_id=r, kind=s.RoleKind.AGENT, display_name=r)
                      for r in ("optimist", "skeptic")},
        provider=MockProvider(),
        agent_providers={r: MockProvider(texts=t) for r, t in agent_texts.items()},
        control_policy=ex.RoundRobinPolicy(),
        oversight=ex.NoShoutingOversight())


async def test_round_robin_policy_drives_the_debate(example: ModuleType) -> None:
    inst = await _orch(example, {"optimist": ["upside"], "skeptic": ["risk"]}).run()
    assert inst.status is s.InstanceStatus.DONE
    assert [m.role_id for m in inst.messages] == ["optimist", "skeptic"]   # round-robin order


async def test_no_shouting_oversight_forces_a_revision(example: ModuleType) -> None:
    # the optimist SHOUTS first; the rubric check flags it → a revision is requested
    inst = await _orch(example, {"optimist": ["SHOUTING!!", "calmer point"],
                                 "skeptic": ["a measured risk"]}).run()
    assert inst.status is s.InstanceStatus.DONE
    assert s.EventType.REVISION_REQUESTED in {e.type for e in inst.events}
    assert [m.content for m in inst.messages] == ["SHOUTING!!", "calmer point", "a measured risk"]
