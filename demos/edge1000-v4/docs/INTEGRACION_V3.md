# WildfireSense V3 — cambios de código y uso sin perder lo anterior

## Qué se ha implementado ahora

1. **Cloud: incidentes de incendio agrupados sin borrar alarmas originales.**
   - `cloud/incidents.py`: agrupación por `run_id`, celdas vecinas en malla 32×32, y un máximo experimental de 30 min entre señales vecinas.
   - `GET /api/incidents?limit=40`: número de incidentes agrupados, eventos corroborados y grupos.
   - `cloud/dashboard.html`: tarjeta y tabla de incidentes separadas del historial de avisos y de los SOS.
   - Evita fusionar ejecuciones `run_id` distintas. Para eventos antiguos sin `run_id`, no agrupa entre sí.
   - La agrupación se recalcula desde la base de datos de avisos, por lo que las alarmas originales y el mecanismo de acuse se mantienen.

2. **Evaluación temporal reproducible**: `python -m lab.early_detection`. Parte del CSV de episodios reservados, no reentrena y deja `resultados/deteccion_temprana.json`. Los horizontes de 5/15/30/60 min se miden desde el inicio de incendio sintético.

3. **Demostración reproducible**: `python -m lab.incident_demo` vuelve a evaluar los escenarios originales `fuego_lento`/`fuego_rapido` y muestra la reducción de mensajes a agrupaciones espaciales.

4. **Corrección ya validada por el usuario**: simulador MQTT con cierre seguro de Paho, sin `KeyError` por sockets liberados.

5. **Tests nuevos**: agrupación por zona, tiempo y run; API HTTP; persistencia y deduplicación; plazos de detección.

## Uso en Windows PowerShell 5.1 (en el directorio de V3)

```powershell
# Sin Docker: basta Python 3.12+ (sin librerías extras para estas dos demos)
python -m lab.demo
python -m lab.incident_demo
python -m lab.early_detection

# Con Docker; conservar el histórico SQLite en los volúmenes
# Si la versión antigua está activa en el mismo Compose, solo Cloud requiere reconstrucción
# para activar las nuevas vistas. También incluye el simulador corregido.
docker compose -f docker-compose.yml -f docker-compose.edge-limits.yml up -d --build mosquitto edge cloud

# Comprobar que la nueva API responde (desde navegador o PowerShell)
Invoke-RestMethod http://localhost:8090/api/incidents

# Guardar pruebas nuevas desde los mensajes del equipo
# (no se necesita borrar los volúmenes ya existentes)
docker compose -f docker-compose.yml -f docker-compose.edge-limits.yml run --rm simulator

# Tests Python en Docker: tests no se copia a la imagen base
# y se monta solo durante el ensayo
# Comando desde PowerShell en la raíz del proyecto:
docker compose -f docker-compose.yml -f docker-compose.edge-limits.yml run --rm --no-deps -v "./tests:/app/tests:ro" simulator python -m unittest discover -s /app/tests -v
```

**No ejecutar `docker compose down -v` si se desea conservar alarmas y estado.**

**Importante**: el ZIP V3 es una versión completa para desarrollar. NO descomprimir encima del anterior sin hacer copia de seguridad; trabajar en una carpeta separada. Si se desea aprovechar los históricos existentes, aplicar únicamente los ficheros modificados mediante el paquete `WildfireSense_V3_CAMBIOS.zip` en una copia y reconstruir Cloud.

## Limitaciones del agrupador

- Las distancias son de **celdas de la malla sintética**, NO metros ni coordenadas GPS.
- Dos focos vecinos simultáneos pueden agruparse incorrectamente; uno que se propaga con un gran salto puede dividirse.
- El identificador del grupo es determinista para un conjunto de eventos pero puede cambiar si llegan eventos antiguos y fusionan grupos; no usarlo como identificador estable de emergencias reales.
- El algoritmo lee avisos y calcula grupos en cada solicitud HTTP: adecuado para el prototipo, no para millones de alertas en producción.
- La clasificación 6 clases, sus umbrales, el SOS y los mensajes originales no se han modificado.

## Integración con GitHub

No sobrescribir `main`; usar una rama nueva desde el repositorio del equipo:

```powershell
git switch -c feature/edge-v3-incidentes
# Añadir V3 como PR, con revisión humana del código y pruebas.
git add cloud/ edge/ lab/ tests/ models/ docs/ README.md docker-compose.yml docker-compose.edge-limits.yml
# Evitar incluir state/, .venv/, volúmenes, datos privados o los bundles históricos de referencia.
```

Asegurar antes que la rama de integración contenga el árbol de Edge1000, dado que `main` público en la revisión anterior solo tenía datos y documentación. No se ha realizado ningún push ni merge desde esta entrega.

## Pruebas de robustez sin arriesgar la demo MQTT

```powershell
# Dentro de Docker, no cambia ni el broker ni el Edge en producción
# Captura resultados en ./resultados/robustez_sintetica.json

docker compose run --rm --no-deps -v "./resultados:/app/resultados" simulator python -m lab.robustness --file data/scenarios/fuego_rapido.jsonl --loss 0.05 --duplicates 0.02 --jitter-s 10 --seed 42
```

Se altera **el orden de llegada** de los mensajes sintéticos de forma determinista y se estudia cuántos llegan a ser aceptados por el motor causal. No se realizan fallos reales del broker ni se representa un canal radio. No modificar la inferencia crítica sin discutir el compromiso entre espera para reordenación y latencia de alerta.
