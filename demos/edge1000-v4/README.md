# WildfireSense V4 · Edge + Cloud AI con validación de modelos

**Novedades V4 (20/11/2026):** puerta de validación para reentrenamiento (modelo candidato vs modelo desplegado, sin sobrescrituras por defecto); generador de observaciones etiquetadas **solo sintéticas** para demostrar ese circuito; buffer de reordenación **solo experimental y offline**. El motor Edge crítico, el SOS y el archivo `models/forest.json` mantienen la versión probada. Lee `docs/V4_VALIDACION_MODELOS.md` y `docs/V4_REORDENACION.md` antes de desplegar un candidato.

**Estado de la integración (22/11/2026):** V4 dispone de ensayos previos con Docker Desktop y 1.000 clientes MQTT documentados en `resultados/ensayos_docker_20261120.json`; la rama Edge IA está sometida a CI con pruebas de regresión y ensayos de umbrales. La implementación definitiva en los dos portátiles físicos continúa pendiente. No ejecutar `docker compose down -v` si necesitas conservar el histórico.

## Estado de Edge AI y política B2 experimental (22/11/2026)

El Random Forest oficial sigue siendo **`rf-a288fc78989a`**; clasificación local, alarmas corroboradas por vecino y SOS conservan el comportamiento original con `EDGE_ISOLATED_ESCALATION=0` (valor predeterminado). La nueva política para nodos sin vecinos está **implementada y validada solo en simulación**; no altera la versión base hasta activarla expresamente en la demo:

```powershell
# Modo B2 opcional para evaluación académica: nunca aplicarlo a incendios reales.
docker compose -f docker-compose.yml -f docker-compose.edge-limits.yml -f docker-compose.edge-b2.yml up -d --build mosquitto edge
docker compose -f docker-compose.yml -f docker-compose.edge-limits.yml -f docker-compose.edge-b2.yml exec mosquitto mosquitto_sub -h 127.0.0.1 -t wildfiresense/edge/status -C 1
# Comprobar isolated_escalation_enabled: true en el JSON de estado.
```

B2 genera `unconfirmed_fire_risk` (**high pero explícitamente NO corroborada**) exclusivamente si faltan vecinos sanos recientes, aumenta PM2.5 rápido frente al fondo, la tendencia de temperatura es positiva y la evidencia persiste. **No se debe contar como `suspected_fire`.** La Cloud V4 la puede almacenar como `environmental_alert`, pero su panel actual todavía no distingue visualmente esa decisión; coordinar esa etiqueta con el compañero de Cloud.

Evidencia y limitaciones: `docs/AI_THRESHOLDS.md`, `docs/POLITICA_B_SELLADO_Y_B2.md`, `docs/POLITICA_B_NODO_AISLADO.md`, GitHub Actions de la PR #9. La política B1 anterior se **rechazó** en la validación sellada (6/48 falsas alertas con fondo alto); B2, más conservadora, pasó un gate **solo sintético**. Faltan pruebas MQTT/recursos sobre el hardware de entrega. No se ha demostrado detección de incendios reales.

## Funcionalidad heredada de V3: IA Edge, incidentes y robustez

Un bosque aleatorio clasifica cada lectura ambiental. El gateway genera un preaviso por persistencia y corrobora la sospecha de fuego con otro nodo cercano. El botón SOS entra por un canal independiente. Incluye el modelo entrenado, los nueve escenarios originales, un simulador de 1.000 sensores, el broker MQTT, el receptor central, el panel y las pruebas.


## Novedades de V3 — desarrollo hacia la entrega de diciembre

Este árbol conserva el **modelo, los nueve escenarios, el Edge y los protocolos MQTT** de Edge1000.
No se ha modificado el algoritmo de detección ni las alertas que publica. Se añade:

