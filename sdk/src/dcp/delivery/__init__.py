"""Delivery layer (SPEC §3.5): transport bindings over the Registry. HTTP/SSE ships here."""

from __future__ import annotations

from .base import Delivery
from .http_sse import HttpSseDelivery, build_app

__all__ = ["Delivery", "HttpSseDelivery", "build_app"]
