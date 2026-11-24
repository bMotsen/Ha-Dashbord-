# Fast Python-image (nyere Home Assistant sender sit eget BUILD_FROM uden Python, så det bruges ikke)
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Europe/Copenhagen

WORKDIR /opt/dashboard
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY web ./web
COPY config.example.yaml run.py ./

CMD ["python", "/opt/dashboard/run.py"]
