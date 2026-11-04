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


## Regularización temporal v2: solución para huecos históricos

El CSV RESISTO tiene sellos temporales reales **irregulares**. Por ejemplo, `replay_004` incluye una lectura de 30 °C y otra de 19 °C separadas por **121,9 minutos**: no deben aparecer como dos mediciones consecutivas separadas por 120 segundos.

El nuevo `loadlab/timegrid.py` aplica, por sensor:

1. Ordenar los timestamps originales y rechazar fechas ambiguas (sin zona horaria) o duplicadas.
2. Separar **segmentos continuos** donde ningún intervalo supere los **300 segundos**. El valor es un límite metodológico provisional, **no calibrado físicamente**.
3. Escoger el segmento más largo por duración; establecer su comienzo como origen local del reloj virtual de cada sensor.
4. Crear puntos cada 120 segundos: un valor es `observed` si coincide exactamente con una observación, `interpolated` si está entre dos observaciones del segmento, y `synthetic_extension` si queda fuera de él.
5. La extensión posterior se simula con una variación de paso limitada y semilla fija. **No es una predicción meteorológica ni un modelo físico de incendios**.
6. Mantener `reference_temperature_origin`, `reference_grid_time` y `reference_source_times` en los mensajes. Para interpolaciones, conservar ambos tiempos fuente; para extensión sintética, lista vacía y `source_time: null`.
7. Registrar el resumen en `historical_audit.json`, `config_used.json` y `summary.json`.

**Auditoría del CSV de noviembre con los parámetros actuales (5 sensores × 72 pasos):** de las **360 posiciones virtuales**, 5 coinciden exactamente con una observación, 70 son interpolaciones y **285 son extensión sintética**. Esta clasificación se refiere a la cuadrícula virtual, **no** niega que el CSV de entrada tenga 360 temperaturas observadas con timestamps irregulares.

La fecha del mensaje `timestamp` es el reloj virtual de LoadLab, no la fecha histórica `reference_grid_time`. Las cuadrículas de distintos sensores **no están sincronizadas con una fecha absoluta común**: utilizamos el inicio del segmento elegido por sensor. Por eso no se puede inferir correlación histórica espacial ni coincidencia real entre sensores de estos resultados.

**Impacto observado en pruebas locales offline:** el escenario térmico pasó de 1/2 a 2/2 detecciones en esta configuración, manteniendo umbrales. Este resultado **no** prueba mayor exactitud frente a incendios reales; sólo cambia el comportamiento bajo la señal sintética temporalmente regularizada. Debe mantenerse la evaluación separada por series/semillas y reportarse el alto porcentaje de extensión sintética.

**Compatibilidad:** el modo por defecto `--baseline synthetic` no se modifica; `--baseline resisto` aplica la cuadrícula v2. El detector de LoadLab sigue siendo **experimental e independiente del Edge oficial** y la ejecución offline no verifica entregas MQTT.

Para probar:

```powershell
docker compose -f docker-compose.yml -f docker-compose.loadlab.yml --profile carga run --rm --no-deps --build --entrypoint python loadlab -m unittest discover -s tests -v
docker compose -f docker-compose.yml -f docker-compose.loadlab.yml --profile carga run --rm --no-deps --build loadlab --baseline resisto --nodes 5 --mode heat_proxy --no-pace
```

Inspeccionar en `loadlab/results/<run_id>/historical_audit.json` → `temperature_point_origins`. Es crucial distinguir las **5 posiciones observadas** de las 70 interpoladas y las 285 extensiones sintéticas antes de presentar conclusiones a Bea.

