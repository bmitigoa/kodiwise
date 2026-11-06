"""KodiWise rent prediction API.

Serves Run D (ml.features.RUN_D_FEATURE_SET) -- bedrooms/bathrooms/location
plus the expanded-form fields (sq_m, furnished, property type, 6 amenity
flags) PredictionFormActivity and PropertyUploadActivity now collect. See
docs/PROGRESS.md for the Run C -> Run D rationale and the measured gain.

Run locally: uvicorn api.main:app --reload --port 8080
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from api.predictor import Predictor
from api.schemas import HealthResponse, ModelVersionResponse, PredictRequest, PredictResponse

PRODUCTION_VERSION = "v20261106-appD"
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


@app.post("/predict", response_model=PredictResponse)
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
    )
    return PredictResponse(**result)
