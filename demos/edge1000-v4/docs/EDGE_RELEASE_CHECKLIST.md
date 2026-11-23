# Checklist final — entrega del módulo Edge + IA (WildfireSense)
**Fecha:** 2026-11-22 | **Rama base:** `feature/edge-ai-evidence-freeze` (PR #9, todavía abierta) | **Alcance:** Edge, no Cloud.

## Decisiones congeladas
- [x] Random Forest `rf-a288fc78989a` (19 árboles, 8 features, 6 clases), sin reentrenar.
- [x] Política V4 original por defecto (`EDGE_ISOLATED_ESCALATION=0`): preaviso persistente 30 s y `suspected_fire` solo con vecino sano.
- [x] SOS independiente; Cloud desconectada no impide clasificación ni alerta local.
- [x] B2 experimental, optativa, *no corroborada*, separada del evento de incendio `suspected_fire`. La evidencia de detección es **solo sintética**.
- [x] Análisis documentado de 24/24 falsos `suspected_fire` en escenario adversarial con PM ambiental elevado. Dos candidatos de mitigación evaluados y rechazados: **no desplegar** ni fusionar como solución (PR #12 e issue #11).
- [x] Umbrales distinguidos por procedencia: norma AQI para referencia PM2.5 35,5 μg/m³ *de 24 h*, hipótesis y valores empíricos para el resto; **no es límite oficial de ignición**.

## Evidencias ya verificadas en CI
- [x] PR #9: tests de regresión y script de sensibilidad.
- [x] B2: prueba MQTT E2E con secuencia de un nodo, `unconfirmed_fire_risk` y SOS crítico con Cloud ausente: https://github.com/guillen-eng/WildfireSense_Proyecto_IoT/actions/runs/45048746292.
- [x] Detector V4 activo y filtros de fondo rechazados: **71 tests OK**, 1.000 clientes MQTT independientes, 6.000/6.000 lecturas, PDR 1,0, Edge limitado a 0,5 CPU/512 MiB, OOM false; p95 de procesamiento 0,149 ms y envío-a-decisión 0,603 ms **en el runner CI**: https://github.com/guillen-eng/WildfireSense_Proyecto_IoT/actions/runs/45051185130.
- [x] Resultados de sensibilidad y robustez sintética, incluidos los fallos, explicados en `docs/AI_THRESHOLDS.md`, `docs/POLITICA_B_NODO_AISLADO.md`, `docs/CIERRE_P0_CONTAMINACION_FONDO.md`.

## P0: aceptación en el portátil de entrega (pendiente)
- [x] Clonada rama en **carpeta nueva** `WildfireSense_EDGE_FINAL`, proyecto Compose `wf-edge-final`, sin borrar volúmenes anteriores (ejecución local comunicada por el usuario).
- [x] Build y 64/64 tests unitarios en Docker local, 5,980 s. La ejecución independiente de `config --quiet` no está confirmada por registro.
- [x] Mosquitto healthy y Edge running sin Cloud; overlay de límites CPU/RAM aplicado en comando Compose (confirmar límites efectivos con `docker inspect`).
- [ ] Primera repetición **completada** con 1.000 clientes, 6.000/6.000 y PDR 1,0; falta segunda repetición, `docker inspect` de los límites y OOM. Salida local `resultados/prueba_edge_1000.json`.
- [x] `fast_fire`: 47.981/47.981, 9 `environmental_risk`, 9 `suspected_fire` con vecino y SOS 1/1 (salida local `resultados/prueba_edge_incendio.json`).
- [x] B2 en Edge local: `node_0804`, 143 lecturas, `environmental_risk` → `unconfirmed_fire_risk` con `confirmation=unconfirmed` → SOS crítico; restablecido modo V4 y comprobado `isolated_escalation_enabled=false` (salida local `resultados/prueba_edge_B2.json`).
- [ ] Documentar hardware, Docker/OS, versión de modelo, fecha y comandos. No usar `docker compose down -v` si necesitas conservar SQLite.

### Pasos Windows PowerShell para empezar (sin Python instalado)
```powershell
git clone --branch feature/edge-ai-evidence-freeze https://github.com/guillen-eng/WildfireSense_Proyecto_IoT.git WildfireSense_EDGE_FINAL
cd WildfireSense_EDGE_FINAL\demos\edge1000-v4
docker compose -p wf-edge-final -f docker-compose.yml -f docker-compose.edge-limits.yml config --quiet
docker compose -p wf-edge-final build simulator
docker compose -p wf-edge-final run --rm --no-deps -v "./tests:/app/tests:ro" simulator python -m unittest discover -s /app/tests -v
```
**Advertencia:** antes de arrancar `up`, revisar que no estén ocupados los puertos 1883/8090 de una demo anterior. Este proyecto Compose tiene nombre y volúmenes propios, pero conserva los mismos puertos de host definidos en el YAML.

## P1: documentación y defensa
- [ ] Exportar tabla única con resultados **de CI y del equipo** sin mezclar latencia de red entre dos portátiles con latencia de inferencia local.
- [ ] Tabla ML vs. detector por reglas, recuerdo por episodio antes de 5/15/30/60 min, falsas sospechas en normales y estrés, junto con limitaciones del generador compartido.
- [ ] Explicar 1 cliente publicando 1.000 sensores vs. 1.000 clientes MQTT, y coste de CPU/RAM/latencia.
- [ ] Evidencia de robustez con pérdida/duplicados/reordenación **solo donde se midió**, y comportamiento de SOS.
- [ ] Comparación cualitativa Edge vs. Cloud en bytes, RTT y offloading; coordinar con compañero Cloud para medir la topología física.
- [ ] Revisar PR #9 → PR #6 → PR #1 con el equipo; documentar contribuciones y versión única de entrega.
- [ ] Informe 8–12 páginas y diapositivas; pruebas sobre dos ordenadores físicos acordadas con la profesora, pero Cloud fuera de esta línea.

**Alcance honesto:** prototipo de anomalías compatibles con humo. No detección forestal validada en campo; las cifras de sensibilidad son de simulación.

## Criterio de "Edge listo"
Modelo/umbrales congelados, todos los tests verdes, demo de 1.000 clientes y SOS repetida en portátil de entrega, resultados archivable y PR revisada por equipo. El falso positivo de PM ambiental elevado **debe figurar como limitación conocida**, no como problema resuelto.

## Evidencia local comunicada por el equipo (22/11/2026)

**Procedencia:** salidas de PowerShell pegadas en la conversación y ficheros JSON locales del usuario. No se han subido a GitHub ni revisado los bytes de los archivos; **no presentarlos como nueva ejecución CI**.

| Ensayo | Lecturas/estado | Latencia y memoria |
| --- | --- | --- |
| 1.000 clientes MQTT independientes, normal, 10 s/lectura, 60 s | 6.000/6.000 (PDR 1,0), 1.000 nodos, 0 huecos/rechazos | p95 procesamiento 0,385 ms; p99 0,539 ms; p95 envío→decisión 2,108 ms; p99 23,085 ms; RSS pico Linux Edge 34.084 KiB |
| `fast_fire` con 1 cliente emitiendo 1.000 nodos × 48 ciclos, speed ×8 | 47.981/47.981, PDR 1,0; 9 preavisos, 9 sospechas con vecino y SOS 1/1; Cloud ausente | p95 procesamiento 0,279 ms, p99 0,463 ms; p95 envío→decisión 10,312 ms, p99 18,549 ms (ventana de 50.000 eventos, **no sólo segunda prueba**); RSS pico 39.720 KiB |
| B2 experimental en MQTT | 143 lecturas de `node_0804`; preaviso `environmental_risk`, alarma `unconfirmed_fire_risk` (no corroborada), `sos_alert` crítico | Confirmado desde el informe JSON del usuario; restaurado V4 con bandera B2 apagada |
| Robustez offline, referencia, `fuego_rapido.jsonl` | 40.740 lecturas aceptadas, 0 descartes, primer aviso a 216,46 s | Retraso disponibilidad primer aviso 216,46 s |
| Robustez offline, 5 % pérdida, 2 % duplicados, jitter 10 s | 2.008 pérdidas simuladas, 742 copias, 34.055 aceptadas, 5.419 rechazadas, 6.675 huecos | Primera sospecha según lectura 233,82 s; disponible a 238,93 s |
| Misma perturbación + buffer experimental de 15 s | **38.732** aceptadas (exactamente 40.740−2.008), 742 rechazadas, 2.003 huecos | Primera sospecha según lectura 221,46 s; disponible a 237,65 s |

**Interpretación estricta:** buffer recuperó 4.677 lecturas válidas reordenadas y descartó las 742 copias extra. El primer aviso disponible mejoró 1,28 s respecto al ensayo degradado, pero aún llegó 21,19 s después de la referencia limpia. Las cifras de sospechas por nodo (41,39,42) **no son tasas de incendios verdaderos**. Las pruebas offline no emitieron SOS; SOS MQTT sí se verificó por separado. La implementación `edge/reorder.py` **NO está conectada** al gateway vivo: resultado de investigación, no mejora desplegada. No se ha probado memoria, CPU o latencia del buffer en producción.

**Próximo cierre:** repetir 1.000 clientes una vez más, comprobar `OOMKilled` y límites Docker reales, guardar JSON y capturas/versiones de hardware/OS; después revisar la PR #9 para integración.
