# Próximo avance medible — validar con datos externos, no con más simulación del mismo origen
**Registro de propuesta:** 23/11/2026. **Alcance:** Edge AI de WildfireSense, sin tocar el Random Forest V4 `rf-a288fc78989a`, la PR #7 Cloud ni la PR #8 de dos PC.

## Punto de partida verificable
- Track A permite **datos sintéticos o replay de datos reales**; Module 3, pp. 3–4. Exige 6 bloques lógicos, justificación de división Edge/Cloud y medidas de overhead, latencia, conectividad, cómputo. No exige desplegar 1000 radios reales.
- En el PC del equipo: **1.000 clientes independientes, 6.000/6.000 lecturas en 60 s (~100 msg/s), p95 de procesamiento 0,385 ms; p95 desde envío 2,108 ms**. Demuestra carga corta, no horas/días de disponibilidad ni fiabilidad radio. `fast_fire` publicó otras 47.981/47.981 desde **un** cliente simulador (~800 msg/s), con 9 `suspected_fire` y 1 SOS.
- Capacidad teórica para 1000 nodos × 1 lectura/10 s: **360.000 lecturas/h** o **8.640.000 lecturas/día**, pero el ensayo vigente duró un minuto.
- IA: RF 19 árboles, ocho características, seis clases, entrenado en escenarios sintéticos. Candidato con 7.634 nuevas muestras sintéticas rechazado por accuracy y demora; gate de validación controla promoción, **no certifica generalización**.
- Limitación prioritaria #11: 24/24 episodios negativos con aumento de PM global sintético disparan una alarma corroborada. PM temporal/temperatura no resolvieron el intercambio especificidad-sensibilidad; NO activar esas propuestas de la PR #12.

## Datos que ya existen (fuentes públicas verificadas, pero formatos aún sin auditar por filas)

| Dataset | Tipo y link | Qué sirve para comprobar | Qué NO se puede inferir |
|---|---|---|---|
| RESISTO, IREC, Doñana | Zenodo https://doi.org/10.5281/zenodo.14169469, CSV ~74,8 MB: tiempo, id, temp, RH, presión, localización, `fire_alert_status` | Distribución meteorológica espacial/temporal; calidad y faltantes | `fire_alert_status` es resultado de alerta de sensor, **no etiqueta independiente de ignición comprobada**; NO contiene PM ni CO entre columnas publicadas. PR #2 del proyecto usa temperatura real y PM/CO SINTÉTICOS. |
| EPA/USFS chamber study 2021 | Data.gov https://catalog.data.gov/dataset/chamber-study-2021-measurement-data, XLSX resolución 10 s | Transitorios y emisiones de combustión controlada de otro experimento, diseño temporal compatible | No representa un bosque ni cubre automáticamente los 4 inputs del V4; comprobar columnas/etiquetado antes del mapeo. |
| EPA/USFS cámara 2019–21 multigás | https://catalog.data.gov/dataset/2019_2021_chamber_study_burn_integrated_data y artículo https://doi.org/10.1080/10962247.2026.2629562 | Contrastar si CO o CO2 ayudan junto a PM bajo combustión controlada | La calibración y respuesta en laboratorio NO garantizan detección al aire libre ni justifican un nuevo sensor sin prueba. |
| EPA field PM during wildfire smoke | https://doi.org/10.23719/1518814 | PM de sensores económicos vs referencia bajo humo real; probar sesgo/corrección | Solo PM, no un benchmark binario fire/no-fire del clasificador V4 completo |
| EEA air quality station series | https://www.eea.europa.eu/en/datahub/datahubitem-view/datahubitem-view/778ef9f5-6293-4846-badd-56a29c70880d | Negativos OOD, PM elevado, polución de fondo, diversas regiones y fechas | Datos horarios/diarios no se convierten en simulación real de 10 s; periodos sin etiqueta no prueban ausencia de fuego |
| NASA FIRMS + NOAA HMS | https://firms.modaps.eosdis.nasa.gov/download/ ; https://www.ospo.noaa.gov/products/land/hms.html | Etiquetas auxiliares de hotspot / plumas de humo para seleccionar episodios/regiones | Son indicadores externos, con resolución y tiempo limitados; no se pueden tratar como verdad de ignición local instantánea |

