FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "paho-mqtt>=2.0,<3"
COPY edge/cusum.py /app/cusum.py
COPY shadow/shadow_monitor.py /app/shadow_monitor.py
COPY shadow/tests/ /app/tests/
ENV PYTHONUNBUFFERED=1
CMD ["python", "shadow_monitor.py"]
