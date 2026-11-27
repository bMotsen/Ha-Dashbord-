# Fast Python-image (nyere Home Assistant sender sit eget BUILD_FROM uden Python, så det bruges ikke)
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Europe/Copenhagen

WORKDIR /opt/dashboard
COPY requirements.txt .
RUN pip install -r requirements.txt
# valgfrit: VW's officielle dataportal (hvis installationen fejler, virker resten stadig)
RUN pip install "carconnectivity-connector-vw-eu-data-act>=0.3" || echo "vw_eu_data_act ikke installeret"

COPY app ./app
COPY web ./web
COPY config.example.yaml run.py ./

CMD ["python", "/opt/dashboard/run.py"]
