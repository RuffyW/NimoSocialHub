FROM python:3.13.15-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 NIMO_DATA=/state
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg age ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini .
RUN groupadd -g 10001 nimo && useradd -u 10001 -g nimo -M nimo
USER 10001:10001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
