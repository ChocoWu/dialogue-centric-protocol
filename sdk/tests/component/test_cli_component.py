"""Phase 7A — the ``dcp inspect / install / use`` CLI over the resolver + plan.

Hermetic: a JSON manifest is written to a temp file whose entrypoint targets a class in this module
(already importable), so provisioning is a no-op — no pip, no network.
"""

from __future__ import annotations

import json
from pathlib import Path

from dcp.cli import main
from dcp.orchestration import DialogueContext, OrchestratorAction
from dcp.schema import TerminationStatus


class CliPolicy:
    """The materialization target for the ``use`` command."""

    async def decide(self, ctx: DialogueContext) -> OrchestratorAction:
        return OrchestratorAction(action="stop", status=TerminationStatus.DONE)


def _manifest_file(tmp_path: Path) -> str:
    doc = {
        "schema_version": "1.0",
        "component": {"namespace": "alice", "name": "rr", "version": "1.0.0",
                      "kind": "control_policy"},
        "metadata": {"license": "Apache-2.0"},
        "interface": {"name": "dcp.control_policy", "version": "1.0"},
        "access_modes": [{
            "type": "local",
            "implementation": {"type": "python_package", "source": "pypi", "package": "alice-rr",
                               "entrypoint": f"{__name__}:CliPolicy"},
        }],
    }
    path = tmp_path / "dcp-component.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return f"file://{path}"


def test_inspect_prints_a_side_effect_free_plan(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    rc = main(["inspect", _manifest_file(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "component: alice/rr @ 1.0.0  (control_policy)" in out
    assert "side effects:" in out
    assert "component license: Apache-2.0" in out


def test_install_is_a_noop_for_an_already_present_component(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    rc = main(["install", _manifest_file(tmp_path), "--yes"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "already present" in out                       # this module is importable ⇒ no pip


def test_use_materializes_and_confirms(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    rc = main(["use", _manifest_file(tmp_path), "--yes"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "materialized control_policy: CliPolicy" in out


def test_inspect_unknown_scheme_reports_error(capsys) -> None:  # type: ignore[no-untyped-def]
    rc = main(["inspect", "pypi://alice-rr@1.0.0"])       # 7B resolver
    assert rc == 1
    assert "error:" in capsys.readouterr().out


class CheckpointProvider:
    def __init__(self, checkpoint: str) -> None:
        self.model = checkpoint

    async def text(self, *, instructions: str, content: str) -> str:
        return "ok"

    async def structured(self, *, instructions: str, content: str, schema: type) -> object:
        raise NotImplementedError


def load_provider(checkpoint: str) -> CheckpointProvider:
    return CheckpointProvider(checkpoint)


def _model_manifest_file(tmp_path: Path) -> str:
    import hashlib

    weights = tmp_path / "model.bin"
    weights.write_bytes(b"weights")
    doc = {
        "schema_version": "1.0",
        "component": {"namespace": "alice", "name": "orch-7b", "version": "1.0.0",
                      "kind": "model_provider"},
        "interface": {"name": "dcp.model_provider", "version": "1.0"},
        "access_modes": [{
            "type": "local",
            "implementation": {"type": "python_package", "source": "pypi", "package": "alice-orch",
                               "entrypoint": f"{__name__}:load_provider"},
            "artifacts": [{"uri": f"file://{weights}",
                           "digest": {"algorithm": "sha256",
                                      "value": hashlib.sha256(b"weights").hexdigest()}}],
        }],
    }
    path = tmp_path / "dcp-component.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return f"file://{path}"


def test_use_provisions_artifact_and_materializes(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DCP_CACHE_DIR", str(tmp_path / "cache"))   # hermetic artifact cache
    rc = main(["use", _model_manifest_file(tmp_path), "--yes"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "materialized model_provider: CheckpointProvider" in out


def test_install_writes_a_lockfile(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DCP_CACHE_DIR", str(tmp_path / "cache"))
    lock = tmp_path / "dcp-components.lock"
    rc = main(["install", _model_manifest_file(tmp_path), "--yes", "--lock", str(lock)])
    out = capsys.readouterr().out
    assert rc == 0
    assert lock.exists()
    assert "downloaded" in out and "wrote lockfile" in out


def test_connect_on_a_local_only_component_errors(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    # `connect` forces remote; a local-only manifest has no remote mode → clean error, exit 1
    rc = main(["connect", _manifest_file(tmp_path)])
    assert rc == 1
    assert "error:" in capsys.readouterr().out
