"""Importable ASGI app for Bayesify.

The transport layer is composed in :mod:`bayesify.api.factory`; route handlers live under
``bayesify.api.routes`` and shared process state lives in ``bayesify.api.runtime``.
"""

from __future__ import annotations

from bayesify.api.factory import create_app
from bayesify.api.runtime import api

app = create_app(api)
store = api.store
