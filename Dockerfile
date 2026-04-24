FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    WEBSITES_PORT=8000 \
    HEARTLAKE_DATA_ROOT=/home/site/heartlake \
    HEARTLAKE_SEED_FILE=/home/site/heartlake/seed.json \
    HEARTLAKE_DATABASE_FILE=/home/site/heartlake/heartlake.db \
    HEARTLAKE_CACHE_FILE=/home/site/heartlake/store_cache.json \
    HEARTLAKE_DASHBOARD_CACHE_FILE=/home/site/heartlake/dashboard_cache.json \
    HEARTLAKE_UPLOAD_DIR=/home/site/heartlake/uploads \
    HEARTLAKE_DUPLICATE_DIR=/home/site/heartlake/duplicates

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app/app
COPY tools /app/tools
COPY README.md /app/README.md

RUN mkdir -p /home/site/heartlake/uploads /home/site/heartlake/duplicates

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
