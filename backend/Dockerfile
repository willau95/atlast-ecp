# ATLAST ECP Backend — Railway Deployment
# Rebuild forced: 2026-03-12

FROM python:3.12-slim

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Railway injects $PORT at runtime (default 8080).
# We read it via Python to avoid shell variable expansion issues.
ENV PORT=8080
EXPOSE 8080

# Entrypoint reads PORT from env — guaranteed to match Railway's routing
CMD python3 -c "import os, uvicorn; port=int(os.environ.get('PORT', 8080)); print(f'Starting on port {port}'); uvicorn.run('app.main:app', host='0.0.0.0', port=port, log_level='info')"
