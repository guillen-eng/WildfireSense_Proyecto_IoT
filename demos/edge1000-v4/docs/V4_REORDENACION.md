# WildfireSense V4 — Mensajes retrasados y reordenación experimental

## Problema observado en V3

`Engine.evaluate()` exige secuencias y tiempos crecientes por nodo. Rechaza mensajes antiguos y duplicados para proteger la causalidad del filtro y evitar duplicar avisos. Con retardos aleatorios grandes, mensajes legítimos pueden recibirse después de otros más nuevos y perderse para la inferencia.

Esto **no es un error de MQTT**: se simula alterando el orden de entrega de tramas JSONL offline. La capa MQTT no necesita garantizar un orden global entre distintos emisores.

## Qué implementa V4

`edge/reorder.py` ofrece `BoundedEventBuffer`: heap ordenado por tiempo de evento, ventana de lateness experimental y máximo de elementos. El SOS entregado **no se bufferiza**. Los mensajes que llegan después del watermark pueden seguir rechazándose. Se contabilizan el máximo de mensajes retenidos y los vaciados forzosos por capacidad.

**Muy importante: el buffer NO está conectado por defecto a `edge/main.py`.** No hemos cambiado los umbrales ni la latencia de la detección crítica en producción. Antes de activarlo en vivo hay que diseñar un temporizador de vaciado para nodos silenciosos, sincronización de relojes, manejo de reconexiones y pruebas bajo límite de recursos. `finish()` solo simula el final de un fichero cerrado.

## Datos medidos reproducibles

Archivo `data/scenarios/fuego_rapido.jsonl` (40.740 mensajes originales), semilla 42; pérdida independiente 5 %, duplicados 2 % y retardo uniforme de hasta 10 s:

| Configuración | Tramas entregadas | Aceptadas por el motor | Rechazadas, incl. duplicados | Primera sospecha disponible desde t0 |
|---|---:|---:|---:|---:|
| V3 sin reordenar | 39.474 | 34.055 | 5.419 | 238,93 s |
| Buffer experimental 12 s | 39.474 | 38.732 | 742 | 234,09 s |

En **este caso concreto**, el primer aviso resultó disponible 4,84 s antes porque el filtro recibió más información útil. **Eso no significa que el buffer siempre reduzca la latencia**: almacenar lecturas hasta un watermark introduce espera y puede retrasar avisos; cada configuración de red, frecuencia y tiempo de ignición cambia el resultado. El SOS no entra en la cola.

Con retardo de hasta 90 s, V3 aceptó 12.259 de 39.474 tramas, mientras que una ventana experimental de 95 s aceptó 38.732 (con pico de 587 mensajes en el buffer). **No recomendaríamos activar una espera de 95 s en el detector**; es solo una cota diagnóstica offline.

Para comparar en tu ordenador sin tocar los servicios activos:

```powershell
# Con la imagen de V4 ya reconstruida y los límites de recursos del Edge activos
# Muestra comparación sin/ con buffer; guarda archivo en el directorio resultados

docker compose run --rm --no-deps -v "./resultados:/app/resultados" simulator python -m lab.compare_reorder --jitter-s 10 --window-s 12
```

No se deben confundir:

- `delivery/PDR`: qué llegó al broker/Edge. No es lo mismo que `accepted_readings`, que excluye duplicados y tramas tardías.
- `first_alarm_available_delay_s`: tiempo del escenario cuando la decisión llega a estar disponible (estimación offline a partir del orden simulado). No es latencia de transmisión de una red real.
- `suspected_fire_delay_s`: tiempo del evento de lectura, que no incluye espera adicional del buffer.

## Requisitos previos para activar buffer en el gateway

1. Acordar latencia máxima admisible por tipo de emergencia y nunca retardar un SOS.
2. Sincronizar relojes de nodo/Edge y detectar relojes adelantados; manejar `boot_id` y duplicados.
3. Garantizar vaciado por inactividad y límite de memoria del buffer, sin perder mensajes pendientes.
4. Repetir pruebas con el límite Edge 0,5 CPU/512 MiB y distintas cadencias, pérdidas y cortes.
5. Comparar detección a 5/15/30 min, falsos episodios y retardos p95/p99; hacer rollback rápido si empeora.

## Fuentes

- [Apache Flink: tiempo de evento y watermarks](https://nightlies.apache.org/flink/flink-docs-stable/docs/concepts/time/) — referencia conceptual; **no se usa Apache Flink**.
- [Eclipse Mosquitto: niveles de QoS de MQTT](https://mosquitto.org/man/mqtt-7.html).
- Material docente, *Module 3 — Project Guidelines*, Track A, pp. 3–4.
