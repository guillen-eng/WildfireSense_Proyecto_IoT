# WildfireSense — Edge AI: fundamento, umbrales y criterio de aceptación
**Referencia:** V4 `rf-a288fc78989a` | **Fecha:** 2026-11-22 | **Estado:** propuesta de congelación técnica pendiente de ensayo de sensibilidad

> **No afirmar validación con incendios reales.** La evidencia experimental actual procede de escenarios sintéticos de la misma familia física/generativa, aunque con semillas distintas. Esta nota distingue explícitamente fuentes externas, decisiones de ingeniería y resultados medidos.

## 1. Relación con lo exigido en clase

- *Module 3 — Project Guidelines*, pp. 2–4: elegir sensores/variables, muestreo, preprocesado, modelo ligero para inferencia en Edge, funcionamiento sin Cloud, presupuesto de latencia y evaluación cuantitativa. La figura 1 de la p. 3 separa fuente, comunicaciones, Edge/Edge AI, Cloud y Cloud AI; esta nota cubre **Edge/Edge AI**, no Cloud.
- *Module 1 — IoT Part II*, pp. 21–22: muestreo periódico/evento y suavizado; pp. 28 y 30–34: inferencia cercana a fuente y clasificación; p. 13: 1.000 sensores cada 10 s es un **ejemplo docente**, no una ley del fenómeno forestal.
- *Module 1 — IoT Part I*, pp. 71–73: MQTT publicación/suscripción, QoS. LoRa (pp. 41–66) se explica como tecnología, **no está simulado por la implementación V4**.

## 2. Variables, modelo y contrato reproducible

- Entradas físicas: `PM2.5` (µg/m³), `PM10` (µg/m³), temperatura ambiente (°C), humedad relativa (%). El modelo **no recibe** ni la clase verdadera del episodio ni etiquetas del simulador: `edge/contract.py` rechaza los campos prohibidos.
- Ocho features temporales definidos en `edge/features.py`: `pm25_fast`, `pm10_fast`, `fine_fraction`, `pm25_change`, `temperature_change`, `humidity_fast`, `humidity_change`, `pm25_slow`. Se usan filtros exponenciales causales con escalas de 30 y 300 s; no se leen muestras futuras.
- Clasificador supervisado Random Forest de **19 árboles** y **6 clases** (`normal`, `slow_fire`, `fast_fire`, `dust`, `fog`, `direct_sun`). Es un modelo de prototipo multiclase; sus puntuaciones no equivalen a probabilidades de fuego real calibradas.
- Modelo **oficial, sin modificar**: `models/forest.json`, versión `rf-a288fc78989a`, exportado a JSON para ejecutar el bosque en Edge sin scikit-learn. La etapa de entrenamiento sí usa scikit-learn fuera de Edge. No volver a entrenar por intuición: un candidato solo puede sustituir al modelo mediante la puerta de validación documentada en `docs/V4_VALIDACION_MODELOS.md`.
- Entrenamiento sintético: semillas 101–124. Selección de modelos y sensibilidad: 301–306. Prueba previamente publicada: 201–230; **no se utilizará para elegir umbrales**. La comparación debe hacerse por **episodio completo**, no mezclando al azar muestras correlacionadas.

## 3. Matriz de decisiones y procedencia

