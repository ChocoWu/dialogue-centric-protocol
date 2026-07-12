"""Phase-7 review pass — hardening: manifest field validation, credential/endpoint safety, robust
error envelopes. Each test pins a fix from the security/correctness review.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient

from dcp.component import (
    ComponentManifest,
    ComponentServer,
    HttpRemoteTransport,
    RemoteAccessMode,
    RemoteAuth,
    resolve_credential,
)
from dcp.component.manifest import Binding
from dcp.component.remote import RemoteRequest
from dcp.errors import RemoteComponentError

_HEX = "a" * 64


def _manifest(**over: object) -> dict[str, object]:
    doc: dict[str, object] = {
        "schema_version": "1.0",
        "component": {"namespace": "a", "name": "p", "version": "1.0.0", "kind": "control_policy"},
        "interface": {"name": "dcp.control_policy", "version": "1.0"},
        "access_modes": [{"type": "local", "implementation": {
            "type": "python_package", "source": "pypi", "package": "p", "entrypoint": "p:P"}}],
    }
    doc.update(over)
    return doc


# --- manifest field validation (path traversal / SSRF / pip redirection) ----------------

def test_digest_must_be_hex_64() -> None:
    art = [{"type": "local", "implementation": {"type": "python_package", "source": "pypi",
                                                "package": "p", "entrypoint": "p:P"},
            "artifacts": [{"uri": "hf://a/m/w@r", "digest": {"algorithm": "sha256",
                                                             "value": "../etc/passwd"}}]}]
    with pytest.raises(ValidationError):
        ComponentManifest.model_validate(_manifest(access_modes=art))


def test_remote_endpoint_must_be_http_s() -> None:
    remote = [{"type": "remote", "binding": {"protocol": "dcp-http", "version": "1.0"},
               "endpoint": "file:///etc/passwd"}]
    with pytest.raises(ValidationError):
        ComponentManifest.model_validate(_manifest(access_modes=remote))


def test_pypi_package_cannot_be_a_url_or_vcs_spec() -> None:
    for bad in ("git+https://evil/x", "https://evil/x.whl", "./local", "a b"):
        impl = [{"type": "local", "implementation": {"type": "python_package", "source": "pypi",
                                                     "package": bad, "entrypoint": "p:P"}}]
        with pytest.raises(ValidationError):
            ComponentManifest.model_validate(_manifest(access_modes=impl))


# --- confused-deputy: env credentials only go to https endpoints (D22) ------------------

def _remote_mode(endpoint: str) -> RemoteAccessMode:
    return RemoteAccessMode(binding=Binding(protocol="dcp-http", version="1.0"), endpoint=endpoint,
                            auth=RemoteAuth(credential_slot="token"))


def test_env_credential_is_withheld_from_plaintext_endpoints() -> None:
    env = {"DCP_CRED_TOKEN": "sekret"}
    assert resolve_credential(_remote_mode("http://attacker.tld"), env=env) is None
    assert resolve_credential(_remote_mode("https://alice.example"), env=env) == "sekret"
    # an explicit token is the owner's deliberate choice — always honored
    assert resolve_credential(_remote_mode("http://x"), token="explicit", env=env) == "explicit"


# --- robust error envelopes -------------------------------------------------------------

def test_server_wraps_a_raising_handler_in_an_error_envelope() -> None:
    def boom(_payload: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("kaboom")

    client = TestClient(ComponentServer(ComponentManifest.model_validate(_manifest()),
                                        operations={"decide": boom}).asgi())
    req = RemoteRequest(interface="dcp.control_policy", interface_version="1.0",  # type: ignore[arg-type]
                        binding_version="1.0", operation="decide", invocation_id="i", payload={})
    r = client.post("/invoke", json=req.model_dump(mode="json"))
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal"          # a clean envelope, not an HTML 500


async def test_client_raises_on_a_non_envelope_response() -> None:
    def opener(method: str, url: str, body: bytes | None,  # type: ignore[no-untyped-def]
               headers: dict[str, str], timeout: float):
        return 502, b"<html>bad gateway</html>"

    t = HttpRemoteTransport("https://x/dcp", opener=opener)
    req = RemoteRequest(interface="dcp.control_policy", interface_version="1.0",  # type: ignore[arg-type]
                        binding_version="1.0", operation="decide", invocation_id="i", payload={})
    with pytest.raises(RemoteComponentError):
        await t.invoke(req)


# --- projection no longer advertises no-op knobs ----------------------------------------

def test_projection_rejects_removed_knobs() -> None:
    from dcp.component import ContextProjection

    with pytest.raises(ValidationError):
        ContextProjection(participant_profiles="omit")      # type: ignore[call-arg]  (removed knob)
