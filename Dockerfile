FROM python:3.10.5-slim-bullseye

WORKDIR /app

COPY requirements.txt .

RUN apt-get update && \
    apt-get install -y gcc && \
    pip install --upgrade pip && \
    pip install -r requirements.txt

COPY app/ .

RUN mkdir -p logs

EXPOSE 3002

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3002"]
