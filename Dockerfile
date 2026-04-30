FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    WEBSITES_PORT=8000 \
    CRICKETCLUBAPP_DATA_ROOT=/home/site/cricketclubapp \
    CRICKETCLUBAPP_SEED_FILE=/home/site/cricketclubapp/seed.json \
    CRICKETCLUBAPP_DATABASE_FILE=/home/site/cricketclubapp/cricketclubapp.db \
    CRICKETCLUBAPP_CACHE_FILE=/home/site/cricketclubapp/store_cache.json \
    CRICKETCLUBAPP_DASHBOARD_CACHE_FILE=/home/site/cricketclubapp/dashboard_cache.json \
    CRICKETCLUBAPP_UPLOAD_DIR=/home/site/cricketclubapp/uploads \
    CRICKETCLUBAPP_DUPLICATE_DIR=/home/site/cricketclubapp/duplicates

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app/app
COPY tools /app/tools
COPY README.md /app/README.md

RUN mkdir -p /home/site/cricketclubapp/uploads /home/site/cricketclubapp/duplicates

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
