"""FastAPI Cloud entrypoint.

FastAPI Cloud may invoke ``fastapi run`` without an explicit module path. Keeping this tiny
root-level shim lets the CLI's default discovery find the app while construction stays in the API
factory/runtime modules.
"""

from bayesify.api.app import app

__all__ = ["app"]

