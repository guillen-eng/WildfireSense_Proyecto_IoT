# WildfireSense — base mínima para Edge AI

**Estado:** prototipo académico. No detecta incendios reales. Esta rama es una propuesta **no integrada** mientras se comprueba Docker y se entregan los escenarios del equipo.

## Estructura activa

- `mosquitto/` y `docker-compose.yml`: MQTT en local (solo desarrollo).
- `simulator/simulator.py`: tráfico MQTT de demostración, **no datos para entrenar**.
- `edge/main.py`, `edge/logic.py`: Edge y Z-score existentes **sin cambiar su código**; `edge/cusum.py` sirve de baseline alternativo.
- `edge/features.py`: extracción **causal** de 18 características sobre PM2.5, PM10, temperatura y humedad por sensor.
- `ml/build_features.py`: une mensajes JSONL con etiquetas externas por `(run_id,node_id,seq)`; no publica etiquetas en MQTT.
- `ml/train_random_forest.py`: entrenamiento y evaluación separados por grupos de episodios.
- `docs/MQTT_CONTRACT.md`, `docs/SCENARIO_HANDOFF.md`: interfaz que debe cumplir el generador del compañero.

`scenario/`, `loadlab/`, `shadow/`, `benchmark/`, `cloud/` y los resultados históricos siguen en las ramas/PR previas; se dejan fuera de **esta propuesta minimalista** para no mezclar desarrollos ni borrar historial. La Cloud se reintegrará como PR propia.

## Primera prueba con PowerShell, desde la raíz del repositorio

```powershell
docker compose -f docker-compose.yml -f docker-compose.edge.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.edge.yml --profile simulacion up -d --build
docker compose -f docker-compose.yml -f docker-compose.edge.yml logs --tail 60 edge simulator
```

En esta fase **el detector oficial sigue siendo Z-score sobre temperatura** (configurado en Compose). `features.py` **no se ha conectado a `main.py`**, y no hay modelo ML desplegado. Un log de lecturas no demuestra detección validada.

Para ver mensajes:

```powershell
docker compose -f docker-compose.yml -f docker-compose.edge.yml exec mosquitto mosquitto_sub -h localhost -t 'wildfiresense/readings/#' -C 3 -v
```

Pruebas unitarias del Edge y las features:

```powershell
docker compose -f docker-compose.yml -f docker-compose.edge.yml run --rm --no-deps --build --entrypoint python edge -m unittest discover -s tests -v
```

Parar sin destruir datos:

```powershell
docker compose -f docker-compose.yml -f docker-compose.edge.yml --profile simulacion stop
```

## Preparación Python para IA (sin Docker)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r ml\requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s ml\tests -v
```

El entrenamiento **no se ejecuta hasta recibir etiquetas reales del simulador**, con grupos y particiones separadas, según `docs/SCENARIO_HANDOFF.md`.

Cuando se entreguen `readings.jsonl` (solo telemetría) y `truth.csv` (etiquetas externas):

```powershell
.\.venv\Scripts\python.exe -m ml.build_features --readings data/readings.jsonl --truth data/truth.csv --output ml/data/labeled_features.csv
.\.venv\Scripts\python.exe -m ml.train_random_forest --dataset ml/data/labeled_features.csv
```

El modelo se guarda en `edge/models/` y sus métricas en `ml/results/` **solo localmente**. No subir artefactos de modelo, datasets grandes ni resultados experimentales sin revisión; el reporte preliminar no valida incendios reales.

## Colaboración

Todo cambio mediante ramas y pull requests. El compañero de escenarios trabajará sobre el contrato MQTT y entregará ficheros etiquetados **sin insertar etiquetas en el payload**. El chat de IA puede trabajar ya en `edge/features.py` y `ml/`; las integraciones con MQTT, inferencia live y Cloud serán PR separadas con tests.