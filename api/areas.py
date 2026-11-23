"""Rent Assistant: "which areas fit my budget" for the app.

Runs the same agent.core.tools.Tools.areas_within_budget logic the MCP server
uses, but against the in-process model instead of calling our own API over HTTP.
No LLM and no paid service: it is plain rules plus the existing rent model.

Work per request is capped: at most agent.core.tools.MAX_PREDICTIONS (32) model
runs, explanations switched off for the sweep, and at most MAX_CONCURRENT sweeps
at the same time (extra requests get HTTP 429 and the app asks to retry).
"""
from __future__ import annotations

import threading
from typing import Callable

from pydantic import ValidationError

from agent.core.errors import KodiWiseError
from agent.core.tools import Tools
from api.predictor import Predictor
from api.schemas import PredictRequest, PredictResponse

MAX_CONCURRENT = 2
_slots = threading.BoundedSemaphore(MAX_CONCURRENT)


class Busy(Exception):
    """Too many sweeps already running."""


class LocalApi:
    """The two calls Tools needs (locations, predict), answered by the loaded model."""

    def __init__(self, predictor: Predictor) -> None:
        self._predictor = predictor
        self._locations = predictor.known_locations()

    def locations(self) -> list[str]:
        return list(self._locations)

    def predict(self, payload: dict) -> dict:
        try:
            req = PredictRequest(**{**payload, "explain": False})
        except ValidationError as exc:
            raise KodiWiseError("Those inputs were not valid. Check the values and try again.") from exc
        result = self._predictor.predict(
            bedrooms_num=req.bedrooms_num, bathrooms_num=req.bathrooms_num, location_std=req.location_std,
            sq_m=req.sq_m, is_furnished=req.is_furnished, property_type=req.property_type,
            has_generator=req.has_generator, has_borehole=req.has_borehole, has_cctv=req.has_cctv,
            has_dsq=req.has_dsq, has_play_area=req.has_play_area, has_garden=req.has_garden,
            explain=False,
        )
        return PredictResponse(**result).model_dump(exclude_none=True)


def areas_within_budget(
    predictor: Predictor, budget_kes, bedrooms, bathrooms, near=None, max_km=5.0, sq_m=None,
    tools_factory: Callable[[LocalApi], Tools] = Tools,
) -> dict:
    """Raises KodiWiseError for bad input (shown to the user) and Busy when over capacity."""
    if not _slots.acquire(blocking=False):
        raise Busy()
    try:
        tools = tools_factory(LocalApi(predictor))
        kwargs = {} if near is None else {"near": near, "max_km": max_km}
        return tools.areas_within_budget(budget_kes, bedrooms, bathrooms, sq_m=sq_m, **kwargs)
    finally:
        _slots.release()
