#!/usr/bin/env python3
"""Share your orchestrator: load a ControlPolicy BY NAME from a plugin's `dcp.control_policies`
entry point, then run a dialogue with it. This is exactly how a consumer uses a shared component —
no import of the plugin's module here.

Install the bundled example plugin first:
    pip install -e examples/plugin-example
    python docs/examples/orchestrator_share_policy.py

See docs/07-extending-sharing.md for the full recipe (templates, oversight, and agents share the
same way; for portable local/remote distribution, package a component — components-reference.md).
"""
from __future__ import annotations

import asyncio

from dcp import Server, plugins
from dcp import schema as s
from dcp.provider import MockProvider

TEMPLATE = s.DialogueTemplate(
    template_id="shared-policy-demo", version="1.0.0", title="Shared policy", goal="Chat briefly.",
    termination_policy=s.TerminationPolicy(condition="done", max_turns=4),
    roles=[s.Role(role_id="a", name="A", kind=s.RoleKind.AGENT,
                  response_requirement=s.ResponseRequirement.REQUIRED),
           s.Role(role_id="b", name="B", kind=s.RoleKind.AGENT,
                  response_requirement=s.ResponseRequirement.REQUIRED)],
)


async def main() -> None:
    available = plugins.available_plugins()
    if "round_robin" not in available.get("dcp.control_policies", []):
        raise SystemExit(
            "The example plugin isn't installed, so its policy can't be discovered. Install it:\n"
            "    pip install -e examples/plugin-example\n"
            f"(currently discovered control policies: {available.get('dcp.control_policies', [])})")

    Policy = plugins.load_control_policy("round_robin")   # resolved by name via the entry point

    server = Server(database_url="sqlite:///:memory:")
    server.register_template(TEMPLATE)
    for pid in ("a", "b"):
        server.register_participant(
            s.Participant(participant_id=pid, kind=s.RoleKind.AGENT, display_name=pid.upper()))
    server.instantiate(s.TemplateRef(template_id="shared-policy-demo", version="1.0.0"),
                       owner="a", instance_id="demo")

    inst = await server.run(
        "demo", cast={"a": "a", "b": "b"},
        orchestrator_provider=MockProvider(),   # unused: round-robin needs no model
        agent_providers={"a": MockProvider(texts=["A"]), "b": MockProvider(texts=["B"])},
        control_policy=Policy())
    print(f"Ran with the shared 'round_robin' policy: "
          f"{[m.role_id for m in inst.messages]}  status={inst.status.value}")


if __name__ == "__main__":
    asyncio.run(main())
