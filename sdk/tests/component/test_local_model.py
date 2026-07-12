"""Phase 7B — the local + model-artifact delivery path end-to-end.

An open-weights model_provider component: resolve → provision (download+verify the checkpoint) →
materialize (factory called with the local checkpoint path). No torch/network — a fake provider and
a fake fetcher stand in; the same wiring drives a real ``TransformersProvider.from_checkpoint``.
"""

from __future__ import annotations

import hashlib
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any

from dcp.component import (
    ArtifactProvisioner,
    ComponentManifest,
    InstalledResolver,
    materialize,
    provision,
    resolve,
)
from dcp.plugins import GROUP_COMPONENTS


class _CheckpointProvider:
    """A ModelProvider built from a local checkpoint path (stands in for TransformersProvider)."""

    def __init__(self, checkpoint: str) -> None:
        self.model = checkpoint

    async def text(self, *, instructions: str, content: str) -> str:
        return "ok"

    async def structured(self, *, instructions: str, content: str, schema: type) -> Any:
        raise NotImplementedError


def _load_provider(checkpoint: str) -> _CheckpointProvider:   # the entrypoint factory
    return _CheckpointProvider(checkpoint)


def test_local_model_resolves_provisions_and_materializes(tmp_path: Path) -> None:
    payload = b"safetensors-bytes"
    src = tmp_path / "model.safetensors"
    src.write_bytes(payload)

    manifest = ComponentManifest.model_validate({
        "schema_version": "1.0",
        "component": {"namespace": "alice", "name": "orch-7b", "version": "1.0.0",
                      "kind": "model_provider"},
        "interface": {"name": "dcp.model_provider", "version": "1.0"},
        "access_modes": [{
            "type": "local",
            "implementation": {"type": "python_package", "source": "pypi", "package": "alice-orch",
                               "entrypoint": f"{__name__}:_load_provider"},
            "artifacts": [{"uri": f"file://{src}",
                           "digest": {"algorithm": "sha256",
                                      "value": hashlib.sha256(payload).hexdigest()},
                           "format": "safetensors"}],
        }],
    })

    class _Fixed(InstalledResolver):
        def locate(self, ref):  # type: ignore[override]
            return manifest

    plan = resolve("installed://alice/orch-7b", resolvers=[_Fixed(source=[
        EntryPoint("alice/orch-7b", "x", GROUP_COMPONENTS)])])

    # the plan advertises the download as a *planned* side effect (nothing fetched yet)
    assert any("download artifact" in e for e in plan.expected_side_effects)

    report = provision(plan, present=lambda _m: True,
                       artifact_provisioner=ArtifactProvisioner(cache_dir=tmp_path / "cache"))
    provider = materialize(plan, artifacts=report.artifacts)

    assert isinstance(provider, _CheckpointProvider)
    assert Path(provider.model).read_bytes() == payload      # built from the provisioned checkpoint


def test_transformers_provider_from_checkpoint_uses_the_path() -> None:
    from dcp.provider import TransformersProvider

    p = TransformersProvider.from_checkpoint("/models/qwen3-local", generate=lambda _m: "x")
    assert p.model == "/models/qwen3-local"                   # local dir, not the HF default
