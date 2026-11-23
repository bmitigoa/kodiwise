"""KodiWise rent prediction API.

Serves Run D (ml.features.RUN_D_FEATURE_SET) -- bedrooms/bathrooms/location
plus the expanded-form fields (sq_m, furnished, property type, 6 amenity
flags) PredictionFormActivity and PropertyUploadActivity now collect. See
docs/PROGRESS.md for the Run C -> Run D rationale and the measured gain.

Run locally: uvicorn api.main:app --reload --port 8080
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from agent.core.errors import KodiWiseError
from api import areas as areas_mod

from api.predictor import Predictor
from api.schemas import HealthResponse, LocationsResponse, ModelVersionResponse, PredictRequest, PredictResponse

PRODUCTION_VERSION = "v20261123-appF"
predictor = Predictor(PRODUCTION_VERSION)


@asynccontextmanager
async def lifespan(app: FastAPI):
    predictor.load()
    yield


app = FastAPI(title="KodiWise Rent Prediction API", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        ok=True,
        model_loaded=predictor.loaded,
        model_version=predictor.version if predictor.loaded else None,
    )


@app.get("/model-version", response_model=ModelVersionResponse)
def model_version() -> ModelVersionResponse:
    if not predictor.loaded:
        raise HTTPException(status_code=503, detail="Model not loaded")
    m = predictor.metrics
    return ModelVersionResponse(
        version=m["version"],
        feature_set=m["feature_set"],
        trained_on=m["data_source"],
        n_train=m["n_train"],
        n_test=m["n_test"],
        test_r2=m["test_metrics"]["R2"],
        test_mape=m["test_metrics"]["MAPE"],
        note="Trained on bedrooms/bathrooms/location plus optional expanded-form fields -- see docs/PROGRESS.md.",
    )


@app.get("/locations", response_model=LocationsResponse)
def locations() -> LocationsResponse:
    if not predictor.loaded:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return LocationsResponse(locations=predictor.known_locations())


@app.post("/predict", response_model=PredictResponse, response_model_exclude_none=True)
def predict(req: PredictRequest) -> PredictResponse:
    if not predictor.loaded:
        raise HTTPException(status_code=503, detail="Model not loaded")
    result = predictor.predict(
        bedrooms_num=req.bedrooms_num,
        bathrooms_num=req.bathrooms_num,
        location_std=req.location_std,
        sq_m=req.sq_m,
        is_furnished=req.is_furnished,
        property_type=req.property_type,
        has_generator=req.has_generator,
        has_borehole=req.has_borehole,
        has_cctv=req.has_cctv,
        has_dsq=req.has_dsq,
        has_play_area=req.has_play_area,
        has_garden=req.has_garden,
        explain=req.explain,
    )
    return PredictResponse(**result)


class AreasRequest(BaseModel):
    budget_kes: float = Field(..., description="Monthly budget in KES")
    bedrooms: int = Field(..., ge=0, le=10)
    bathrooms: int = Field(..., ge=0, le=10)
    near: str | None = Field(None, max_length=100, description="Optional neighbourhood to stay close to")
    max_km: float = Field(5.0, ge=0.5, le=50, description="Straight-line distance from `near`, in km")
    sq_m: float | None = Field(None, ge=0, le=2000)


def _areas(req: AreasRequest) -> dict:
    if not predictor.loaded:
        raise HTTPException(status_code=503, detail="Model not loaded")
    try:
        return areas_mod.areas_within_budget(
            predictor, req.budget_kes, req.bedrooms, req.bathrooms,
            near=req.near, max_km=req.max_km, sq_m=req.sq_m)
    except KodiWiseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except areas_mod.Busy as exc:
        raise HTTPException(status_code=429, detail="Busy right now. Please try again in a few seconds.") from exc


@app.post("/areas-within-budget")
def areas_within_budget_post(req: AreasRequest) -> dict:
    """Areas whose estimated rent fits a budget, split into comfortable and stretch.
    Estimates only; same logic as the MCP areas_within_budget tool."""
    return _areas(req)


@app.get("/areas-within-budget")
def areas_within_budget_get(
    budget_kes: float, bedrooms: int = Query(..., ge=0, le=10), bathrooms: int = Query(..., ge=0, le=10),
    near: str | None = Query(None, max_length=100), max_km: float = Query(5.0, ge=0.5, le=50),
    sq_m: float | None = Query(None, ge=0, le=2000),
) -> dict:
    return _areas(AreasRequest(budget_kes=budget_kes, bedrooms=bedrooms, bathrooms=bathrooms,
                               near=near, max_km=max_km, sq_m=sq_m))
