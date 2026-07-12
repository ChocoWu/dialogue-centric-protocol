"""Phase 7A — the provision stage (PROPOSAL §5, D11): install a local package before materialize.

Provision is idempotent and injectable, so these tests never touch real pip: ``present`` fakes the
presence check and ``runner`` captures the install spec.
"""

from __future__ import annotations

from importlib.metadata import EntryPoint

import pytest

from dcp.component import ComponentManifest, InstalledResolver, provision, resolve
from dcp.errors import ComponentError
from dcp.plugins import GROUP_COMPONENTS


def _manifest(*, source: str = "pypi", version: str | None = "1.2.0",
              remote: bool = False, artifacts: bool = False) -> ComponentManifest:
    local = {
        "type": "local",
        "implementation": {"type": "python_package", "source": source, "package": "somepkg",
                           "version": version, "entrypoint": "somepkg.mod:Policy"},
    }
    if artifacts:
        local["artifacts"] = [{"uri": "hf://x/m@abc",
                               "digest": {"algorithm": "sha256", "value": "d" * 64}}]
    modes: list[dict[str, object]] = [local]
    if remote:
        modes.append({"type": "remote", "binding": {"protocol": "dcp-http", "version": "1.0"},
                      "endpoint": "https://x/dcp", "auth": {"type": "bearer",
                                                            "credential_slot": "tok"}})
    return ComponentManifest.model_validate({
        "schema_version": "1.0",
        "component": {"namespace": "a", "name": "p", "version": "1.0.0", "kind": "control_policy"},
        "interface": {"name": "dcp.control_policy", "version": "1.0"},
        "access_modes": modes,
    })


def _plan(manifest: ComponentManifest, *, mode: str | None = None):
    src = [EntryPoint("a/p", "x", GROUP_COMPONENTS)]

    class _Fixed(InstalledResolver):
        def locate(self, ref):  # type: ignore[override]
            return manifest

    return resolve("installed://a/p", resolvers=[_Fixed(source=src)], mode=mode)


def test_provision_is_a_noop_when_already_present() -> None:
    calls: list[str] = []
    report = provision(_plan(_manifest()), present=lambda _m: True, runner=calls.append)
    assert report.action == "already-present"
    assert calls == []                                    # nothing installed


def test_provision_installs_the_pinned_spec_when_absent() -> None:
    calls: list[str] = []
    report = provision(_plan(_manifest()), present=lambda _m: False, runner=calls.append)
    assert report.action == "installed"
    assert calls == ["somepkg==1.2.0"]                    # pinned to the impl version


def test_provision_uses_the_module_from_the_entrypoint() -> None:
    seen: list[str] = []

    def _present(module: str) -> bool:
        seen.append(module)
        return True

    provision(_plan(_manifest()), present=_present)
    assert seen == ["somepkg.mod"]                        # the entrypoint's module, not the package


def test_provision_rejects_remote_mode() -> None:
    with pytest.raises(ComponentError):
        provision(_plan(_manifest(remote=True), mode="remote"), present=lambda _m: False)


def test_provision_provisions_artifacts(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import hashlib

    from dcp.component import ArtifactProvisioner

    payload = b"weights"
    # point the fixture artifact at real bytes with a matching digest
    src = tmp_path / "w.bin"
    src.write_bytes(payload)
    manifest = _manifest(artifacts=True)
    manifest.access_modes[0].artifacts[0].uri = f"file://{src}"                 # type: ignore[union-attr]
    manifest.access_modes[0].artifacts[0].digest.value = hashlib.sha256(payload).hexdigest()  # type: ignore[union-attr]

    ap = ArtifactProvisioner(cache_dir=tmp_path / "cache")
    report = provision(_plan(manifest), present=lambda _m: True, artifact_provisioner=ap)
    assert len(report.artifacts) == 1
    assert report.artifacts[0].path.read_bytes() == payload


def test_provision_defers_non_pypi_sources() -> None:
    with pytest.raises(ComponentError):
        provision(_plan(_manifest(source="git", version=None)), present=lambda _m: False)
