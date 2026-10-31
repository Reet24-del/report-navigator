FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 OMP_THREAD_LIMIT=1
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt
COPY api ./api
COPY backend ./backend
COPY src ./src
COPY models ./models
RUN useradd --create-home --uid 1000 navigator && chown -R navigator:navigator /app
USER navigator
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-access-log"]
