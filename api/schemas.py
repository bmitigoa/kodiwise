"""Request/response schemas for the KodiWise prediction API.

Deliberately matches only what PredictionFormActivity can actually send
(bedrooms, bathrooms, location) -- see ml.features.APP_FEATURE_SET and
docs/PROGRESS.md for why the richer paper/Run-B feature set isn't served.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class PredictRequest(BaseModel):
    bedrooms_num: int = Field(..., ge=0, le=20, description="0 = studio/bedsitter")
    bathrooms_num: int = Field(..., ge=0, le=20)
    location_std: str = Field(..., min_length=1, max_length=200)

    @field_validator("location_std")
    @classmethod
    def strip_location(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("location_std must not be blank")
        return v


class PredictResponse(BaseModel):
    predicted_rent_kes: float
    predicted_rent_low_kes: float
    predicted_rent_high_kes: float
    model_version: str
    note: str


class HealthResponse(BaseModel):
    ok: bool
    model_loaded: bool
    model_version: str | None = None


class ModelVersionResponse(BaseModel):
    version: str
    feature_set: str
    trained_on: str
    n_train: int
    n_test: int
    test_r2: float
    test_mape: float
    note: str
