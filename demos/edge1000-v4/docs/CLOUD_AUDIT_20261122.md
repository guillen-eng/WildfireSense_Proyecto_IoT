# Cloud V4: auditoría, alcance y plan de integración (2026-11-22)

**Estado:** auditoría estática sobre la rama `feature/edge1000-v4-integration` (PR #6, base SHA `f9c31a2a56394f5375fd6a89243179d09c5acd22`) y primera mejora sobre `feature/cloud-v4-reliability`.

**Regla de colaboración:** no editar `edge/`, `models/forest.json`, `lab/model_gate.py`, los topics MQTT ni formatos compartidos sin acuerdo previo. No modificar `main`; ninguna PR se fusiona automáticamente.

## 1. Fuente de verdad y dos Clouds coexistentes

- `cloud/` de la raíz conserva el receptor del prototipo anterior. Su código ofrece SQLite, alertas, endpoints básicos y panel, pero **no** consume el ACK de aplicación de la V4.
- `demos/edge1000-v4/cloud/` es la implementación integrada a la demo V4. **Esta es la base propuesta para Cloud V4**. Contiene `app.py` (MQTT, SQLite y API), `analysis.py` (agregados PM2.5), `incidents.py` (agrupación experimental) y `dashboard.html`.
- La V4 todavía es un demostrador autocontenido dentro de `demos/`. No sustituir `cloud/` raíz ni iniciar ambas variantes por accidente en el mismo puerto.
- El término Cloud designa **un contenedor local** sobre Docker; no un proveedor remoto, ni un enlace físico LoRa/WiFi de campo.

## 2. Correspondencia con docencia

Referencias locales aportadas por la asignatura:

- *Module 3 — Project Guidelines*, pp. 3-4: seis componentes, capa Cloud de histórico/dashboard, IA Cloud para reentrenamiento y vuelta de pesos, separación Edge/Cloud por latencia/ancho de banda/privacidad/energía, medidas de tráfico.
- *Module 3*, p. 7: memoria 8-12 páginas, README y Compose reproducibles, historial de commits y demo viva con defensa individual.
- *IoT and V2X presentation*, pp. 11 y 13: gateway con selección adaptativa según enlace y ejemplo Edge/Cloud.
- *Module 1 — IoT Part II*, pp. 13, 15, 23, 27, 30: 1.000 sensores de ejemplo, complementariedad Edge/Cloud, almacenamiento temporal + histórico, API de dashboard y arquitectura ML híbrida.

| Requisito | Estado comprobado en código V4 | Brecha de entrega |
| --- | --- | --- |
| MQTT real y separación de funciones | Broker Mosquitto, topics QoS 0/1; Edge genera alarmas y Cloud las suscribe | Documentar semánticas distintas de QoS y de ACK de aplicación |
| Edge autónomo | Journal SQLite en Edge; inferencia y SOS locales; envío posterior tras ACK | Repetir escenario de caída y reinicio del receptor en equipo de entrega |
| Reparto adaptativo | `edge/main.py` decide cómputo local/remoto de agregados no críticos con Ping/Pong y RTT | Demostrar y medir escenarios conectados/degradados sin cambiar detector crítico |
| Cloud histórico | Alertas y ventanas agregadas en SQLite WAL y volumen `cloud_state` | No se guardan todas las lecturas ni hay BD de series temporales especializada; justificar la elección |
| Deduplicación | Alerta por ID, resumen por ID; en esta rama se diferencia repetición idéntica de colisión de contenido | Probar reinicios, colisiones y fallo de BD con MQTT real |
| API y dashboard | `/api/health`, `/api/stats`, `/api/alerts`, `/api/incidents`; panel refrescado periódicamente | En esta rama se añade `/api/summaries`; todavía faltan series temporales, paginación histórica y filtros de fechas |
| Incidentes | Agrupación derivada, sin alterar alertas, por run, malla 32x32 y vecindad 8-conexa/30 min | Agrupación recalculada desde todos los eventos en cada GET: coste creciente, sin estado operador |
| IA Cloud | `trainer`, `retrain`, `validator`, `promote`; gate compara modelos en escenas sintéticas | El receptor Cloud no produce etiquetas reales ni distribuye el modelo; actualización mediante carpeta y reinicio manual |
| Observabilidad | Logs, estado MQTT, estado Edge retenido y último agregado | Health solo refleja conexión MQTT, no comprueba lectura/escritura BD; sin métricas de retrasos, conflictos o frescura |
| Seguridad | Puertos HTTP/MQTT vinculados a localhost | MQTT anónimo y HTTP sin autenticación: **solo laboratorio local** |

**Interpretación:** la guía da como ejemplos InfluxDB/TimescaleDB + Grafana, pero admite elegir tecnologías justificadas. Se propone conservar SQLite y el panel Python para una entrega estable; un perfil opcional con Grafana/InfluxDB solo si las pruebas y el calendario lo permiten. No presentar SQLite como un backend Cloud elástico de producción.

## 3. Riesgos confirmados en la auditoría del código V4 original

1. **P0: ID duplicado de contenido diferente.** `AlertStore.ingest()` devolvía `duplicate` por `INSERT OR IGNORE` sin cotejar contenido, y el callback emitía ACK. Lo mismo ocurría con `summaries`. Un `event_id` reutilizado por error con datos distintos podía desaparecer de la cola Edge sin haberse almacenado. Corregido en esta rama: `conflict`, no ACK, registro de error, evento previo intacto.
2. **P0: alcance de garantía de entrega.** Paho puede emitir PUBACK MQTT aunque falle SQLite; la seguridad real del reenvío depende de que el Journal Edge mantenga el evento hasta el **ACK de aplicación**. No proclamar exactly-once end-to-end. Necesita ensayo de fallos de disco/SQLite y broker.
3. **P1: histórico incompleto para análisis.** La Cloud original solo exponía `last_summary`; no podía consultarse la serie de agregados. En esta rama existe `GET /api/summaries?limit=...`, orden inverso de inserción, y `total_summaries` en stats. No se han añadido lecturas crudas ni se ha cambiado el tráfico Edge.
4. **P1: crecimiento de incidentes.** `/api/incidents` carga todas las alertas ambientales en memoria y agrupa en cada solicitud. El panel lo solicita cada 2 s. Necesita evaluación con semanas de histórico y eventual cache/vista materializada **sin reemplazar evidencia bruta**.
5. **P1: observabilidad débil.** `/api/health` no valida SQLite; no existen contadores de payload inválido, conflicto, tamaño de backlog en Cloud, lag de ingesta, capacidad o estado del modelo Cloud.
6. **P1: actualización de modelos solo por fichero compartido.** La validación y promoción son funciones de `lab/`, no un canal autenticado Cloud -> Edge. Gate de candidatos sintéticos probado según documentos V4; descarga/distribución, firma, roll-back automático y revisión humana trazada no implementados.
7. **P2: autenticación y aislamiento.** Configuración aceptable solo bajo loopback para demostración; no desplegar hacia Internet.

## 4. Primera entrega de esta rama

Solo se modifican:
- `demos/edge1000-v4/cloud/app.py`: idempotencia estricta en alertas/resúmenes, ACK condicionado a persistencia coincidente, endpoint de histórico y contador de resúmenes.
- `demos/edge1000-v4/tests/test_cloud_history.py`: nueve tests de persistencia, colisiones, validación, historial y API.
- `.github/workflows/cloud-v4-tests.yml`: ejecución de unittest con Python 3.12 y la rueda Paho versionada.
- Este documento de auditoría.

**Compatibilidad:** no cambia ningún nombre de topic ni forma de mensaje/ACK MQTT. Los endpoints antiguos y el dashboard existente conservan sus respuestas; solo se añade información. Un ID conflictivo no se confirma, de manera intencionada: requiere diagnóstico del emisor, no eliminación silenciosa de datos. No se toca el modelo.

**Estado de pruebas (verificado 22/11/2026):** GitHub Actions [run #45022489272](https://github.com/guillen-eng/WildfireSense_Proyecto_IoT/actions/runs/45022489272), Python 3.12, completó **53 tests en 7,722 s, OK**: los 44 de V4 más los nueve tests Cloud nuevos. La ejecución validó los commits de código/tests y workflow hasta `37e248ad9c3da8ac118c274de597fdc784cf4402`; los commits posteriores de documentación no alteran runtime. El archivo histórico `resultados/tests.txt` contiene solo 22 tests antiguos y no debe tomarse como la prueba actual. **Pendiente:** test E2E con broker MQTT y Docker en el equipo de entrega, además de inyección de fallo de SQLite. El archivo `resultados/ensayos_docker_20261120.json` documenta un ensayo de 1.000 clientes aportado por el equipo; no valida los cambios de esta rama.

## 5. Hoja de ruta priorizada al 11/12/2026

| Prioridad y fecha objetivo | Desarrollo | Criterio de aceptación observable |
| --- | --- | --- |
| P0 — 25/11 | Validar deduplicación + histórico de resúmenes (esta rama) | Tests verdes, HTTP 200/400 coherentes, duplicados no incrementan cuentas, conflictos no generan ACK de aplicación |
| P0 — 27/11 | Ensayo Cloud caído / recuperación, reinicio con volumen, fallo SQLite y reenvío repetido | Identificadores sin pérdida de eventos aceptados; backlog Edge vuelve a cero **solo** para eventos escritos |
| P1 — 02/12 | API de histórico por rango temporal/paginación; panel con tendencias PM2.5 y estado de frescura | Navegar históricos mayores de 200 resultados sin saltos ni reconsultas masivas |
| P1 — 04/12 | Observabilidad: latencia de ingesta, tasas, errores/conflictos, estado DB y vista eficiente de incidentes | Health diferencia MQTT de DB; pruebas bajo volumen histórico y tiempos HTTP medidos |
| P1 — 07/12 | Integración de Cloud AI sin promoción automática | Candidato con ID/hash y metadatos auditables; gate y rechazo visibles; procedimiento manual de rollback documentado |
| P0 — 09/12 | Validación integral con 1.000 clientes, reconexión, persistencia y dashboard | Medidas de PDR, bytes MQTT, p95/p99, CPU/RAM con entorno, semilla, revisión y límites explícitos |
| P0 — 11/12 | Cierre de informe y demo | README de clon limpio, guion de demo, reporte 8-12 páginas, contribuciones y limitaciones sintéticas |

**Dependencia externa:** si la integración final del equipo decide sustituir `demos/` por servicios en raíz, deberá aprobarse una PR específica. Esta auditoría no autoriza esa migración.

## 6. Verificación reproducible

Desde `demos/edge1000-v4/`:

```bash
python -m pip install --no-index -r requirements.txt
python -m unittest discover -s tests -v
docker compose up -d --build mosquitto edge cloud
curl -fsS http://127.0.0.1:8090/api/health
curl -fsS http://127.0.0.1:8090/api/stats
curl -fsS "http://127.0.0.1:8090/api/summaries?limit=5"
curl -fsS "http://127.0.0.1:8090/api/incidents?limit=5"
```

Para probar desconexión sin borrar datos:

```bash
docker compose stop cloud
docker compose run --rm simulator
docker compose start cloud
docker compose logs --tail=80 edge cloud
```

Observar `backlog` en `wildfiresense/edge/status` y comparar IDs con SQLite. **No ejecutar `docker compose down -v`** mientras se quiera conservar el histórico. La demo no prueba radio física ni rendimiento de Cloud público.

## 7. Decisiones abiertas para revisión del equipo

1. ¿Se acepta SQLite persistente en Cloud como implementación definitiva del laboratorio o se requiere perfil paralelo InfluxDB/Grafana? La guía permite elección, pero obliga a justificarla.
2. ¿Cómo documentar y visualizar los errores conflictivos sin añadir un topic de control o modificar Edge? Primera opción: contador y logs locales, diagnóstico manual.
3. ¿Qué política de retención/backup de alertas y resúmenes se desea, y por cuánto tiempo? Evitar borrar eventos originales por la vista de incidentes.
4. ¿Existe un conjunto revisado de señales y etiquetas externas para reentrenamiento? Si no, declarar expresamente que el circuito es sintético y no alimentarlo automáticamente con predicciones.
5. ¿Cuál será el contrato definitivo de distribución de modelos firmado y aprobado? No implementarlo unilateralmente sobre Edge.

**Nota final:** la agrupación de eventos es una hipótesis de laboratorio y la calidad de detección de incendios se ha evaluado exclusivamente con fenómenos sintéticos.
