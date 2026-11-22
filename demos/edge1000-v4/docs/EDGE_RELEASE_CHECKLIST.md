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
- [ ] Clonar esta rama en una **carpeta nueva**, evitando mezclar volúmenes y puertos con demos anteriores.
- [ ] Verificar `docker compose ... config --quiet`, construcción `simulator` y todos los tests unitarios.
- [ ] Iniciar solo Mosquitto + Edge con 0,5 CPU/512 MiB (Cloud no necesaria para aceptación Edge).
- [ ] Enviar 1.000 clientes independientes / 6.000 lecturas; conservar salida completa y `PDR`, p95 y p99, CPU/RAM y `OOMKilled`; realizar **2 repeticiones** sin reiniciar el modelo.
- [ ] Enviar datos de un escenario de incendio sintético, verificar `environmental_risk` y `suspected_fire` (con vecino).
- [ ] Activar B2 **solo en instancia de ensayo aislada**, verificar `unconfirmed_fire_risk` y SOS sin Cloud, reiniciar modo V4 tras el ensayo. Nunca afirmar que ese aviso está corroborado.
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
