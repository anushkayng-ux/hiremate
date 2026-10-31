# HireMate in one container (Render, Hugging Face Spaces, any Docker host).
# FastAPI runs inside on 8000; Streamlit is the public app on $PORT (Render sets it; default 7860).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data API_URL=http://127.0.0.1:8000 HOME=/app \
    VECTOR_STORE=memory EMBEDDER=hashing

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data && chmod -R 777 /app/data && chmod +x start.sh

EXPOSE 7860
CMD ["./start.sh"]
