"""Rubric loading.

Each ``rubric/<id>.yaml`` is one self-contained rubric (``synthesis`` is the default; ``gelman`` is
solely the Gelman 2020 workflow). ``loader.py`` is the registry over that directory:
``load_rubric(id)`` loads one, ``available_rubrics()`` lists them for the pickers. ``models.py`` has
the typed shape (``RubricSpec``: steps, the G5 ``scoring`` block, per-step ``citations``, and a
``label`` + ``summary`` preamble). Adding a rubric = dropping a yaml; nothing is hardcoded.
"""

from veribayes.core.rubric.loader import (
    RubricProfileError,
    available_rubrics,
    load_rubric,
)
from veribayes.core.rubric.models import RubricInfo, RubricSpec, RubricStep, ThresholdEntry

__all__ = [
    "RubricInfo",
    "RubricProfileError",
    "RubricSpec",
    "RubricStep",
    "ThresholdEntry",
    "available_rubrics",
    "load_rubric",
]
