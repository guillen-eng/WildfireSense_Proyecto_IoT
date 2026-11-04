FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "paho-mqtt>=2.0,<3"
COPY config.json generator.py historical.py timegrid.py rules.py run.py ./
COPY tests/ ./tests/
ENTRYPOINT ["python", "run.py"]
