# kodiwise-chat image. Built from a staging folder made by infra/deploy_chat.ps1
# (chat/, agent/core/ and the neighbourhood centre points), not from the repo root.
FROM python:3.12-slim
WORKDIR /app
COPY chat/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY chat/ ./chat/
COPY agent/ ./agent/
COPY data/reference/neighbourhood_centroids.csv ./data/reference/
ENV PORT=8080
CMD exec uvicorn chat.main:app --host 0.0.0.0 --port ${PORT}
