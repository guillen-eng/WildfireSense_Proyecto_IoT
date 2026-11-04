# Decisión de datos v1 — RESISTO como referencia + escenarios sintéticos

**Estado:** implementación experimental en rama separada. No modifica ni elimina el simulador de escenarios ni la versión anterior de LoadLab. **No es una simulación física calibrada de incendios.**

## 1. Qué parte es real y cuál es sintética

| Campo | Procedencia del nuevo modo RESISTO | Límite de interpretación |
|---|---|---|
| Temperatura (°C) | Primeros 5 nodos: las 5 series de temperatura del CSV RESISTO, 72 lecturas por sensor; valores históricos en escenario normal | Si se inyecta evento, el incremento es sintético |
| Humedad (%) | Generada sintéticamente a partir de una hipótesis de tendencia inversa con temperatura | El CSV contiene pocas lecturas válidas de humedad; **no se imputa ni calibra a partir de ellas** |
| PM2.5 (µg/m³) | Generada sintéticamente | No hay mediciones PM2.5 en estos CSV |
| CO (ppm) | Generada sintéticamente | No hay mediciones CO en estos CSV |
| Identidad/tiempo | Se conservan `source_sensor` y `source_time` originales; `timestamp` representa reloj **virtual** | No se afirma alineamiento real de series entre sensores |
| Etiqueta del escenario | Archivo local separado `ground_truth.json` | Describe inyección artificial, **no un incendio real** |

Con `--nodes 50`, `100` o `500`, los nodos adicionales reutilizan plantillas de las mismas cinco series originales con variaciones sintéticas deterministas. No son sensores reales adicionales ni observaciones independientes.

La decisión se basa en la falta de datos multivariables históricos suficientemente completos. Este compromiso sirve para evaluar **software y arquitectura IoT**, no para medir la sensibilidad ante incendios forestales.

## 2. Qué hemos añadido

- `loadlab/historical.py`: lector de las 5 series, auditoría del CSV mediante SHA-256, generación de temperatura anclada e identificación explícita de variables sintéticas.
- `loadlab/run.py`: nuevos parámetros `--baseline resisto` y `--historical-csv`, sin cambiar el comportamiento predeterminado `--baseline synthetic`.
- `docker-compose.loadlab.yml`: montaje de `scenario/data/` **solo lectura**.
- `loadlab/Dockerfile`: incluye el nuevo módulo.
- `loadlab/tests/test_historical.py`: tests de trazabilidad, determinismo, exportación offline y separación de etiquetas.

La etiqueta de evento está **fuera de MQTT**; en el mensaje se marca únicamente `test_only` y la procedencia de cada medida mediante `measurement_provenance`.

## 3. Cómo probarlo desde la raíz del repositorio

Primero, con Docker Desktop abierto, **sin levantar broker, Edge ni Cloud**:

```powershell
docker compose -f docker-compose.yml -f docker-compose.loadlab.yml --profile carga run --rm --no-deps --build --entrypoint python loadlab -m unittest discover -s tests -v
```

Generar 5 nodos normales a partir de RESISTO, **offline**:

```powershell
docker compose -f docker-compose.yml -f docker-compose.loadlab.yml --profile carga run --rm --no-deps --build loadlab --baseline resisto --nodes 5 --mode normal --no-pace
```

Generar escenario mixto con 50 nodos virtuales:

```powershell
docker compose -f docker-compose.yml -f docker-compose.loadlab.yml --profile carga run --rm --no-deps --build loadlab --baseline resisto --nodes 50 --mode mixed_proxy --no-pace
```

Para ensayos de escala usar `--nodes 100` o `--nodes 500`; no son pruebas de carga MQTT cuando se omite `--publish`.

**No añadas todavía `--publish`.** Publicar requiere broker y un ensayo separado de recepción Edge, latencia y mensajes perdidos. PUBACK de MQTT QoS 1 no demuestra que el Edge haya procesado una lectura.

## 4. Evidencias guardadas por ejecución

Cada ejecución crea una carpeta propia en `loadlab/results/`:

- `readings.jsonl`: mensajes generados y procedencia de las variables.
- `historical_audit.json`: hash del archivo fuente, número de sensores, disponibilidad de humedad, límites de temperatura y advertencia de timestamps no alineados.
- `ground_truth.json`: qué nodos recibieron una perturbación y cuándo; archivo **solo de evaluación**.
- `config_used.json`: semilla, configuración, `baseline` y hash histórico.
- `summary.json`: mensajes/bytes, detecciones de **la regla experimental offline**, y `mqtt_delivery_to_edge_verified: false`.

## 5. Qué no hemos probado todavía

1. No se ha ejecutado este modo en Docker Desktop de los cuatro compañeros.
2. No se ha integrado con MQTT/Edge/Cloud ni confirmado recepción de 500 nodos.
3. No se han calibrado humedad, PM2.5 y CO con mediciones reales.
4. No se ha entrenado ML con particiones independientes por sesión de datos.
5. No se ha medido precisión frente a incendios reales: las etiquetas son de inyecciones.

## 6. Qué falta para cumplir el Track A de Bea

- Acordar contrato MQTT v1 (incluyendo `schema_version`, ID, variables, unidades y frecuencia).
- Documentar fuentes, calidad y uso del dataset original. Con humedad escasa, una línea base multivariable necesita fuentes externas o se declara sintética.
- Entrenar un modelo ligero sobre escenarios con separación por **series y semillas**, inferencia real en Edge sin Cloud y comparación con Z-score/CUSUM.
- Histórico y reentrenamiento Cloud con actualización versionada de modelo.
- Medir MQTT (payload + overhead), tasa de mensajes, latencia, CPU/RAM, ancho de banda y diferencias entre Edge y Cloud.
- Preparar experimentos reproducibles y reportar falsas alarmas, retraso y límites.

## 7. Interpretación del experimento

Los modos `normal`, `mixed_proxy`, `smoke_proxy`, `heat_proxy` y `dust_control` son **escenarios de prueba de software**. Los umbrales en `loadlab/config.json` son experimentales y **no deben describirse como umbrales físicos validados de incendio**. El detector `ExperimentalFusion` dentro de LoadLab es independiente del Edge oficial, que ahora usa Z-score.

**Referencias internas:** `scenario/data/holdout_manifest.json`, `scenario/data/resisto_sample.csv`, `loadlab/config.json` y *Module 3 — Project guidelines*, Track A.
