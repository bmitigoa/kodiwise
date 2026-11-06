"""KodiWise rent prediction API.

Serves Run C (ml.features.APP_FEATURE_SET) -- the model trained on only
bedrooms/bathrooms/location, matching exactly what PredictionFormActivity
collects. See docs/PROGRESS.md for why Run B (the higher-benchmark but
unservable model) was not shipped here.

Run locally: uvicorn api.main:app --reload --port 8080
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from api.predictor import Predictor
from api.schemas import HealthResponse, ModelVersionResponse, PredictRequest, PredictResponse

PRODUCTION_VERSION = "v20261106-appC"
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
        note="Trained on bedrooms/bathrooms/location only -- see docs/PROGRESS.md.",
    )


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> PredictResponse:
    if not predictor.loaded:
        raise HTTPException(status_code=503, detail="Model not loaded")
    result = predictor.predict(req.bedrooms_num, req.bathrooms_num, req.location_std)
    return PredictResponse(**result)
