FROM python:3.11-slim
RUN apt-get update && apt-get install -y libzbar0 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "main.py"]