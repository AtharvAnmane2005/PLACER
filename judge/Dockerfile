FROM python:3.12-slim

# Node.js is the JavaScript runtime; Python is the image's own interpreter.
# Both are required by the shared runner.
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 judge

WORKDIR /srv
COPY judge/requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt

# The judge reuses the backend's runner and models — one implementation of
# grading, not a second sandbox. Only the modules that runner actually imports
# are copied, so the image does not carry the backend's ML model artifacts.
COPY backend/app/__init__.py /srv/app/__init__.py
COPY backend/app/core/__init__.py /srv/app/core/__init__.py
COPY backend/app/core/config.py /srv/app/core/config.py
COPY backend/app/models/__init__.py /srv/app/models/__init__.py
COPY backend/app/models/base.py /srv/app/models/base.py
COPY backend/app/models/assessment.py /srv/app/models/assessment.py
COPY backend/app/services/__init__.py /srv/app/services/__init__.py
COPY backend/app/services/code_execution_service.py /srv/app/services/code_execution_service.py
COPY judge/app.py /srv/judge_app.py

ENV PYTHONPATH=/srv \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    CODE_EXECUTION_BACKEND=local \
    CODE_EXECUTION_ENABLED=true \
    CODE_EXECUTION_TIMEOUT_SECONDS=3 \
    CODE_EXECUTION_TOTAL_TIMEOUT_SECONDS=20 \
    CODE_EXECUTION_MAX_CODE_BYTES=20000 \
    CODE_EXECUTION_MAX_OUTPUT_BYTES=100000 \
    CODE_EXECUTION_MAX_TEST_CASES=20

USER judge
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=3)"

CMD ["uvicorn", "judge_app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
