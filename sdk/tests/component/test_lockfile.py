"""Phase 7B — the reproducible lockfile (D17): a serialized, re-loadable resolution plan."""

from __future__ import annotations

from importlib.metadata import EntryPoint
from pathlib import Path

from dcp.component import (
    ComponentManifest,
    InstalledResolver,
    read_lock,
    resolve,
    write_lock,
)
from dcp.plugins import GROUP_COMPONENTS


def _manifest() -> ComponentManifest:
    return ComponentManifest.model_validate({
        "schema_version": "1.0",
        "component": {"namespace": "a", "name": "p", "version": "1.0.0", "kind": "control_policy"},
        "interface": {"name": "dcp.control_policy", "version": "1.0"},
        "access_modes": [{
            "type": "local",
            "implementation": {"type": "python_package", "source": "pypi", "package": "p",
                               "entrypoint": "p:P"},
            "artifacts": [{"uri": "hf://a/m/w.bin@r",
                           "digest": {"algorithm": "sha256", "value": "a" * 64}}],
        }],
    })


def _plan():  # type: ignore[no-untyped-def]
    class _Fixed(InstalledResolver):
        def locate(self, ref):  # type: ignore[override]
            return _manifest()

    return resolve("installed://a/p", resolvers=[_Fixed(source=[
        EntryPoint("a/p", "x", GROUP_COMPONENTS)])])


def test_lock_round_trips(tmp_path: Path) -> None:
    plan = _plan()
    path = write_lock(plan, tmp_path / "dcp-components.lock")
    assert path.exists()
    assert read_lock(path) == plan                          # exact round-trip


def test_lock_records_artifact_digest(tmp_path: Path) -> None:
    path = write_lock(_plan(), tmp_path / "l.lock")
    text = path.read_text()
    assert "a" * 64 in text and "hf://a/m/w.bin@r" in text  # immutable pin captured (D19)
