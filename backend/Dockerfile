FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

EXPOSE 8000

# Shell form: allows $PORT environment variable to be expanded at runtime
# Railway injects $PORT automatically; fallback to 8000 for local dev
CMD ["python3", "-c", "import os,uvicorn; uvicorn.run('app.main:app', host='0.0.0.0', port=int(os.environ.get('PORT',8000)), log_level='info')"]