| Valor en V4 | Papel real en código | Procedencia y argumento | ¿Qué falta justificar empíricamente? |
|---|---|---|---|
| `fire_score >= 0.65` | Clasificador: suma de fracciones de voto/probabilidad de hojas en las clases fuego; una condición necesaria | **Hipótesis de decisión del equipo**. No existe normativa que prescriba 0,65; su balance sensibilidad/especificidad se estudia con distintas puntuaciones | Curva de detección por episodio, demora, falsos avisos y calibración si se usa como probabilidad |
| `pm25_fast >= 18 µg/m³` | Filtro de plausibilidad después de RF | **Corte empírico** diseñado para evitar alertas por pequeñas variaciones de fondo. No procede del AQI ni define ignición | Mostrar sensibilidad a fondo alto y humo débil; no imponerlo a sensores futuros sin calibración |
| `fine_fraction >= 0.36` | Filtro `PM2.5_filt/PM10_filt` después de RF | **Hipótesis del generador**, buscando discriminar polvo grueso/humo fino. Las relaciones varían entre combustibles, composición y aerosoles | Probar ratios por debajo de 0,36 y confusores con fracción fina alta |
| 30 s `persist_s` | Preaviso `environmental_risk` solo después de señal sostenida | **Compromiso experimental** entre inmunidad a picos y retardo. A periodo 10 s suele exigir ~4 lecturas, si el evento se mantiene | Escenarios de fuego de aparición rápida, pérdidas y frecuencia distinta de muestreo |
| 180 s `neighbour_ttl_s` | Sospecha `suspected_fire` al corroborar vecino sano entre 8 celdas | **Supuesto espacio-temporal del piloto**, no velocidad de propagación certificada. La malla usa 126 m/paso en simulación | Distancias reales, viento variable, densidad de nodos y nodos aislados |
| 60 s `clear_s` | Borra estado de alarma de episodio tras ausencia persistente de evidencia | **Histéresis experimental**, reduce oscilación y permite futuros episodios | Tasa de alarmas repetidas vs. duración del episodio |
| Filtro rápido 30 s/lento 300 s | Características temporales causales | **Escalas de análisis escogidas**: variación rápida vs. fondo de varios minutos; enseñanza de smoothing en Module 1 II, p. 22 | Comparación en diferentes periodos de muestreo; no reentrenar features sin nuevo gate |
| Diez lecturas exactamente iguales | Marca nodo como `SOSPECHOSO` | **Heurística de fallo por congelación**; a 10 s, ~90 s desde la primera de 10 lecturas | Falsos bloqueos en variables cuantizadas o escenarios muy estables |
| Varianzas >115 (PM2.5) y >1,05 (T) en 12 lecturas | Marca nodo `SOSPECHOSO` por ruido conjunto | **Valores de laboratorio**, no caracterización certificada del sensor | Ajuste con ruido medido de dispositivo concreto; sensibilidad al cambio de cadencia |
| Silencio > `max(45, 2.5 × periodo)` s | Marca `FALLO` y descarta evidencia vencida | **Watchdog proporcional a frecuencia**, evita falso fallo en nodos que reportan cada 60 s | Medir pérdidas y apagones; distinguir MQTT keepalive de presencia de cada nodo |
| Reglas: `pm25_fast >= 35.5` | Referencia de comparación **solo en modo `rules`**, no condición del Random Forest | **EPA AQI**: 35,5 µg/m³ inicia una categoría de PM2.5 de *promedio 24 horas*. No es un umbral de humo, ignición ni lectura de 10 s | No presentarlo como detector científicamente certificado; evaluar en la misma prueba que ML |

**Importante:** `environmental_risk` es un preaviso de **evidencia de humo/partículas en el prototipo**, no un índice meteorológico de *riesgo de ignición*. `suspected_fire` tampoco demuestra un incendio real.

## 4. Estados y comportamiento al perder sensores

1. MQTT recibe mensajes válidos y Edge mantiene estado causal por nodo (secuencia, periodo, filtros, calidad).
2. `fire_score`, PM2.5 y fracción fina cumplen el corte; tras persistencia de 30 s se genera `environmental_risk` de prioridad `advisory`.
3. Solo si un **nodo vecino sano** conserva evidencia de los últimos 180 s se publica `suspected_fire` de prioridad `high`.
4. Con **un solo nodo o vecinos sin datos**, se conserva el aviso `advisory` y se evita afirmar corroboración. **Es el comportamiento actual**, pendiente de decisión explícita del equipo respecto a escalado sin vecinos.
5. El botón SOS es un canal independiente: aviso `critical` sin esperar modelo ni vecinos.
6. Si Cloud no está disponible, Edge continúa procesando y conserva mensajes pendientes en su SQLite local. La IA crítica nunca se traslada a Cloud.

**Decisión provisional conservadora para nodo aislado:** mantener `advisory`; no crear una falsa `high` corroborada. Para el informe final, registrar riesgo de perder/demorar fuego verdadero en zona de baja densidad. Si el equipo decide otra política, requerirá otra PR y nuevos ensayos.

## 5. Validación cuantitativa y criterios antes de congelar

