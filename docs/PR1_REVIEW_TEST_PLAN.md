# PR #1 — Plan de revisión, limpieza y validación (sin fusionar)

> **Ámbito:** rama `setup/import-current-prototype`, PR #1 hacia `main`. Este documento forma parte de una PR **apilada sobre la #1**, de revisión, y no cambia código de producción. La PR #2 se basa en la PR #1 y debe revalidarse tras cualquier integración.
>
> **Estado de pruebas:** inspección estática del código y comandos; **no se han ejecutado los tests ni Docker desde esta revisión de GitHub**. No dar por superada ninguna prueba sin adjuntar su salida.

## 1. Inventario y limpieza segura

- PR #1 incluye `simulator/`, `scenario/`, `loadlab/`, `edge/`, `shadow/`, `cloud/`, `benchmark/` y varios Docker Compose. **No eliminar ni sobrescribir ninguno** mientras se discute el simulador definitivo y la IA.
- La ruta versionada `scenario/results - copia/` contiene trazas, resúmenes, logs y salidas de evaluaciones anteriores. Son **artefactos de experimentos** que conviene apartar del código activo; **no se eliminan en esta PR** hasta verificar referencias desde tests/informes y decidir qué evidencias deben preservarse.
- `edge/logic_backup.py` está duplicado en apariencia. No borrarlo sin comparar contenido, dependencias y utilidad histórica.
- `.gitignore` debe prevenir nuevos `scenario/results - copia/`, `outputs/`, archivos temporales y entornos locales. Un `.gitignore` **no desversiona** archivos que ya estén en Git.
- Cuando se autorice retirar los resultados históricos: hacer una **PR separada**, con un manifiesto de archivos, referencia al commit antiguo y/o copias de resultados seleccionados para el informe. El historial Git conserva las versiones originales.
- No introducir el ZIP descargado del nuevo simulador completo dentro de la carpeta del repositorio sin adaptar rutas y dependencias.

## 2. Comprobar el entorno (PowerShell desde la raíz del repositorio)

```powershell
git status --short
git branch --show-current
docker --version
docker compose version
docker info
docker compose -f docker-compose.yml -f docker-compose.edge.yml -f docker-compose.cloud.yml config --quiet
```

Si se está trabajando en otra carpeta que contiene otro `docker-compose.yml`, cambiar a la raíz del **clone del repositorio** antes de ejecutar pruebas. Comprobar que no hay otros brokers con el puerto 1883 o dashboards con el 8090 ocupados.

## 3. Pruebas unitarias de la PR #1 (Docker; ejecutar y guardar el resultado)

```powershell
# Edge
docker compose -f docker-compose.yml -f docker-compose.edge.yml run --rm --no-deps --build --entrypoint python edge -m unittest discover -s tests -v

# Cloud local
docker compose -f docker-compose.yml -f docker-compose.cloud.yml run --rm --no-deps --build --entrypoint python cloud -m unittest discover -s tests -v

# Escenarios
docker compose -f docker-compose.yml -f docker-compose.scenario.yml --profile escenario run --rm --no-deps --build --entrypoint python scenario -m unittest discover -s tests -v

# Generador experimental LoadLab (PR #1: modo anterior, sin RESISTO v2)
docker compose -f docker-compose.yml -f docker-compose.loadlab.yml --profile carga run --rm --no-deps --build --entrypoint python loadlab -m unittest discover -s tests -v

# Shadow
docker compose -f docker-compose.yml -f docker-compose.shadow.yml --profile shadow run --rm --no-deps --build --entrypoint python edge-shadow -m unittest discover -s tests -v

# Benchmark
docker compose -f docker-compose.yml -f docker-compose.benchmark.yml --profile benchmark run --rm --no-deps --build --entrypoint python benchmark -m unittest discover -s tests -v
```

Las pruebas Shadow y Benchmark son **comandos propuestos a partir de sus Dockerfiles**, todavía no verificados en Windows. Registrar suites ejecutadas, número de tests, errores y commit SHA. No extrapolar pruebas unitarias a robustez ante incendios reales.

