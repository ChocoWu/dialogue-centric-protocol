"""Phase 7C.2b — streaming contributions (SSE, bindings/http-sse.md).

Three hermetic angles: the server SSE endpoint (via TestClient), the client SSE parser (via injected
frames), and the in-process loopback stream driving ``RemoteAgent.stream_text``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from starlette.testclient import TestClient

from dcp.component import (
    ComponentManifest,
    ComponentServer,
    HttpRemoteTransport,
    LoopbackTransport,
    RemoteAgent,
    RemoteComponentClient,
)
from dcp.component.remote import RemoteRequest, descriptor_from_manifest
from dcp.errors import RemoteComponentError


def _manifest() -> ComponentManifest:
    return ComponentManifest.model_validate({
        "schema_version": "1.0",
        "component": {"namespace": "alice", "name": "scout", "version": "1.0.0", "kind": "agent"},
        "interface": {"name": "dcp.agent_definition", "version": "1.0"},
        "access_modes": [{"type": "remote", "binding": {"protocol": "dcp-http", "version": "1.0"},
                          "endpoint": "https://alice.example/scout"}],
    })


async def _three_frames(payload: dict[str, Any]) -> AsyncIterator[str]:
    for word in payload["content"].split():
        yield word + " "


def _req(operation: str = "generate") -> RemoteRequest:
    return RemoteRequest(interface="dcp.agent_definition", interface_version="1.0",  # type: ignore[arg-type]
                         binding_version="1.0", operation=operation, invocation_id="i",
                         payload={"content": "one two three"})


# --- server SSE (via TestClient) -------------------------------------------------------

def test_server_streams_chunks_then_a_result_frame() -> None:
    server = ComponentServer(_manifest(), stream_operations={"generate": _three_frames})
    client = TestClient(server.asgi())
    with client.stream("POST", "/invoke", json=_req().model_dump(mode="json"),
                       headers={"accept": "text/event-stream"}) as resp:
        assert resp.status_code == 200
        events, datas = [], []
        for line in resp.iter_lines():
            if line.startswith("event:"):
                events.append(line[len("event:"):].strip())
            elif line.startswith("data:"):
                datas.append(line[len("data:"):].strip())
    assert events == ["chunk", "chunk", "chunk", "result"]
    assert [json.loads(d).get("text") for d in datas[:3]] == ["one ", "two ", "three "]
    final = json.loads(datas[3])
    assert final["ok"] is True and final["result"]["text"] == "one two three "


def test_server_falls_back_to_json_without_sse_accept() -> None:
    # same op, but no event-stream Accept and no non-stream handler → 501
    server = ComponentServer(_manifest(), stream_operations={"generate": _three_frames})
    client = TestClient(server.asgi())
    r = client.post("/invoke", json=_req().model_dump(mode="json"))
    assert r.status_code == 501


# --- client SSE parser (injected frames) -----------------------------------------------

def _canned_opener(frames: list[bytes]):  # type: ignore[no-untyped-def]
    async def open_(method: str, url: str, body: bytes | None, headers: dict[str, str],
                    timeout: float) -> AsyncIterator[bytes]:
        for f in frames:
            yield f
    return open_


async def test_http_transport_parses_sse_frames() -> None:
    result_data = b'data: {"invocation_id": "i", "ok": true, "result": {"text": "hello"}}\n'
    frames = [
        b"event: chunk\n", b'data: {"text": "hel"}\n', b"\n",
        b"event: chunk\n", b'data: {"text": "lo"}\n', b"\n",
        b"event: result\n", result_data, b"\n",
    ]
    transport = HttpRemoteTransport("https://x/scout", stream_opener=_canned_opener(frames))
    out = [frame async for frame in transport.stream(_req())]
    assert out == ["hel", "lo"]                       # result frame ends the stream, not yielded


# --- in-process loopback + RemoteAgent.stream_text -------------------------------------

async def test_remote_agent_stream_text_over_loopback() -> None:
    transport = LoopbackTransport(descriptor=descriptor_from_manifest(_manifest()),
                                  stream=_three_frames)
    agent = RemoteAgent(RemoteComponentClient(transport, manifest=_manifest()))
    out = "".join([f async for f in agent.stream_text(instructions="i", content="alpha beta")])
    assert out == "alpha beta "


async def test_stream_raises_when_transport_cannot_stream() -> None:
    class _NoStream:
        async def describe(self) -> Any:
            return descriptor_from_manifest(_manifest())

        async def health(self) -> bool:
            return True

        async def invoke(self, request: RemoteRequest) -> Any:
            raise AssertionError("unused")

    client = RemoteComponentClient(_NoStream(), manifest=_manifest())
    with pytest.raises(RemoteComponentError):
        _ = [f async for f in client.stream("generate", {})]
