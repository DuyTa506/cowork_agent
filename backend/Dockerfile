FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

# LibreOffice draws Word files as PDF pages for the viewer (app/services/preview.py); Liberation fonts are metric-compatible with
# Times New Roman and Arial, so lines break where they do in Word. Without it the viewer falls back to the extracted text.
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-writer fonts-liberation fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
COPY requirements.txt ./requirements.txt
COPY wheels /wheels
RUN pip install --upgrade pip && pip install --find-links /wheels -r requirements.txt
COPY app ./app
RUN mkdir -p /data/uploads /data/tmp && chown -R appuser:appgroup /app /data
USER appuser
EXPOSE 8000
# The same image runs the API (default) and the worker: `python -m app.worker`.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