## 4. Smoke test de integración de la PR #1 (solo laboratorio local)

```powershell
docker compose -f docker-compose.yml -f docker-compose.edge.yml -f docker-compose.cloud.yml up -d --build mosquitto edge cloud
docker compose -f docker-compose.yml -f docker-compose.edge.yml -f docker-compose.cloud.yml ps
Invoke-RestMethod "http://127.0.0.1:8090/api/health"
docker compose -f docker-compose.yml -f docker-compose.edge.yml -f docker-compose.cloud.yml logs --tail 80 edge cloud
```

Con broker y servicios comprobados, revisar el script `PRUEBA_INTEGRACION.ps1` y ejecutarlo manualmente en ambiente de prueba:

```powershell
.\PRUEBA_INTEGRACION.ps1
```

Ese script publica un SOS sintético, comprueba su recepción mediante el API Cloud y reinicia el Cloud para verificar persistencia. No valida el detector ambiental ni el nuevo simulador. **No** ejecutar sobre una base de datos con resultados que no deban alterarse. Guardar logs antes y después.

Para detener sin borrar volúmenes/datos:
```powershell
docker compose -f docker-compose.yml -f docker-compose.edge.yml -f docker-compose.cloud.yml stop mosquitto edge cloud
```

No usar `down -v` ni `docker system prune` sin plan de copia de seguridad.

## 5. Prueba y contrato entre simulador y Edge (PENDIENTE de implementación)

- Revisar `docs/MQTT_CONTRACT_DRAFT.md` y `docs/examples/telemetry_v1.json`; este contrato NO está implementado.
- La prueba reciente de 100 nodos por `wildfire/nodes/{id}/telemetry` demuestra que **un suscriptor vio mensajes**, no que el Edge de la PR #1 los haya procesado.
- Introducir adaptador o migrar producers/consumers al contrato seleccionado, sin cambiar la interfaz pública silenciosamente.
- Pruebas de aceptación: (a) parseo JSON correcto, (b) rechazo de negativos/no finitos/IDs no válidos, (c) `seq` monotónico por sensor/ejecución, (d) deduplicación QoS 1, (e) 100/1000 sensores sin fuga de etiquetas, (f) registro de `rx_ts`, (g) contar mensajes **en receptor**, (h) alarma aun sin Cloud, (i) restauración tras reconexión.
- Evaluación de la IA: particiones independientes por escenario/semilla/foco de ignición, no por filas aleatorias del mismo episodio, y métricas FPR/FNR/latencia de detección.

## 6. PR #2 y coordinación entre chats

- PR #2 (`feature/resisto-anchored-simulation`) **depende de #1**; no rebasarla ni fusionarla antes de resolver dependencias, adaptar el contrato y repetir pruebas de su rama.
- Chat Simulador/MQTT trabaja en `feature/simulator-spatial-v2` desde una base integrada verificada.
- Chat Edge AI trabaja en `feature/edge-ai-detector` desde **esa misma base**. Ninguna de esas ramas debe crearse sobre `main` vacío mientras #1 siga sin fusionar.
- Ambos chats comparten exclusivamente contratos y casos de prueba versionados; no trabajan a la vez sobre `edge/main.py` ni `docker-compose.yml` sin coordinarse por PR.
- Mantener `main` estable, revisar cada PR, dejar evidencia del resultado de tests y hacer merge solo después.

## 7. Checklist para dar por revisada PR #1

- [ ] Tests Edge, Cloud, Scenario, LoadLab, Shadow y Benchmark ejecutados con commit SHA registrado.
- [ ] `docker compose config --quiet` y servicios levantados desde un clone limpio.
- [ ] Smoke test MQTT → Edge → Cloud/SQLite → API validado.
- [ ] Limpieza de artefactos históricos evaluada sin perder evidencia/reproducibilidad.
- [ ] Contrato de mensajes elegido y plan de migración acordado con el chat de IA.
- [ ] PR #2 revalidada tras los cambios en su base.
- [ ] Aprobación del equipo antes de fusionar #1 en `main`.

**La aceptación del prototipo IoT no equivale a validación científica de detección de incendios reales.**
