# Build from the repo root so this can COPY both api/ and ml/:
#   docker build -f api/Dockerfile -t kodiwise-api .
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
COPY ml/models/v20261106-appC/ ./ml/models/v20261106-appC/

# Cloud Run sets PORT; default to 8080 for local runs.
ENV PORT=8080
CMD exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT}
