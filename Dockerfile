# api/ container image. Must live at the repo root (not api/Dockerfile) --
# gcloud run deploy --source only auto-detects a Dockerfile at the root of
# the given source path, and this needs the repo root as build context
# anyway, to COPY both api/ and ml/ (siblings, not nested).
#
# Local build:   docker build -t kodiwise-api .
# Cloud deploy:  gcloud run deploy kodiwise-api --source=. ...  (see docs/PROGRESS.md)
FROM python:3.12-slim

# LightGBM needs libgomp at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only what the API needs at runtime: the api/ package, ml/features.py
# (the single source of truth for feature construction, shared with
# training), and the one versioned model directory currently served.
COPY api/ ./api/
COPY ml/__init__.py ml/features.py ./ml/
COPY ml/models/v20261107-appD/ ./ml/models/v20261107-appD/

# Cloud Run sets PORT; default to 8080 for local runs.
ENV PORT=8080
CMD exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT}
