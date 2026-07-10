"""M7 — HTTP API + SSE delivery over the Registry (SPEC §3.5; A3).

Uses Starlette's in-process ``TestClient`` (ASGI, no socket) so the suite stays hermetic. The
semantic core never imports Starlette; only ``dcp.delivery`` does.
"""

from __future__ import annotations

import json

from starlette.testclient import TestClient

from dcp import schema as s
from dcp.authoring import TemplateGenerator
from dcp.delivery import build_app
from dcp.provider import MockProvider
from dcp.registry import Registry
from dcp.state import SqlStore


def _template_payload(*, version: str = "1.0.0") -> dict[str, object]:
    return s.DialogueTemplate(
        template_id="t", version=version, title="T",
        termination_policy=s.TerminationPolicy(condition="done"),
        default_visibility=s.Visibility.PUBLIC,
        roles=[s.Role(role_id="a", name="A", kind=s.RoleKind.AGENT,
                      response_requirement=s.ResponseRequirement.REQUIRED)],
    ).model_dump(mode="json")


def _client() -> tuple[TestClient, Registry]:
    reg = Registry(SqlStore())
    return TestClient(build_app(reg)), reg


def test_register_template_over_http() -> None:
    client, reg = _client()
    r = client.post("/templates", json=_template_payload())
    assert r.status_code == 201
    assert reg.get_template("t", "1.0.0") is not None


def test_list_templates_over_http() -> None:
    client, _ = _client()
    client.post("/templates", json=_template_payload())
    r = client.get("/templates")
    assert r.status_code == 200
    assert [t["version"] for t in r.json()] == ["1.0.0"]


def test_instantiate_and_get_instance() -> None:
    client, _ = _client()
    client.post("/templates", json=_template_payload())
    r = client.post("/instances", json={"template_id": "t", "version": "1.0.0", "owner": "@owner"})
    assert r.status_code == 201
    iid = r.json()["instance_id"]
    got = client.get(f"/instances/{iid}")
    assert got.status_code == 200
    body = got.json()
    assert body["owner"] == "@owner"
    assert body["status"] == "created"


def test_join_over_http_returns_full_replay() -> None:
    client, _ = _client()
    client.post("/templates", json=_template_payload())          # public template
    iid = client.post(
        "/instances", json={"template_id": "t", "version": "1.0.0", "owner": "@owner"}
    ).json()["instance_id"]
    r = client.post(f"/instances/{iid}/join", json={"participant_id": "@guest"})
    assert r.status_code == 200
    roster = {row["participant_id"]: row["tier"] for row in r.json()["roster"]}
    assert roster["@guest"] == "observe"


def test_private_join_without_grant_is_403() -> None:
    reg = Registry(SqlStore())
    client = TestClient(build_app(reg))
    tmpl = _template_payload()
    tmpl["default_visibility"] = "private"
    client.post("/templates", json=tmpl)
    iid = client.post(
        "/instances", json={"template_id": "t", "version": "1.0.0", "owner": "@owner"}
    ).json()["instance_id"]
    r = client.post(f"/instances/{iid}/join", json={"participant_id": "@intruder"})
    assert r.status_code == 403


def test_unknown_instance_is_404() -> None:
    client, _ = _client()
    assert client.get("/instances/nope").status_code == 404


def _parse_sse(text: str) -> list[dict[str, object]]:
    """Extract JSON payloads from ``data:`` lines of an SSE body."""
    out: list[dict[str, object]] = []
    for line in text.splitlines():
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if payload:
                out.append(json.loads(payload))
    return out


def test_sse_replays_event_log_in_order() -> None:
    client, _ = _client()
    client.post("/templates", json=_template_payload())
    iid = client.post(
        "/instances", json={"template_id": "t", "version": "1.0.0", "owner": "@owner"}
    ).json()["instance_id"]
    client.post(f"/instances/{iid}/join", json={"participant_id": "@guest"})

    # tail=false => finite stream that ends once caught up (deterministic for tests)
    r = client.get(f"/instances/{iid}/events", params={"tail": "false"})
    assert r.status_code == 200
    events = _parse_sse(r.text)
    types_ = [e["type"] for e in events]
    assert types_[0] == "instance_created"
    assert types_.count("participant_joined") == 2               # owner + guest, in order
    assert "participant_joined" in types_


def test_sse_join_replays_history_to_late_subscriber() -> None:
    client, _ = _client()
    client.post("/templates", json=_template_payload())
    iid = client.post(
        "/instances", json={"template_id": "t", "version": "1.0.0", "owner": "@owner"}
    ).json()["instance_id"]
    # subscriber connects AFTER events already exist; must still receive them all (D3)
    r = client.get(f"/instances/{iid}/events", params={"tail": "false"})
    assert len(_parse_sse(r.text)) >= 2                          # created + owner-joined


# --- discovery / introspection surface (SPEC §1.11, §3.4) ------------------------------

def test_server_info_lists_capabilities_and_providers() -> None:
    client, _ = _client()
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["dcp_version"] == "0.2.0"
    assert body["capabilities"]["auto_generate"] is False        # no generator wired
    assert {p["provider"] for p in body["model_providers"]} == {"openai", "anthropic", "mock"}


def test_get_template_version() -> None:
    client, _ = _client()
    client.post("/templates", json=_template_payload())
    assert client.get("/templates/t/versions/1.0.0").status_code == 200
    assert client.get("/templates/t/versions/9.9.9").status_code == 404


def test_list_and_get_participants() -> None:
    client, _ = _client()
    p = s.Participant(participant_id="@bot", kind=s.RoleKind.AGENT, display_name="Bot",
                      discoverable=True).model_dump(mode="json")
    client.post("/participants", json=p)
    assert [x["participant_id"] for x in client.get("/participants").json()] == ["@bot"]
    assert client.get("/participants/@bot").json()["display_name"] == "Bot"
    assert client.get("/participants/@missing").status_code == 404


def test_list_instances_and_resumable_hint() -> None:
    client, _ = _client()                                        # public template
    client.post("/templates", json=_template_payload())
    inst = client.post(
        "/instances", json={"template_id": "t", "version": "1.0.0", "owner": "@owner"}
    ).json()
    assert inst["resumable"] is True                             # created => non-terminal
    listing = client.get("/instances").json()
    assert [i["instance_id"] for i in listing] == [inst["instance_id"]]
    assert listing[0]["resumable"] is True


def test_generate_endpoint_501_without_capability() -> None:
    client, _ = _client()                                        # no generator
    r = client.post("/templates/generate", json={"query": "make a debate template"})
    assert r.status_code == 501


def test_generate_endpoint_returns_draft_when_enabled() -> None:
    draft = _template_payload(version="2.0.0")
    reg = Registry(SqlStore(), generator=TemplateGenerator(MockProvider(structured_queue=[draft])))
    client = TestClient(build_app(reg))
    r = client.post("/templates/generate", json={"query": "brainstorm"})
    assert r.status_code == 200
    assert r.json()["version"] == "2.0.0"
    # draft is NOT auto-registered
    assert reg.get_template("t", "2.0.0") is None
