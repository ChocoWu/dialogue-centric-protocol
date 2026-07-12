"""Phase 7B — ArtifactProvisioner: verified, content-addressed, idempotent fetch (D16/D17/D19).

Hermetic: a fake fetcher writes fixed bytes, so no network. The cache is a tmp dir.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from dcp.component import ArtifactProvisioner
from dcp.component.manifest import ArtifactReference, Digest
from dcp.errors import ComponentError


def _artifact(payload: bytes, *, uri: str = "hf://alice/m/model.bin@v1",
              digest: str | None = None) -> ArtifactReference:
    value = digest if digest is not None else hashlib.sha256(payload).hexdigest()
    return ArtifactReference(uri=uri, digest=Digest(algorithm="sha256", value=value))


def _fetcher(payload: bytes) -> dict[str, object]:
    calls: list[str] = []

    def fetch(uri: str, dest: Path) -> None:
        calls.append(uri)
        dest.write_bytes(payload)

    return {"fetch": fetch, "calls": calls}


def test_downloads_verifies_and_caches(tmp_path: Path) -> None:
    payload = b"weights-bytes"
    f = _fetcher(payload)
    prov = ArtifactProvisioner(cache_dir=tmp_path, fetchers={"hf": f["fetch"]})   # type: ignore[dict-item]
    got = prov.provision(_artifact(payload))
    assert got.from_cache is False
    assert got.path.read_bytes() == payload
    assert f["calls"] == ["hf://alice/m/model.bin@v1"]              # one fetch


def test_second_provision_hits_the_cache(tmp_path: Path) -> None:
    payload = b"weights-bytes"
    f = _fetcher(payload)
    prov = ArtifactProvisioner(cache_dir=tmp_path, fetchers={"hf": f["fetch"]})   # type: ignore[dict-item]
    art = _artifact(payload)
    prov.provision(art)
    again = prov.provision(art)
    assert again.from_cache is True
    assert f["calls"] == ["hf://alice/m/model.bin@v1"]              # NOT fetched twice


def test_digest_mismatch_is_rejected_and_not_cached(tmp_path: Path) -> None:
    f = _fetcher(b"tampered")
    prov = ArtifactProvisioner(cache_dir=tmp_path, fetchers={"hf": f["fetch"]})   # type: ignore[dict-item]
    art = _artifact(b"expected", digest=hashlib.sha256(b"expected").hexdigest())  # fetch mismatches
    with pytest.raises(ComponentError):
        prov.provision(art)
    assert list(tmp_path.glob("sha256-*")) == []                   # nothing cached (.part cleaned)


def test_cache_is_content_addressed_by_digest(tmp_path: Path) -> None:
    payload = b"abc"
    f = _fetcher(payload)
    prov = ArtifactProvisioner(cache_dir=tmp_path, fetchers={"hf": f["fetch"]})   # type: ignore[dict-item]
    got = prov.provision(_artifact(payload))
    assert got.path.name == f"sha256-{hashlib.sha256(payload).hexdigest()}"


def test_unknown_scheme_errors(tmp_path: Path) -> None:
    prov = ArtifactProvisioner(cache_dir=tmp_path, fetchers={})
    with pytest.raises(ComponentError):
        prov.provision(_artifact(b"x", uri="ftp://host/m.bin"))


def test_file_scheme_copies_a_local_source(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"local-weights")
    prov = ArtifactProvisioner(cache_dir=tmp_path / "cache")        # real default fetchers (file)
    got = prov.provision(_artifact(b"local-weights", uri=f"file://{src}"))
    assert got.path.read_bytes() == b"local-weights"
