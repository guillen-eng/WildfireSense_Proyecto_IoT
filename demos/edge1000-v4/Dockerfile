FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY vendor/ vendor/
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --no-index -r requirements.txt
COPY edge/ edge/
COPY cloud/ cloud/
COPY lab/ lab/
COPY models/ models/
COPY data/ data/
CMD ["python","-m","edge.main"]

FROM runtime AS training
RUN python -m pip install --no-cache-dir -r lab/requirements-train.txt
CMD ["python","-m","lab.train","--output","/exchange/candidate.json"]
