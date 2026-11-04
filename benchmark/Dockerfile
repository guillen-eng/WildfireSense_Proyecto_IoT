FROM python:3.12-slim
WORKDIR /app
# Banco de pruebas exclusivamente offline; no instala MQTT.
COPY edge/logic.py edge/cusum.py ./
COPY edge/tests/ ./tests/
COPY benchmark/tests/ ./tests/
COPY benchmark/compare_detectors.py benchmark/sweep_cusum.py benchmark/evaluate_shadow.py benchmark/traffic_report.py benchmark/diagnose_drift.py benchmark/audit_alignment.py ./
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "compare_detectors.py"]
