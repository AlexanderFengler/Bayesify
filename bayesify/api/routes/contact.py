"""About-us contact-form route: relays a visitor's message as an email via Resend."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from bayesify.api.config import contact_from_email, contact_to_email, resend_api_key

logger = logging.getLogger(__name__)

router = APIRouter()

RESEND_ENDPOINT = "https://api.resend.com/emails"
SEND_FAILED_DETAIL = "Could not send your message. Please try again."


class ContactMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    message: str = Field(min_length=1, max_length=5000)


@router.post("/api/contact")
async def send_contact(payload: ContactMessage) -> dict[str, bool]:
    api_key = resend_api_key()
    if not api_key:
        # The form is wired up but no provider is configured — surface a clean "unavailable"
        # rather than a 500, so the UI can tell the visitor to email directly.
        raise HTTPException(status_code=503, detail="The contact form is not available right now.")

    to_addr = contact_to_email()
    body = {
        "from": f"Bayesify Contact <{contact_from_email()}>",
        "to": [to_addr],
        "reply_to": str(payload.email),
        "subject": f"Bayesify contact form — {payload.name}",
        "text": (
            f"Name: {payload.name}\n"
            f"Email: {payload.email}\n\n"
            f"{payload.message}\n"
        ),
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                RESEND_ENDPOINT,
                json=body,
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.HTTPError as exc:
        logger.warning("contact form: Resend request failed: %s", exc)
        raise HTTPException(status_code=502, detail=SEND_FAILED_DETAIL) from exc

    if resp.status_code >= 400:
        # Resend returns a JSON {message, name} on error; log it but never leak provider internals.
        logger.warning("contact form: Resend rejected (%s): %s", resp.status_code, resp.text)
        raise HTTPException(status_code=502, detail=SEND_FAILED_DETAIL)

    return {"sent": True}