**Ya observado en V4, usando el mismo generador con semillas independientes:** `resultados/validacion.json` registra 60/60 episodios de incendio con `suspected_fire`, 0/120 episodios negativos con alarma corroborada, `macro F1 = 0.770705` y retardo medio ~595,67 s entre los incendios detectados. Este 60/60 **no es** sensibilidad de incendios de campo. Las seis clases se evalúan por lectura; los avisos se evalúan por episodio y por deadline (5/15/30/60 min).

**Pendiente antes de elegir parámetros:** ejecutar el barrido `lab.threshold_sensitivity` sobre 301–306. Varia una variable cada vez y mantiene el bosque fijo. Guardar `configurations.csv` y `episodes.csv`. Los resultados no seleccionan automáticamente ninguna configuración, no reentrenan, no modifican `models/forest.json` ni tocan el motor MQTT desplegado.

**Criterio recomendado de aceptación de cambios:** no incrementar episodios negativos con `suspected_fire` en validación; no disminuir episodios de incendio detectados; buscar mejora real del recall a 5/15 min o de p95 de demora. Cualquier criterio final debe fijarse **antes** de mirar los nuevos datos de prueba. Si las alternativas no mejoran de forma convincente, mantener los umbrales V4. La métrica crítica es la alarma corroborada, no solo la salida de clase del RF.

**Prueba de generalización adicional:** escenarios con otras ecuaciones o mediciones externas etiquetadas. Nuevas semillas 401–420 del mismo generador son un *stress check adicional*, **NO una fuente independiente**. Para demostrar robustez fuera de distribución hay que cambiar condiciones físicas o usar datos etiquetados independientes, sin reutilizar esos nuevos datos para el ajuste.

**Pruebas de ingeniería necesarias:** un único nodo, vecino envejecido, SOS sin histórico, duplicados, reorder/pérdida MQTT y comportamiento con Cloud apagada. Capturar rendimiento con 0,5 CPU y 512 MiB en Edge. El buffer de reorder offline sigue **deshabilitado** en la ruta MQTT crítica hasta probar coste de latencia y reglas de reloj.

## 6. Comandos reproducibles (en la carpeta `demos/edge1000-v4`)

```powershell
# Tests automáticos del Edge/Cloud legado
docker compose -p wf-edge-ai-final run --rm --no-deps -v "./tests:/app/tests:ro" simulator python -m unittest discover -s /app/tests -v

# Comparación de políticas: selección con semillas de validación 301–306
docker compose -p wf-edge-ai-final run --rm --no-deps -v "./resultados:/app/resultados" simulator python -m lab.threshold_sensitivity --seeds 301 302 303 304 305 306 --out /app/resultados/umbral_sensibilidad

# Exploración corta, solo la puntuación, para verificar el script
docker compose -p wf-edge-ai-final run --rm --no-deps -v "./resultados:/app/resultados" simulator python -m lab.threshold_sensitivity --axis score --seeds 301 --out /app/resultados/umbral_rapido
```

NOTA: antes de los comandos en una instalación limpia hay que **construir** las imágenes con `docker compose build simulator`. El nombre Compose aislado evita mezclar volúmenes de pruebas con la instalación histórica. No ejecutar `down -v` sobre el proyecto original.

## 7. Fuentes verificables (no justifican automáticamente números concretos)

1. Beatriz Soret, *Module 3 — Project Guidelines* (septiembre 2026), pp. 2–4 y 7; *Module 1 — IoT Part II*, pp. 13, 21–22, 28 y 30–34; *Module 1 — IoT Part I*, pp. 68 y 71–76.
2. U.S. EPA, *AQI Breakpoints*, PM2.5 de 24 horas, categoría `UNHEALTHY FOR SENSITIVE` desde 35,5 µg/m³: https://aqs.epa.gov/aqsweb/documents/codetables/aqi_breakpoints.html (consultado 22/11/2026).
3. Barkjohn, K., Gantt, B., Clements, A. (2021), *Development and application of a United States-wide correction for PM2.5 data collected with the PurpleAir sensor*, Atmospheric Measurement Techniques 14, 4617–4637. DOI: https://doi.org/10.5194/amt-14-4617-2021. Justifica **considerar humedad/calibración**, no los cortes 0,36 o 0,65.
4. scikit-learn, *Tuning the decision threshold for class prediction*, https://scikit-learn.org/stable/modules/classification_threshold.html (consultado 22/11/2026). Recomienda sintonizar umbrales con datos de validación separados, sin reutilizar los de entrenamiento.
5. Código del proyecto, `edge/logic.py`, `edge/features.py`, `lab/episodes.py`, `lab/evaluate.py`, `resultados/validacion.json`, rama `feature/edge1000-v4-integration` (commit `f9c31a2`).

