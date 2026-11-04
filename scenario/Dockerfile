FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY runner.py evaluate.py config.json config_normal.json ./
COPY configs/ ./configs/
COPY data/ ./data/
COPY tests/ ./tests/
COPY tools/ ./tools/
ENV PYTHONUNBUFFERED=1
CMD ["python", "runner.py"]
