# Política B de nodo aislado — WildfireSense Edge AI (fase experimental)

**Responsabilidad:** solo Edge + IA. No supone activar un clasificador nuevo en Cloud. La política B fue elegida por el equipo el 22/11/2026 para su *estudio*, **no** para despliegue inmediato.

## 1. Necesidad e interpretación

- Un nodo puede detectar un aumento anómalo sin vecinos disponibles: fallos de red, baja densidad de cobertura o apagones.
- V4 da el preaviso `environmental_risk` después de evidencia persistente; solo crea `suspected_fire` si detecta evidencia de **otro nodo sano** y reciente.
- En la opción B, después del preaviso se puede crear `unconfirmed_fire_risk`, con `priority=high`, `confirmation=unconfirmed` y `reason=no_fresh_healthy_neighbour`. **NUNCA** etiquetarlo como `suspected_fire` ni contarlo como incendio corroborado.
- Sin vecino, el sistema no sabe si hay incendio: la alerta pide revisión humana y comunica explícitamente su incertidumbre.
- **No se eleva** cuando hay un vecino sano y reciente que está dando lecturas normales. Esto evita disfrazar un desacuerdo real entre sensores como ausencia de corroboración.
- SOS siempre tiene `priority=critical` y no necesita ni IA ni vecinos.

## 2. Reglas candidatas, no normativas

En código `edge/logic.py`, `DetectionPolicy` define los parámetros; `EDGE_ISOLATED_ESCALATION=0` sigue siendo la configuración predeterminada del gateway, y `1` es una activación consciente del modo experimental.

La escalada exige simultáneamente:
1. `s.health == OK`, evidencia normal de fuego ML sostenida (base V4: puntuación >=0.65, PM2.5 rápido >=18 µg/m³, fracción fina >=0.36);
2. Tiempo adicional de persistencia desde el inicio de la evidencia, mayor que el del preaviso;
3. Puntuación de fuego más estricta que el mínimo ordinario (medida del clasificador sin calibración probabilística de campo);
4. Aumento temporal respecto a la media lenta: `pm25_fast - pm25_slow`, para intentar discriminar una concentración **alta pero estable** de una señal creciente;
5. Hipótesis fase 2: aumento simultáneo `temperature_fast - temperature_slow`, que ayuda a filtrar algunas fuentes de partículas sin calentamiento local;
6. **Ningún vecino sano con lectura fresca**. Frescura: edad >=0 y <= `max(45 s, 2.5×periodo)`, reutilizando el criterio de watchdog.

Los valores concretos de 120/180 s, 4/8 µg/m³ y 0.25/0.5/1 °C son **niveles candidatos para estudiar un compromiso**, no recomendaciones físicas ni criterios oficiales de ignición. El comportamiento de V4 permanece intacto con el interruptor desactivado.

La nueva clase mantiene `type=environmental_alert` y topic MQTT existente (`wildfiresense/edge/alerts`), de modo que se almacena en el SQLite Cloud anterior. **Limitación de integración:** el dashboard Cloud V4 no tiene aún etiqueta específica para la nueva decisión y puede mostrar `—`; coordinar con su responsable antes de entregar.

## 3. Desarrollo experimental: resultados, fallos y siguiente comprobación