- `GET /api/incidents`: **agrupa sospechas corroboradas en incidentes experimentales** por `run_id`, vecindad 8-conexa en la malla 32×32 y máximo de 30 minutos entre observaciones contiguas. El panel separa estos grupos de los mensajes de alarma, y siempre conserva los mensajes originales.
- `python -m lab.incident_demo`: demuestra offline la agrupación en los archivos originales. En `fuego_lento`, **218 avisos → 1 grupo**; `fuego_rapido`, **41 avisos → 2 grupos** (40 y 1), según esos supuestos. No se debe llamar a estos grupos incendios reales.
- `python -m lab.early_detection`: **recall por episodio antes de 5, 15, 30 y 60 minutos**, a partir de `resultados/episodios_test.csv`, sin reentrenar ni reutilizar etiquetas como entradas.
- `python -m lab.robustness --loss 0.05 --duplicates 0.02 --jitter-s 10`: prueba **offline y reproducible** de pérdidas, duplicados y orden de llegada, sin afirmar que se haya simulado WiFi/LoRa real.
- `docker-compose.edge-limits.yml`: límite opcional de **0,5 CPU y 512 MiB para el Edge**.
- Corrección del cierre de sockets Paho en simulaciones de muchos clientes.
- `docs/ROADMAP_TRES_SEMANAS.md`, `docs/INTEGRACION_V3.md` y nuevas pruebas.

**En tu Windows, sin instalar Python**, ejecuta las nuevas funciones dentro de Docker:

```powershell
# En la carpeta del proyecto, junto a docker-compose.yml
docker compose -f docker-compose.yml -f docker-compose.edge-limits.yml up -d --build mosquitto edge cloud
docker compose run --rm --no-deps -v "./resultados:/app/resultados" simulator python -m lab.incident_demo
docker compose run --rm --no-deps -v "./resultados:/app/resultados" simulator python -m lab.early_detection
docker compose run --rm --no-deps -v "./resultados:/app/resultados" simulator python -m lab.robustness --loss 0.05 --duplicates 0.02 --jitter-s 10
# Comprobar los incidentes agrupados en el nuevo panel
Invoke-RestMethod http://localhost:8090/api/incidents
# Tests de la revisión actual, montados en el contenedor porque no van en la imagen runtime
docker compose run --rm --no-deps -v "./tests:/app/tests:ro" simulator python -m unittest discover -s /app/tests -v
```

Si el entorno anterior sigue abierto con nombre de proyecto Compose `wildfiresense-edge-ai`, se reutilizan sus servicios/volúmenes cuando se ejecuta desde esta carpeta. Haz copia del directorio anterior y usa la actualización controlada descrita en `docs/INTEGRACION_V3.md`. **No ejecutar `docker compose down -v`** si quieres conservar los históricos. La V4 está publicada en la PR #6 y las mejoras optativas de Edge IA en la PR #9, pendientes de revisión y fusión.

**Interpretación**: los agrupamientos espaciales y las pruebas con pérdidas son hipótesis experimentales; no es un detector certificado ni se han probado enlaces radio físicos.

## Primera demostración · Python 3.12

Descomprime el ZIP y abre una terminal en la carpeta que contiene este README.

```bash
python -m lab.demo
```

En Windows también puedes usar `py -3.12 -m lab.demo`. En Linux, `python3 -m lab.demo`. Este recorrido local funciona con la biblioteca estándar, sin Internet ni instalaciones de paquetes. Usa el mismo motor de inferencia que MQTT. Deberías ver **1.000 nodos, 47.981 lecturas, 1 SOS y 9 sospechas con vecino**. La llegada del frente interrumpe el envío de algunos nodos. El primer SOS corresponde a `node_0496`; la primera sospecha corroborada aparece en `node_0497` con `node_0496` como vecino.

## Demo MQTT con panel · Docker Desktop o Docker Engine + Compose v2

Desde la misma carpeta:

```bash
docker compose up -d --build mosquitto edge cloud
docker compose run --rm simulator
```

Abre **http://localhost:8090**. El proceso del simulador termina al completar ocho minutos virtuales a velocidad ×8 (aproximadamente un minuto real). El panel actualiza los avisos automáticamente. Los servicios se mantienen disponibles. Para revisar una alarma, abre **http://localhost:8090/api/alerts?limit=5**. Para ver el modelo, los nodos y la latencia, lee el estado del gateway:

```bash
docker compose exec mosquitto mosquitto_sub -h localhost -t wildfiresense/edge/status -C 1
docker compose logs --tail=30 edge
```

