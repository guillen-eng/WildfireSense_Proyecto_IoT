# WildfireSense — HANDOFF Edge AI (22 noviembre 2026)

**Rama:** `feature/edge-ai-evidence-freeze` → [PR #9](https://github.com/guillen-eng/WildfireSense_Proyecto_IoT/pull/9), **borrador sin fusionar**. Se basa en `feature/edge1000-v4-integration` → PR #6. `main` no contiene aún este código.

**Límite de responsabilidad:** algoritmo de Edge, inferencia local, política de avisos y evaluación. No sustituir la Cloud de otros compañeros ni fusionar la rama de dos ordenadores (PR #8) sin revisión. La UI Cloud necesita distinguir el nuevo aviso no corroborado: [Issue #10](https://github.com/guillen-eng/WildfireSense_Proyecto_IoT/issues/10).

## Qué está terminado y qué está validado

| Requisito | Implementación | Evidencia |
| --- | --- | --- |
| Random Forest ligero en Edge | `models/forest.json` 19 árboles, 8 features, 6 clases, `rf-a288fc78989a`; inferencia portátil sin sklearn | Tests, modelo intacto respecto V4 |
| Seguridad de contrato IoT | JSON versionado, id/secuencia, orden causal, filtro de medidas, rechazo etiquetas de verdad | `edge/contract.py`, `tests/test_edge.py` |
| SOS independiente | Evento crítico sin esperar ML, vecinos ni Cloud | `tests/test_edge.py`, `tests/test_isolated_escalation.py` |
| Detección habitual | Score >=0.65, PM2.5 rápido >=18, fracción fina >=0.36, persistencia 30 s, evidencia vecina <=180 s | `edge/logic.py`, `docs/AI_THRESHOLDS.md`, episodio sintético |
| Reglas B2 opcionales en nodo aislado | `unconfirmed_fire_risk` (high pero `confirmation=unconfirmed`); nunca confundir con `suspected_fire` | `docs/POLITICA_B_NODO_AISLADO.md`, pruebas sintéticas selladas, tests unitarios |
| Modelo inalterado al comparar umbrales | `DetectionPolicy` parametrizable, sin entrenar ni promover pesos | `lab/threshold_sensitivity.py`, `lab/isolated_policy_study.py` |
| Realismo y límites | Benchmark interno por episodio; OOD sintético: PM alto, humedad, lectura sesgada, mezcla gruesa | `docs/RESULTADOS_EDGE_AI_20261122.md`, `docs/POLITICA_B_SELLADO_Y_B2.md` |
| MQTT a 1.000 clientes con recursos | 6.000/6.000 lecturas, PDR observado 1,0, Edge 0,5 CPU/512 MiB, B2 activado sin Cloud | [CI Docker y MQTT B2 45048746292](https://github.com/guillen-eng/WildfireSense_Proyecto_IoT/actions/runs/45048746292), no prueba radio física |

## Política B: qué se ha decidido y por qué

- El equipo eligió **estudiar un escalado condicionado** cuando no hay vecinos sanos recientes. Por diseño, no se puede inventar una corroboración.
- B1 (score >=0.8, subida PM >=8, persistencia 120 s, tendencia temperatura >=0) se rechazó con nuevos datos: **6/48 episodios negativos con contaminación alta produjeron alerta de prioridad alta**. No se ocultó el fallo.
- B2 mantiene score >=0.8, PM rápido - PM lento >=8 µg/m³ y persistencia >=120 s; exige además **temperatura rápida - temperatura lenta >=0.5 °C** y ausencia de vecinos sanos recientes. **Todos son umbrales experimentales**, no una norma de incendios.
- B2, probado **una sola vez** con semillas nuevas 801–812 tras prefijarlo: 11/24 episodios de fuego aislado reconocidos, 0/48 negativos normales, 0/48 negativos con fondo PM alto y 0 avisos anteriores a ignición. Con humedad alta detectó 5/24, con PM2.5 30 % inframedido 1/24, y con mezcla gruesa 0/24. **Limitación importante: baja sensibilidad bajo condiciones adversas.**
- B2 superó un gate **solo para demo sintética limitada**, no implica sensibilidad de campo ni seguridad operacional. Se mantendrá **desactivado por defecto** para reproducir V4. Su activación opcional debe ser consciente y mostrarse en `wildfiresense/edge/status`.

**Fuente científica del criterio general:** medidas de PM para humo pueden seguir tendencias, pero no prueban ignición por sí solas, los sensores ópticos están sujetos a sesgos de humedad/calibración y un único nodo no demuestra causa. Ver *Module 3 – Project Guidelines* pp. 2–4, *Module 1 – IoT Part II* pp. 20–22 y 28–33; Holder et al. (2020) https://doi.org/10.3390/s20174796; EPA (2026) https://www.epa.gov/system/files/documents/2026-06/air-quality-sensors-for-smoke-factsheet.pdf. Ninguna fuente prescribe nuestros cortes numéricos: se defienden como hipótesis ensayadas.

## Cómo reproducir sin sobrescribir el prototipo estable (Windows PowerShell)

```powershell
git clone --branch feature/edge-ai-evidence-freeze https://github.com/guillen-eng/WildfireSense_Proyecto_IoT.git WildfireSense_EDGE_AI
cd WildfireSense_EDGE_AI\demos\edge1000-v4

# Construcción de la imagen y tests; no hace falta Python instalado en Windows.
docker compose -p wf-edge-ai build simulator
docker compose -p wf-edge-ai run --rm --no-deps -v "./tests:/app/tests:ro" simulator python -m unittest discover -s /app/tests -v

# Base V4: NO se activa la política B2.
docker compose -p wf-edge-ai -f docker-compose.yml -f docker-compose.edge-limits.yml up -d --build mosquitto edge

# B2 opcional: primero parar el Edge de la prueba, luego usar el override.
docker compose -p wf-edge-ai -f docker-compose.yml -f docker-compose.edge-limits.yml -f docker-compose.edge-b2.yml up -d --build edge
docker compose -p wf-edge-ai -f docker-compose.yml -f docker-compose.edge-limits.yml -f docker-compose.edge-b2.yml exec mosquitto mosquitto_sub -h 127.0.0.1 -t wildfiresense/edge/status -C 1
# Buscar isolated_escalation_enabled = true
```

**No usar `docker compose down -v` con histórico de un proyecto anterior.** No mezclar dos proyectos Compose apuntando al mismo puerto MQTT 1883. La opción B2 se probó con `lab.b2_mqtt_probe` vía MQTT: [CI #45048746292](https://github.com/guillen-eng/WildfireSense_Proyecto_IoT/actions/runs/45048746292) verde, aunque pendiente de repetir en los portátiles físicos.

## Qué queda y en qué orden

1. **HECHO en CI:** [MQTT real con B2 y SOS](https://github.com/guillen-eng/WildfireSense_Proyecto_IoT/actions/runs/45048746292). Publicadas 143 lecturas sintéticas de un nodo: `environmental_risk` → `unconfirmed_fire_risk` de prioridad alta/no corroborada → `sos_alert` crítico, **sin** fabricar `suspected_fire` y con Cloud desconectada. Conservar el artefacto JSON y repetir el ensayo en Docker Desktop del equipo.
2. Repetir Docker con el hardware de entrega y, cuando se reúna el equipo, en las **dos máquinas** acordadas con la profesora. Registrar CPU/RAM, MQTT p95/p99, desconexión, cola, sincronización de reloj.
3. Integrar PR #9 mediante revisión de compañeros sin perder PR #7 Cloud; Issue #10 para distinguir `unconfirmed_fire_risk` en el panel.
4. Documentar limitación de generalización: todos los resultados de detección son del mismo simulador o perturbaciones derivadas. Para estimar eficacia con incendios reales hay que obtener observaciones externas con etiquetas y sensores calibrados.
5. Completar el informe de 8–12 páginas y defensa, citando qué es implementado/probado y qué es solamente experimental.

**No se deben hacer más ajustes de los umbrales en esta entrega usando las mismas semillas**. Cualquier cambio futuro requiere nueva hipótesis, nueva validación de desarrollo, ensayo ciego adicional y aprobación del equipo.

## Anexo — Issue P0 de fondo PM elevado (22/11/2026)

La [PR #12](https://github.com/guillen-eng/WildfireSense_Proyecto_IoT/pull/12) (sobre la PR #9) documenta dos ensayos **sin mejora aprobada**; fichero principal `docs/CIERRE_P0_CONTAMINACION_FONDO.md`.

- El escenario sintético adversarial de PM global elevado genera **24/24** falsos `suspected_fire` en la baseline V4 (semillas nuevas 901–906 y 921–926).
- Exigir subida de PM en ambos nodos dejó **3/24** falsos, pero solo **7/12** incendios reconocidos.
- Exigir además tendencia de temperatura eliminó las 24 falsas sospechas en el conjunto de desarrollo para el corte fuerte, pero redujo a **6/12** las detecciones originales.
- Ningún candidato superó las reglas preestablecidas; **no hubo test sellado** y no se debe presentar como problema solucionado.
- Se ha bloqueado la activación accidental en Gateway: `EDGE_CORROBORATION_TREND_GATE=1` produce error explícito. La inyección experimental sigue permitida solo en el motor offline.
- La PR #12 debe permanecer sin fusionar mientras solo documenta un estudio y una política fallida; la línea V4 y B2 de PR #9 permanecen inalteradas por defecto.
- Siguiente tarea real: diseñar validación con datos externos y/o instrumentación adicional. No ajustar más umbrales con estas mismas escenas para fabricar un resultado de éxito.

**Conclusión para defensa:** sensores de partículas pueden detectar anomalías compatibles con humo, pero no permiten identificar la causa de todas las subidas ambientales; un segundo sensor con fondo alto compartido no elimina la ambigüedad.
