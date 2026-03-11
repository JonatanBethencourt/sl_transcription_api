# ---- Base image ----
FROM python:3.11-slim

# ---- System setup (faster, smaller builds) ----
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# ---- Install Python dependencies ----
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Copy app code ----
COPY . .

# (Optional) Create upload dir; app also does this at runtime
RUN mkdir -p /tmp/uploads

# ---- Expose the port Uvicorn will listen on ----
EXPOSE 8000

# ---- Start the FastAPI server ----
# If Railway sets a $PORT env var, Uvicorn will inherit our default (8000) unless overridden.
# Railway typically maps traffic to the exposed/used port automatically.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]