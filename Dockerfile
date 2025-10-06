FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY server.py memory_store.py /app/
EXPOSE 8787
CMD ["uvicorn","server:app","--host","0.0.0.0","--port","8787"]