## Experimento A (prioridad máxima; sin cambiar el detector)

1. **Auditar y documentar** dos fuentes reales: RESISTO y uno de los dos paquetes de la EPA. Guardar URL, licencia, hash, registros, unidad, fechas, resolución, porcentaje de faltantes y definición de etiqueta. No inventar columnas ausentes.
2. Crear adapter *solo si* están presentes `pm25, pm10, temperature, humidity, timestamp` con unidades válidas y orden causal; si no, usar el dataset en un experimento parcial (p. ej., PM calibration o distribución de temperatura), **no rellenar PM con humo simulado y llamarlo externo**.
3. Congelar el RF desplegado, separar ensayos por **incendio/sitio y fecha**, no mezclar muestras próximas del mismo episodio entre train/test. Registrar previamente qué condiciones se considerarán negativos para evitar fuga de etiquetas.
4. Métricas: falsas `suspected_fire` por 24 h/nodo (o nº de episodios negativos), sensibilidad y demora por evento de incendio **solo cuando exista verdad independiente**, detección antes de 5/15/30/60 min, PM sensor vs referencia, faltantes, ratio de muestras compatibles, y comparación RF vs reglas con idénticos datos.
5. **No** sustituir el RF hasta superar una puerta nueva bajo condiciones externas sin reoptimización con el test.

## Experimento B (carga reproducible de larga duración, 1000 clientes reales MQTT TCP)

No tratar 6000 como el límite máximo: 1000 nodos × 60 ciclos cada 10 s = **60.000 lecturas** y **10 min** de actividad, con idéntico ritmo nominal de 100 msg/s.

Desde `demos/edge1000-v4`, tras comprobar contenedores y límites:

```powershell
docker inspect wf-edge-final-edge-1 --format '{{.HostConfig.NanoCpus}} {{.HostConfig.Memory}} {{.State.OOMKilled}}'
docker compose -p wf-edge-final -f docker-compose.yml -f docker-compose.edge-limits.yml run --rm --no-deps -v "./resultados:/app/resultados" simulator python -m lab.mqtt_run --clients 1000 --nodes 1000 --cycles 60 --period 10 --speed 1 --scene normal --out /app/resultados/soak_1000_clientes_60k.json
```

Medir PDR, p95/p99 de procesado y envío→decisión, pico RSS, memoria residente Docker, CPU, OOM, SQLite (backlog y tamaño), mensajes/s y errores de conexión. **Cloud apagada** demuestra independencia Edge pero no reducción de tráfico Edge→Cloud ni recuperación de ACK; esto necesita prueba E2E aparte.

Luego se puede comparar 60k / 360k (una hora) y períodos de recuperación sin confundir una prueba acelerada con una de duración real.

## ¿Añadir CO₂ o CO?

**Decisión provisional: no incorporar ningún canal nuevo aún.** En el exterior humo puede dispersarse; CO₂ fluctúa con fondo atmosférico y no demuestra origen fuego. **CO (monóxido de carbono)** es una hipótesis más directamente asociada a combustión incompleta, aunque también tiene confusores (tráfico, vehículos, combustión no forestal) y sensores con consumo, deriva y necesidad de calibración. Artículos EPA/USFS 2026 y Holder 2020. Si hay conjunto de datos medido simultáneamente con PM + CO / CO₂ y etiquetas claras:
- entrenar *experimento separado* de ablation: `PM + temp + RH` vs `+CO` vs `+CO₂` (si existe);
- evaluar por **incendio** y por fondo no-fuego, y medir adicionalmente precio, vida de batería, consumo y coste MQTT por campo; solo incluir si la mejora supera ese coste.
- El modelo JSON V4 de ocho features no acepta cambios de entradas sin contrato, reentrenamiento, validación y nueva versión.

## Cierre para seguimiento semanal
Entregar **una ficha de procedencia de datos + un gráfico con métricas externas** (aunque demuestre fallo), y un **benchmark 60.000** con hardware y fecha. Se considera progreso si se descubre científicamente que el dato externo **no permite evaluar la tarea**, siempre que se documente la incompatibilidad y se decida cómo resolverla. La clase permite simulación; no fingir validación de incendios reales.
