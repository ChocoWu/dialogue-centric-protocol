"""Keeps the runnable component example (docs/examples/component/) honest — like test_facade does.

Local flow runs the example's real code path (resolve → materialize → dialogue). Remote flow uses
the same manifest + handler through ComponentServer/TestClient (hermetic — the script's
uvicorn/socket is smoke-tested by hand, not in CI).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

_EXAMPLE = Path(__file__).resolve().parents[3] / "docs" / "examples" / "component"
pytestmark = pytest.mark.skipif(not _EXAMPLE.exists(), reason="component example not present")

if str(_EXAMPLE) not in sys.path:
    sys.path.insert(0, str(_EXAMPLE))


def _ref() -> str:
    return f"file://{_EXAMPLE / 'dcp-component.json'}"


async def test_local_flow_matches_the_example() -> None:
    from _demo import run_with

    from dcp.component import materialize, provision, resolve

    plan = resolve(_ref(), mode="local")
    provision(plan)                                   # no-op: module importable via sys.path
    policy = materialize(plan)
    inst = await run_with(policy)
    assert inst.status.value == "done"
    assert [m.content for m in inst.messages] == [
        "I propose 'Northstar'.", "'Northstar' is clear and low-risk. +1."]


async def test_remote_flow_matches_the_example() -> None:
    from _demo import run_with
    from round_robin import decide

    from dcp.component import (
        ComponentManifest,
        ComponentServer,
        HttpRemoteTransport,
        connect,
        resolve,
    )

    manifest = ComponentManifest.model_validate_json((_EXAMPLE / "dcp-component.json").read_text())
    tc = TestClient(ComponentServer(manifest, decide=decide).asgi())

    def opener(method: str, url: str, body: bytes | None,  # type: ignore[no-untyped-def]
               headers: dict[str, str], timeout: float):
        path = url.split("8123", 1)[-1] or "/"
        r = tc.request(method, path, content=body, headers=headers)
        return r.status_code, r.content

    plan = resolve(_ref(), mode="remote")
    policy = await connect(plan, HttpRemoteTransport("http://127.0.0.1:8123", opener=opener))
    inst = await run_with(policy)
    assert inst.status.value == "done"
    assert [m.role_id for m in inst.messages] == ["proposer", "critic"]


def test_manifest_declares_both_delivery_modes() -> None:
    from dcp.component import ComponentManifest

    m = ComponentManifest.model_validate_json((_EXAMPLE / "dcp-component.json").read_text())
    modes = {mode.type.value for mode in m.access_modes}
    assert modes == {"local", "remote"}                # the point of the example
    assert m.component.kind.value == "control_policy"
