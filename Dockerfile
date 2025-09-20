FROM python:3.10.5-slim-bullseye

# Cache buster - change this value to force rebuild
ARG CACHEBUST=20241219v1
ENV CACHEBUST=${CACHEBUST}

WORKDIR /app

COPY requirements.txt .

RUN apt-get update && \
    apt-get install -y gcc && \
    pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY app/ .

RUN mkdir -p logs

EXPOSE 3002

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3002"]
