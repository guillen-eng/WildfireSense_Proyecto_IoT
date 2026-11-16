# Contrato de telemetría MQTT v1 — propuesta para validar con el equipo

**Topics propuestos**
- Lecturas: wildfiresense/readings/{node_id}, MQTT QoS 0 para tráfico periódico.
- Alerta Edge: wildfiresense/edge/alerts, QoS 1 (al menos una vez; puede duplicarse).
- SOS: wildfiresense/events/sos, QoS 1, independiente del ML.

**JSON requerido:** schema_version=1, run_id, node_id, seq creciente por nodo/ejecución, type=reading, timestamp UTC de medición, emitted_at UTC de envío, timebase (simulated o wall), source, test_only=true y measurements con pm25_ug_m3, pm10_ug_m3, air_temperature_c, relative_humidity_pct.

- rx_ts se añade en Edge al recibir, no lo envía el sensor.
- Las coordenadas y vecindad están en nodes.csv separado por run_id, no se repiten en cada payload.
- Las etiquetas label, ground_truth, affected_by_fire, synthetic_event y similares NO viajan en MQTT hacia Edge AI.
- En replay acelerado, rx_ts - timestamp NO representa latencia real de red; emitted_at solo ayuda si hay sincronización documentada.
- Ver docs/examples/telemetry_v1.json para el ejemplo completo.
- Edge main.py/logic.py son baselines legados: el preprocesamiento de cuatro variables NO está conectado al servicio live.
