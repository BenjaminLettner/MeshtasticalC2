FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV MINIC2_PORT=/dev/ttyACM0 \
    MINIC2_CHANNEL=1 \
    MINIC2_TIMEOUT=20

CMD ["python", "app/minic2.py"]
