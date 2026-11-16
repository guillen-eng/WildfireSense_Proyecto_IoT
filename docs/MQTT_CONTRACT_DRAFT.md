# WildfireSense — Contrato MQTT v1 (BORRADOR)

> **Estado: propuesta para revisión entre Sensor Simulator y Edge AI.** Ningún productor/consumidor actual está obligado todavía a cumplir este formato. No fusionar sin adaptar y probar ambos extremos.
>
> Basado en la PR #1 (`setup/import-current-prototype`) y en la arquitectura acordada: PM2.5, PM10, temperatura y humedad. La PR #2 usa CO en lugar de PM10; esa diferencia está PENDIENTE de resolución técnica y no debe ocultarse.

## 1. Topics propuestos

| Flujo | Topic | QoS propuesto | Emisor → receptor |
| --- | --- | ---: | --- |
| Telemetría ordinaria | `wildfiresense/readings/{node_id}` | 0 | Simulador → broker → Edge |
| Avisos de Edge | `wildfiresense/edge/alerts` | 1 | Edge → broker → Cloud |
| SOS de prueba | `wildfiresense/events/sos` | 1 | Publicador autorizado → Edge |
| Versiones de modelo (futuro) | `wildfiresense/models/updates` | 1 | Cloud → Edge (NO implementado) |

**Justificación:** preservar topics ya usados por el prototipo de la PR #1. La prueba reciente con `wildfire/nodes/{id}/telemetry` debe adaptarse mediante un *adapter* o renombrarse en el simulador, no silenciarse ni considerarse ya integrado.

MQTT QoS 1 = entrega al menos una vez en el salto MQTT; admite duplicados y no prueba que Edge o Cloud hayan persistido/procesado el mensaje. Para alertas usar `alert_id` estable, deduplicación y seguimiento de recepción. El suscriptor y el publicador deben solicitar QoS compatibles. QoS 0 para telemetría es una decisión experimental, no una garantía de fiabilidad.

## 2. Mensaje de telemetría propuesto

`docs/examples/telemetry_v1.json` contiene un ejemplo completo.

| Campo | Tipo / semántica |
| --- | --- |
| `schema_version` | entero fijo `1` |
| `run_id` | identificador de experimento; ayuda a separar reinicios y secuencias |
| `node_id` | identificador del sensor, mismo que el sufijo del topic |
| `seq` | entero >= 0, creciente **por (run_id,node_id)** |
| `type` | `reading` |
| `timestamp` | instante de **medición**, ISO 8601 UTC |
| `emitted_at` | instante UTC del **envío real** del simulador |
| `timebase` | `simulated` o `wall`, según la escala temporal |
| `source` | origen/procedencia del generador |
| `test_only` | `true` en todos los mensajes sintéticos de laboratorio |
| `measurements.pm25_ug_m3` | PM2.5 en µg/m³, número finito >= 0 |
| `measurements.pm10_ug_m3` | PM10 en µg/m³, número finito >= 0 |
| `measurements.air_temperature_c` | temperatura del aire en °C, número finito |
| `measurements.relative_humidity_pct` | humedad relativa en %, entre 0 y 100 |

No poner `ground_truth`, `fire`, `affected_by_fire`, `event_start` ni etiquetas de clase en un mensaje consumido por Edge AI. Guardarlas en archivos de evaluación separados. Si hay sensores ausentes/fallidos, registrar explícitamente la calidad o el valor ausente en una extensión de esquema (no inventar mediciones normales).

La ubicación de los nodos (`x_m`, `y_m`, mapa/CRS) se conserva preferiblemente en un catálogo de nodos por `run_id`, evitando retransmitirla en cada medida. La distribución espacial y el modelo de propagación no están definidos por este contrato.

## 3. Recepción y métricas de tiempo

**El Edge añade** `rx_ts` UTC al recibir cada mensaje (no es un campo generado por el sensor). También debe guardar `run_id`, `node_id` y `seq` para detectar saltos, duplicados y lecturas fuera de orden.

No calcular latencia real de red mediante `rx_ts - timestamp` cuando `timestamp` es tiempo virtual o el replay está acelerado. Para medición extremo a extremo en tiempo real, contrastar `rx_ts` con `emitted_at` solo si los relojes de emisor/receptor están sincronizados y documentados. Dentro de un mismo proceso usar reloj monotónico para procesamiento. Separar: tiempo de simulación, tiempo de transporte, tiempo de inferencia y retraso desde ignición sintética hasta alerta.

## 4. Contrato de alerta (propuesta mínima)

Topic `wildfiresense/edge/alerts`, QoS 1, JSON con:
`schema_version=1`, `alert_id` estable y único, `type=environmental_alert`, `node_id`, `run_id`, `generated_at` UTC, `priority`, `detector_version`, `reason`, `test_only=true`, referencia a la lectura/ventana (`seq` o rango de secuencias) y, cuando proceda, `edge_processing_ms`.

La PR #1 ya usa parte de estos campos y un hash para deduplicación Cloud; **esto es una evolución propuesta**, no la estructura actualmente implementada. Las modificaciones de Edge y Cloud se harán en PR separadas con tests de compatibilidad.

## 5. Tareas y criterios para aprobar v1

1. **Simulador:** generar 100 y 1000 nodos con formato estable, reproducibilidad por semilla, `seq` y `run_id`. Preservar PM10; CO será opcional en una extensión futura previa decisión del equipo.
2. **Edge:** validar JSON, límites y unidades; registrar `rx_ts`, mensaje inválido, duplicado y secuencia faltante; no usar etiquetas de escenario durante inferencia.
3. **MQTT:** capturar y comparar publicados/recibidos en un experimento controlado con 100 nodos y otro con 1000; declarar sus QoS y fallos emulados, **no** asumir que PUBACK significa procesamiento en Edge.
4. **ML:** consumir el mismo contrato documentado; registrar versión de modelo, umbrales y métricas, sin introducir cambios incompatibles silenciosos.
5. **Cloud:** almacenar alertas con deduplicación; histórico de series, reentrenamiento y actualizaciones versionadas son pendientes del Track A.
6. **Pruebas:** ejemplo JSON parseable, tests unitarios por componente y un test E2E que confirme el conteo en el **suscriptor**, no solo los publishes.

## 6. Migración desde formatos actuales

| Componente | Estado PR #1 / pruebas locales | Adaptación pendiente |
| --- | --- | --- |
| `simulator/simulator.py` | `wildfiresense/readings/{sensor}`; solo temperatura y humedad | Cuatro variables, metadatos y secuencia |
| `loadlab/run.py` | `wildfiresense/readings/{sensor}`; temp/RH/PM2.5/CO | PM10, contrato v1, metadatos/tiempo; preservar procedencia RESISTO |
| Simulador v0.1 probado en Windows **fuera de GitHub** | `wildfire/nodes/{id}/telemetry`, `id`, `ts`, PM2.5/PM10/temp/RH | Topic, esquema y adaptador; no reemplazar código sin revisar |
| `edge/main.py`, `edge/logic.py` | topic anterior `wildfiresense/readings/#`; Z-score univariante con campo predeterminado `sensible_heat_flux` | Validación multivariable e interfaz de IA; conservar baseline como referencia |
| `cloud/app.py` | guarda alertas en SQLite local | Contrato de alerta versionado, histórico/Cloud AI en iteraciones posteriores |

**Decisiones abiertas:** cadencia temporal definitiva, coordenadas/CRS, tamaño de red, fallos de sensores y si CO se agrega como quinta variable. Registrar decisiones en PR antes de cambiar consumidores.
