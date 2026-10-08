FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app:/shared
COPY services/tuition/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared /shared
COPY services/tuition/app ./app
EXPOSE 8002
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
