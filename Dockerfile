# One container for the whole site: the SvelteKit build served by the FastAPI app.
#   docker build -t resilinet . && docker run -p 8000:8000 resilinet
# Render (render.yaml) and Hugging Face Spaces build this file as is.

# ---- the site (frontend/web -> build/) ---------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/web/package.json frontend/web/package-lock.json ./
RUN npm ci
COPY frontend/web/ ./
# The CARTO basemap key is read at build time (see frontend/web/.env.example).
ARG VITE_CARTO_KEY=""
ENV VITE_CARTO_KEY=$VITE_CARTO_KEY
RUN npm run build

# ---- the API and the models ------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Runtime packages only: the Streamlit app and dev tools stay out of the image.
# The pins come from requirements.txt; xarray (seir/) and the server are added here.
COPY requirements.txt /tmp/requirements.txt
RUN grep -vE '^(streamlit|pydeck|pytest|ruff|psutil)\b' /tmp/requirements.txt > /tmp/runtime.txt \
    && pip install -r /tmp/runtime.txt "xarray>=2024.6" "fastapi>=0.110" "uvicorn>=0.29"

COPY . .
COPY --from=web /web/build frontend/web/build

# Run the historical backtest now so "Tested on real data" opens without a wait.
RUN PYTHONPATH=/app python scripts/run_backtest.py

# Free hosts have little memory: one worker process for ensembles unless raised.
ENV MAX_WORKERS=1 PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn main:app --app-dir frontend/api --host 0.0.0.0 --port ${PORT}"]
