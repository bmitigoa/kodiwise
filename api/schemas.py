"""Request/response schemas for the KodiWise prediction API.

Serves ml.features.RUN_D_FEATURE_SET: bedrooms/bathrooms/location are
required (the three fields every form screen always collects); everything
else is optional, matching exactly what PredictionFormActivity's and
PropertyUploadActivity's expanded forms *might* collect -- a user can
always skip sq_m ("I don't know the size") or leave amenities unchecked.
See docs/PROGRESS.md for the Run C -> Run D rationale.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

PropertyType = Literal["apartment", "house", "bedsitter"]


class PredictRequest(BaseModel):
    bedrooms_num: int = Field(..., ge=0, le=20, description="0 = studio/bedsitter")
    bathrooms_num: int = Field(..., ge=0, le=20)
    location_std: str = Field(..., min_length=1, max_length=200)

    # Everything below is optional. None means "not provided" -- sq_m is
    # genuinely missing-aware (imputed by the trained pipeline, same as at
    # training time); the binary flags default to 0 (not furnished / no
    # amenity) since that's the only sensible reading of "not mentioned".
    sq_m: float | None = Field(None, ge=0, le=2000)
    is_furnished: int | None = Field(None, ge=0, le=1)
    property_type: PropertyType | None = None
    has_generator: int | None = Field(None, ge=0, le=1)
    has_borehole: int | None = Field(None, ge=0, le=1)
    has_cctv: int | None = Field(None, ge=0, le=1)
    has_dsq: int | None = Field(None, ge=0, le=1)
    has_play_area: int | None = Field(None, ge=0, le=1)
    has_garden: int | None = Field(None, ge=0, le=1)

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
    location_recognised: bool
    note: str


class LocationsResponse(BaseModel):
    locations: list[str]


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
