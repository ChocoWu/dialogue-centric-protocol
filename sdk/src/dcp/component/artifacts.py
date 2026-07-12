"""Artifact provisioning (Phase 7B) — fetch a checkpoint/resource, verify it, cache it.

Separate from reference resolution (D16): a :class:`ComponentReferenceResolver` locates *manifests*;
an :class:`ArtifactProvisioner` fetches the *resources* a component depends on (weights/tokenizers).
Integrity is mandatory (D19): every artifact carries an immutable digest, the cache is **content-
addressed** by that digest, and a download whose bytes don't match is rejected — never cached.

Scheme-specific downloading is a pluggable ``fetch`` per scheme (``file`` / ``http(s)`` / ``hf``),
so tests provision without touching the network. The cache directory is ``$DCP_CACHE_DIR`` or
``~/.cache/dcp/artifacts``.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from ..errors import ComponentError
from .manifest import ArtifactReference, Digest

#: Downloads ``uri`` into ``dest`` (a file path). Raises on failure.
Fetcher = Callable[[str, Path], None]

_CHUNK = 1 << 20


@dataclass(frozen=True)
class ProvisionedArtifact:
    """A locally available, digest-verified artifact."""

    uri: str
    digest: Digest
    path: Path
    from_cache: bool


def default_cache_dir() -> Path:
    env = os.environ.get("DCP_CACHE_DIR")
    return Path(env) if env else Path.home() / ".cache" / "dcp" / "artifacts"


def _scheme(uri: str) -> str:
    return uri.split("://", 1)[0] if "://" in uri else "file"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify(path: Path, digest: Digest) -> bool:
    return _sha256_file(path) == digest.value          # algorithm is Literal["sha256"] (D19)


def _fetch_file(uri: str, dest: Path) -> None:
    src = uri[len("file://"):] if uri.startswith("file://") else uri
    shutil.copyfile(src, dest)


def _fetch_http(uri: str, dest: Path) -> None:
    if not uri.startswith(("http://", "https://")):      # defense in depth (beyond scheme routing)
        raise ComponentError(f"refusing non-http(s) artifact fetch: {uri!r}")
    with urllib.request.urlopen(uri) as resp, dest.open("wb") as out:  # noqa: S310 (scheme-checked)
        shutil.copyfileobj(resp, out)


def _fetch_hf(uri: str, dest: Path) -> None:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:                          # optional extra
        raise ComponentError("hf:// artifacts need the optional dependency: "
                             "pip install 'dcp[hf]'") from exc
    body = uri[len("hf://"):]
    body, _, revision = body.partition("@")
    parts = body.split("/")
    if len(parts) < 3:
        raise ComponentError(f"hf artifact {uri!r} must be hf://<namespace>/<repo>/<file>[@rev]")
    repo_id = "/".join(parts[:2])
    filename = "/".join(parts[2:])
    fetched = hf_hub_download(repo_id=repo_id, filename=filename, revision=revision or None)
    shutil.copyfile(fetched, dest)


def default_fetchers() -> dict[str, Fetcher]:
    return {"file": _fetch_file, "http": _fetch_http, "https": _fetch_http, "hf": _fetch_hf}


class ArtifactProvisioner:
    """Fetches + verifies + caches artifacts. Content-addressed by digest, so provisioning is
    idempotent and reproducible (D17/D19)."""

    def __init__(self, *, cache_dir: str | Path | None = None,
                 fetchers: Mapping[str, Fetcher] | None = None) -> None:
        self._cache = Path(cache_dir) if cache_dir is not None else default_cache_dir()
        self._fetchers = dict(fetchers) if fetchers is not None else default_fetchers()

    def provision(self, artifact: ArtifactReference) -> ProvisionedArtifact:
        self._cache.mkdir(parents=True, exist_ok=True)
        key = f"{artifact.digest.algorithm}-{artifact.digest.value}"
        cached = self._cache / key
        if cached.exists():
            if _verify(cached, artifact.digest):
                return ProvisionedArtifact(artifact.uri, artifact.digest, cached, from_cache=True)
            cached.unlink()                             # corrupt cache entry → re-fetch

        scheme = _scheme(artifact.uri)
        fetch = self._fetchers.get(scheme)
        if fetch is None:
            raise ComponentError(f"no artifact fetcher for scheme {scheme!r} ({artifact.uri!r})")

        fd, tmp_name = tempfile.mkstemp(dir=self._cache, prefix=f"{key}.", suffix=".part")
        os.close(fd)                                    # unique temp: no parallel-provision race
        tmp = Path(tmp_name)
        try:
            fetch(artifact.uri, tmp)
            if not _verify(tmp, artifact.digest):
                raise ComponentError(
                    f"artifact {artifact.uri!r} failed {artifact.digest.algorithm} verification "
                    "— refusing to cache (supply-chain integrity, D19)")
            tmp.replace(cached)
        finally:
            tmp.unlink(missing_ok=True)
        return ProvisionedArtifact(artifact.uri, artifact.digest, cached, from_cache=False)


__all__ = [
    "Fetcher",
    "ProvisionedArtifact",
    "ArtifactProvisioner",
    "default_cache_dir",
    "default_fetchers",
]
