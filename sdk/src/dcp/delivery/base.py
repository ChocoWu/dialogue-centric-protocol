"""Delivery layer seam (SPEC §3.5).

The semantic protocol MUST NOT depend on any particular delivery mechanism, so this module stays
free of any transport library. A :class:`Delivery` is any binding that exposes a
:class:`~dcp.registry.Registry` to clients over some transport; the shipped one is
``HttpSseDelivery`` (HTTP + SSE), but WebSocket / polling / batch bindings satisfy the same seam.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Delivery(Protocol):
    """A transport binding over a Registry (SPEC §3.5). Concrete impls live outside the core."""

    def asgi(self) -> Any:
        """Return the underlying application object for this binding (e.g. an ASGI app)."""
        ...


__all__ = ["Delivery"]
