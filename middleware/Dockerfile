FROM python:3.11-slim

WORKDIR /app

# ffmpeg is required by pydub for MP3 → WAV conversion
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run injects $PORT at runtime; gunicorn binds to it
CMD exec gunicorn \
    --bind "0.0.0.0:${PORT:-8080}" \
    --workers 1 \
    --threads 8 \
    --timeout 120 \
    app:app
