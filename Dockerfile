# P6: one image that runs the SilverFile staff dashboard, the CLI and the tests.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SILVERFILE_DB=/app/runtime/sessions.sqlite

WORKDIR /app

# Tesseract reads the W-2 images (P4 extraction); English data is included
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first so code changes don't reinstall them
COPY requirements.txt .
RUN python -m pip install -r requirements.txt

COPY . .
RUN chmod +x docker/entrypoint.sh && mkdir -p runtime

EXPOSE 8501
ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