**Fase 1 (GitHub Actions run #45047451621):** la prueba sintética sobre 301–306 probó variaciones de persistencia, puntuación y cambio de PM2.5, sin temperatura como condición. En modo aislado convencional la política más permisiva alcanzó 12/12 episodios de fuego; pero con PM de fondo elevado produjo **18/24 falsos eventos de prioridad alta**. Con `pm25_change >= 8`, llegaron a 11/12 fuegos y 1/24 negativos falsos. **Ninguno cumple un objetivo de cero falsas alertas en ese control adversarial**. No se promovió ningún candidato.

**Fase 2 (hipótesis formulada tras mirar la fase 1):** añadir tendencia de temperatura en el mismo nodo. Evaluar candidatos en datos de desarrollo 301–306. Es un *ajuste iterativo* de diseño: el nuevo barrido no proporciona una estimación final insesgada por sí mismo. La temperatura ambiente no siempre aumenta de forma detectable ante humo a distancia, por lo que una puerta térmica estricta puede **retrasar o perder incendios**. No elegir solo por eliminar falsos positivos.

## 4. Criterios de aceptación fijados antes del nuevo estudio

Comparar **por episodio** y distinguir tres tipos de mensaje:
- `environmental_risk` → preaviso de prioridad `advisory`.
- `unconfirmed_fire_risk` → alerta `high` **NO corroborada**, con razón, persistencia y tendencias.
- `suspected_fire` → alerta `high` espacialmente corroborada.

Para **considerar** activación B deben cumplirse:
- Cero `unconfirmed_fire_risk` en episodios negativos del conjunto de desarrollo *normal* y del fondo elevado **y** cero alertas previas a ignición simulada.
- Detección de una proporción material de fuegos de nodo aislado (cuantificar 5/15/30 min y los no detectados). Una alerta mucho más tardía que la corroboración normal puede no compensar.
- No cambiar los resultados de `suspected_fire` cuando hay vecinos sanos, los SOS, el formato MQTT, ni la recuperación del Journal.
- Repetición con **nuevas semillas selladas después de elegir** parámetros; si el equipo no tiene datos físicos externos, documentar que sigue siendo una validación sintética.

Se permite **rechazar todas las configuraciones** y mantener `EDGE_ISOLATED_ESCALATION=0` si ninguna cumple. Ese es un resultado científico válido y más defendible que activar una regla poco específica.

## 5. Evidencia y reproducibilidad

- Código: `edge/logic.py`, `edge/main.py`, `lab/isolated_policy_study.py`, `tests/test_isolated_escalation.py`.
- PR de desarrollo: https://github.com/guillen-eng/WildfireSense_Proyecto_IoT/pull/9
- Comandos desde `demos/edge1000-v4`:
  ```powershell
  docker compose -p wf-edge-b run --rm --no-deps -v "./resultados:/app/resultados" simulator python -m lab.isolated_policy_study --out /app/resultados/isolated_policy_dev
  docker compose -p wf-edge-b run --rm --no-deps -v "./tests:/app/tests:ro" simulator python -m unittest discover -s /app/tests -v
  ```
- En CI, descargar `candidates.csv`, `episodes.csv` y `study.json` desde la acción `WildfireSense isolated-node policy B study`.

## 6. Fuentes que fundamentan el **enfoque**, no los valores

1. Beatriz Soret (2026), *Project Guidelines — IoT and V2X System Design*, pp. 2–4: Edge autónomo, ML con latencia acotada, validación bajo conectividad y presupuesto de cómputo.
2. Beatriz Soret (2026), *Module 1 — IoT Part II*, pp. 20–22 y 28–30: falta/retardo de muestras, cambios temporales, suavizado y reparto inferencia Edge/Cloud.
3. EPA (2026), *Using Air Quality Sensors for Smoke: What to Consider*, https://www.epa.gov/system/files/documents/2026-06/air-quality-sensors-for-smoke-factsheet.pdf. El PM2.5 puede seguir humo, pero hay incertidumbre y variabilidad; **no prescribe umbral de incendio**.
4. Holder et al. (2020), *Field Evaluation of Low-Cost Particulate Matter Sensors for Measuring Wildfire Smoke*, Sensors 20(17), 4796, https://doi.org/10.3390/s20174796. Discute problemas de calibración/efecto de humedad en sensores ópticos.
5. *A tuneable framework for outlier detection in PM2.5 air sensor networks during wildland fire smoke events*, Atmospheric Measurement Techniques 19, 7359–7385 (2026), https://amt.copernicus.org/articles/19/7359/2026/. Describe retos de gradientes espaciales y condiciones hiperlocales que pueden diferenciar un sensor de sus vecinos.

**Advertencia:** estas fuentes no demuestran que las condiciones temporales concretas de V4 detecten un incendio forestal real, ni que sumar dos criterios derivados de un mismo evento equivalga a dos sensores independientes.

## 7. Segunda fase completada y candidato prefijado para prueba sellada

**Fase 2, validación 301–306:** GitHub Actions https://github.com/guillen-eng/WildfireSense_Proyecto_IoT/actions/runs/45047673848 (64 tests y barrido, OK).
Se ha evaluado una condición adicional: `temperature_fast - temperature_slow >= T`. **Incluso T=0 representa una puerta de temperatura nueva**: obliga a que la señal térmica rápida no esté descendiendo respecto al fondo lento, y no equivale a la primera fase sin puerta térmica.

| Opción en desarrollo | Aislados detectados (12) | Negativos con alarma (24) | Fondo alto con alarma (24) |
| --- | ---: | ---: | ---: |
| B, 120 s / score 0.80 / subida PM >=4 / subida T >=0 | 12 | 0 | 12 |
| **B, 120 s / score 0.80 / subida PM >=8 / subida T >=0** | **9** | **0** | **0** |
| B, 120 s / score 0.80 / subida PM >=8 / subida T >=0.25 °C | 8 | 0 | 0 |
| B, 120 s / score 0.80 / subida PM >=4 / subida T >=0.5 °C | 6 | 0 | 0 |
| B, 180 s / score 0.80 / subida PM >=8 / subida T >=0 | 3 | 0 | 0 |

**Candidato único para la evaluación sellada posterior:** `isolated_enabled=True`, `isolated_persist_s=120`, `isolated_min_fire_score=0.80`, `isolated_min_pm25_rise=8.0`, `isolated_min_temperature_rise=0.0`. Esta selección maximiza detecciones en el grupo de opciones del desarrollo que no producen falsas alarmas en los dos negativos examinados. No es una probabilidad calibrada ni una recomendación de campo.

**Protocolo fijado antes de la siguiente prueba:** semillas **601–612**, nunca usadas en el entrenamiento, validación de umbrales, test anterior o estrés anterior. Se evalúa el candidato fijo contra opción desactivada en:
1. nodo aislado, escenas sintéticas normales;
2. nodo aislado con PM de fondo elevado;
3. nodo aislado con mezcla de partículas gruesas;
4. nodo aislado con humedad elevada;
5. nodo aislado con PM2.5 inframedido un 30 %;
6. red de cinco nodos normales, para verificar que no aparezcan alarmas no corroboradas por efecto secundario.

**Gate predefinido:** exigir cero alertas de prioridad alta sin corroboración en episodios negativos y cero antes de la ignición en las condiciones aisladas normales y de alto fondo, y recuperar por lo menos un episodio real de fuego aislado después de la ignición. Los demás escenarios de estrés revelan debilidades, no se usará el resultado para retocar el candidato sobre las mismas semillas. Si se incumple el gate, conservar el modo desactivado y registrar el rechazo. Una superación limitada seguiría siendo **solo validación sintética**; para incendios reales faltan sensores calibrados y un conjunto independiente de observaciones.

La elección final de *activar el candidato en la demo* requiere además prueba MQTT en Docker del equipo y conformidad de quien mantiene el sistema de avisos.