La primera construcción necesita descargar las imágenes de Python y Mosquitto. Paho 2.1.0 está incluido en `vendor/`. Los datos y los pesos se cargan desde el ZIP. Se utilizan los puertos de bucle local 1883 y 8090. Si ya está abierto el stack anterior, páralo desde su propio directorio o cambia los puertos del host en este Compose. Los servicios mantienen los puertos internos.

### Demostrar autonomía y recuperación en clase

1. Arranca los tres servicios y abre el panel.
2. Ejecuta `docker compose stop cloud` y espera 7 segundos para que caduque el último eco.
3. Ejecuta `docker compose run --rm simulator`. Mira `docker compose logs --tail=30 edge`. Durante el corte aparecen el SOS y las sospechas en el gateway.
4. Ejecuta `docker compose start cloud`. El panel recupera los avisos guardados. En el estado del gateway, `backlog` vuelve a 0 después de los acuses de aplicación.
5. Para detener la demo conservando los históricos, ejecuta `docker compose down`.

### Demostrar 1.000 conexiones distintas

```bash
docker compose run --rm simulator python -m lab.mqtt_run --clients 1000 --nodes 1000 --cycles 6 --period 10 --speed 1 --scene normal
```

Son seis lecturas de cada nodo, 100 mensajes/s nominales durante un minuto. Revisa `publishing_clients`, `distinct_nodes_sent`, `received`, `PDR` y los percentiles. Ejecuta un solo simulador a la vez para esta prueba: los contadores del gateway son globales. La demo rápida usa por defecto un publicador multiplexado. Los parámetros `--clients 1000` y `--nodes 1000` prueban por separado conexiones y estados por sensor. Cada ejecución usa un identificador nuevo. El estado muestra tanto identificadores físicos distintos como pares ejecución–nodo retenidos. Los filtros permanecen aislados entre ejecuciones.

### Reproducir un archivo del equipo por MQTT

```bash
docker compose run --rm simulator python -m lab.mqtt_run --file data/scenarios/polvo_tractor.jsonl --speed 120
docker compose run --rm simulator python -m lab.mqtt_run --file data/scenarios/sos_boton.jsonl --speed 120
```

Cada trama recibe un instante real de envío. El campo `ts` del escenario conserva su tiempo virtual. Para incendios distribuidos puede haber muchos avisos por nodo durante un mismo episodio. El panel muestra tanto mensajes únicos como agrupaciones experimentales de incidentes; ninguna agrupación equivale a un incendio confirmado en campo.

## Qué abrir para la presentación

| Archivo | Contenido |
|---|---|
| `docs/Informe_WildfireSense_Edge.pdf` | Ocho páginas para explicar la arquitectura, la IA, los resultados y los límites |
| `docs/DECISIONES.md` | Incongruencias, decisiones del equipo, fuentes y alcance académico |
| `docs/ROADMAP_TRES_SEMANAS.md` | Plan de entrega hasta el 11/12/2026, prioridades, aceptación y riesgos |
| `docs/RESULTADOS_V3_20261120.md` | Resultados temporales, agrupación y simulación adversarial reproducibles |
| `docs/REPRODUCIR.md` | Evaluación, entrenamiento, actualización del modelo y protocolo MQTT |
| `resultados/` | Medidas reales de esta entrega, CSV por episodio, confusión, tráfico y pruebas |
| `data/scenarios/` | Los nueve JSONL originales de la semilla 42 y su verdad externa |
| `edge/`, `models/`, `lab/`, `cloud/` | Gateway, modelo exportado, simulación/evaluación, almacenamiento y panel |
| `referencia/` | Documento Word aportado y revisiones Git de partida sin configuración local |

Las métricas describen una simulación. La carga con 1.000 conexiones se verificó con procesos nativos de Mosquitto y Python en Linux; también se validó el manifiesto con Docker Compose. Las pruebas completas de la version nueva del panel siguen pendientes de repetirse en Docker Desktop del equipo. Ya se midieron 1.000 clientes MQTT independientes y el limite de 0,5 CPU / 512 MiB en el prototipo anterior. El comportamiento radio y el consumo electrico de la placa permanecen sin medir.
