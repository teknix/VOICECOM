FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY static/ ./static/

ENV PYTHONUNBUFFERED=1

CMD ["gunicorn", "--worker-class=gevent", "--workers=4", "--worker-connections=100", "--bind", "0.0.0.0:5000", "app:create_app()"]