## 8. Criterio de cierre de este trabajo de Edge AI

- [ ] Tests automatizados pasan en una CI de GitHub y en Docker de la máquina de entrega.
- [ ] Modelo y versión de baseline verificables en salida real del Edge.
- [ ] Estudio de sensibilidad sobre semillas de validación, con CSV y decisión escrita, **sin seleccionar con test 201–230**.
- [ ] Prueba posterior de robustez fuera de distribución, o limitación documentada con suficiente precisión.
- [ ] Política para nodo aislado explícita y demostrada.
- [ ] Alarmas y SOS idénticos con/sin Cloud; rendimiento y errores cuantificados.
- [ ] Aprobación del equipo antes de fusionar a V4, conservando trazabilidad.

## 9. Actualización final de la política B2 (22/11/2026)

El equipo eligió estudiar el escalado condicionado de un sensor aislado. **Después de dos rondas preregistradas de prueba sintética**, se seleccionó la alternativa conservadora B2 *solo para un modo de demostración opcional*, sin alterar los umbrales originales del clasificador ni el archivo `forest.json`:

| Parámetro optativo B2 | Valor | Procedencia |
| --- | --- | --- |
| Ausencia de vecino sano reciente | edad > `max(45,2.5 × periodo)` o inexistente | Semántica de calidad/availability ya presente en el watchdog V4 |
| Persistencia total | >=120 s | Selección experimental por episodios de desarrollo 301–306 |
| Score de fuego | >=0.80 | Puerta empírica más exigente que el score ordinario 0.65; NO es probabilidad calibrada |
| `pm25_fast - pm25_slow` | >=8 µg/m³ | Puerta empírica de tendencia causal para evitar interpretar como incendio todo fondo de partículas alto |
| `temperature_fast - temperature_slow` | >=0.5 °C | Puerta empírica adicional para reducir falsas alertas aisladas; puede perder humo que no calienta el punto de medición |
| Tipo de evento | `unconfirmed_fire_risk` | `priority=high` y `confirmation=unconfirmed`; distinto de `suspected_fire`, sin afirmar confirmación |

**Secuencia científica transparente:** B1, con puerta de temperatura >=0 °C, falló en el ensayo sellado 601–612 (6/48 episodios negativos con falsa alerta alta ante fondo elevado); B2, seleccionado **antes de abrir** nuevas semillas 801–812, superó el criterio de aceptación *solo sintético limitado*: 11/24 fuegos aislados normales, 0/48 falsos normales y 0/48 falsos con fondo elevado, sin pre-ignición. La sensibilidad cae a 5/24 en humedad >=97 %, 1/24 con PM2.5 subestimado 30 % y 0/24 en una mezcla deliberadamente gruesa. Estas cifras no justifican desplegar B2 en un bosque real.

Pruebas verificables:
- [B1 rechazado](https://github.com/guillen-eng/WildfireSense_Proyecto_IoT/actions/runs/45047919874).
- [B2 aprobada para demo sintética limitada](https://github.com/guillen-eng/WildfireSense_Proyecto_IoT/actions/runs/45048219655).
- [B2 MQTT real y SOS, 1.000 clientes bajo 0.5 CPU / 512 MiB](https://github.com/guillen-eng/WildfireSense_Proyecto_IoT/actions/runs/45048746292).

**Estado de producción académica:** el Edge V4 sigue usando la ruta original por defecto (`EDGE_ISOLATED_ESCALATION=0`); el overlay `docker-compose.edge-b2.yml` activa el experimento conscientemente. El equipo de Cloud debe representar la advertencia no corroborada en el panel (issue [#10](https://github.com/guillen-eng/WildfireSense_Proyecto_IoT/issues/10)), sin contarla como incidente espacialmente corroborado.

**Interpretación:** ningún artículo revisado ni las diapositivas exige exactamente 120 s, 8 µg/m³ o 0.5 °C. Los números son hipótesis de ingeniería escogidas mediante pruebas de desarrollo y un test sellado dentro del simulador. La calidad real requiere observaciones etiquetadas externas y sensores calibrados.
