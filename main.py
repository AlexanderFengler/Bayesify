"""FastAPI Cloud entrypoint.

FastAPI Cloud may invoke ``fastapi run`` without an explicit module path. Keeping this tiny
root-level shim lets the CLI's default discovery find the production app while the implementation
stays in ``bayesify.api.app``.
"""

from bayesify.api.app import app

