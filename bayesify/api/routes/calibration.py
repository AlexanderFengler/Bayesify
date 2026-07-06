"""Validation-calibration report route."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from bayesify.core.validation import harness, to_calibration_payload

router = APIRouter()


@router.get("/api/calibration")
async def calibration() -> dict:
    real_dir = Path(harness.REAL_REPORTS_DIR)
    real = sorted(real_dir.glob("*.json")) if real_dir.is_dir() else []
    if real:
        return JSONResponse(json.loads(real[-1].read_text(encoding="utf-8")))
    fake = Path(harness.FAKE_GOLDSET_DIR)
    if fake.is_dir() and any(fake.glob("*.json")):
        report = harness.build(
            goldset_dir=harness.FAKE_GOLDSET_DIR,
            engine_dir=harness.FAKE_ENGINE_DIR,
            treat_as_real=False,
            n_resamples=300,
        )
        return to_calibration_payload(report)
    return {
        "status": "not_yet_validated",
        "note": "Validation (validation/protocol.md) runs at M7; no agreement metrics exist yet.",
    }
