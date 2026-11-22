# Cierre del experimento P0 — PM de fondo alto y falsas sospechas
**22/11/2026** | Basado en `feature/edge-ai-evidence-freeze` (PR #9) | PR experimental #12 | Issue #11 permanece abierta.

## 1. Problema real del prototipo, no validación de campo

En la familia de escenas sintéticas con un *desplazamiento aditivo global* (PM2.5 +25, PM10 +30 µg/m³) sin incendio, V4 puede emitir `suspected_fire` en **24/24 episodios negativos**. El detector interpreta dos nodos con partículas elevadas como evidencia suficiente; ambos pueden estar afectados por una misma fuente de contaminación. Esto **no significa que el sistema tenga 100 % de falsas alarmas en incendios reales**: es un test adversarial definido por el equipo que demuestra que la corroboración espacial no ofrece especificidad universal.

Los escenarios usan un único generador con perturbaciones artificiales. El `high_background` NO incorpora cinemática aerosol validada, ni sensores calibrados.

## 2. Comparación reproducible de hipótesis

### Fase 1 — subida de PM2.5 causal en ambos vecinos, semillas 901–906
Fuente: [GitHub Actions #45050548439](https://github.com/guillen-eng/WildfireSense_Proyecto_IoT/actions/runs/45050548439). 70 tests correctos.

| Configuración | Incendios detectados en normal (12) | Negativos de PM de fondo alto con `suspected_fire` (24) |
| --- | ---: | ---: |
| Original V4 | 12 | 24 |
| Subida PM >=2 µg/m³, TTL 180–600 s | 12 | 24 |
| Subida PM >=4 µg/m³, TTL 180 s | 12 | 18 |
| Subida PM >=8 µg/m³, TTL 180–600 s | 7 | 3 |

**Resultado**: ningún candidato cumplió la exigencia de 0 falsas sospechas y >=10/12 incendios detectados. No se seleccionó ninguno.

### Fase 2 — PM2.5 en dos vecinos + aumento de temperatura en al menos uno, semillas 921–926
Fuente: [GitHub Actions #45050854776](https://github.com/guillen-eng/WildfireSense_Proyecto_IoT/actions/runs/45050854776). 71 tests correctos.

| Configuración (subida PM / subida T) | Incendios detectados (12) | Negativos de fondo alto con sospecha (24) | Detectados antes de 15 min |
| --- | ---: | ---: | ---: |
| Original V4 | 12 | 24 | 11 |
| >=2 µg/m³ / >=0.25°C | 11 | 22 | 11 |
| >=4 µg/m³ / >=0.25°C | 11 | 10 | 10 |
| >=4 µg/m³ / >=0.5°C | 6 | 1 | 6 |
| >=8 µg/m³ / >=0.5°C | 6 | 0 | 6 |
| >=8 µg/m³ / >=1.0°C | 6 | 0 | 6 |

**Resultado**: el candidato con 0 falsas sospechas detecta solo 6/12 fuegos sintéticos; cae por debajo de los criterios fijados (>=10/12, sin pérdida excesiva de detección temprana). El clima, la distancia y el transporte de humo pueden no calentar el termómetro. **No hay candidato para test sellado**, porque ninguno superó la puerta de desarrollo. No se miraron las semillas reservadas 1121–1132.

## 3. Decisión y razón técnica

**No se activará ninguno de estos dos filtros en el gateway MQTT.** No sería honesto afirmar que hemos solucionado el problema cambiando un umbral: la reducción de falsos positivos implica perder demasiados incendios.

- `DetectionPolicy.corroboration_trend_enabled=False` conserva las decisiones V4 por defecto; `models/forest.json` versión `rf-a288fc78989a` permanece igual.
- El constructor `Gateway` **rechaza** `EDGE_CORROBORATION_TREND_GATE=1` en lugar de arrancar un filtro no validado.
- El motor de laboratorio todavía permite `Engine(policy=DetectionPolicy(...))` para reproducir la evaluación de ambos enfoques y analizarlos. Las hipótesis, semillas y resultados siguen guardados.
- Las alertas `environmental_risk`, `suspected_fire` y SOS mantienen su contrato existente en modo conservador. La nueva política B2 para nodos aislados es un experimento distinto y sigue siendo optativa.

**No declarar `suspected_fire` un incendio confirmado:** es un aviso de *sospecha de fuego según el simulador*, que debe revisarse. Una anomalía persistente de partículas exige intervención/inspección, pero no se puede atribuir de forma inequívoca a una combustión con estos cuatro canales.

## 4. Fuentes e implicaciones

1. U.S. EPA, *Using Air Quality Sensors for Smoke: Understanding Sensor Data* (2026): https://www.epa.gov/system/files/documents/2026-06/air-quality-sensors-for-smoke-factsheet.pdf — indica que deben examinarse tendencias de PM2.5 en el tiempo y que las lecturas de sensores por sí solas no identifican con certeza el origen del humo.
2. Holder et al. (2020), *Field Evaluation of Low-Cost Particulate Matter Sensors for Measuring Wildfire Smoke*, Sensors 20, 4796; https://doi.org/10.3390/s20174796 — demuestra necesidad de corrección/calibración específica y problemas por condiciones ambientales.
3. Beatriz Soret, *Module 3 — Project Guidelines*, pp. 2–4 — se exige modelo ligero en Edge, análisis cuantitativo de latencia y errores, reparto Edge/Cloud y justificar decisiones, **no garantizar sensibilidad de campo**.

**Consecuencia para el informe:** PM2.5, PM10, temperatura y humedad son suficientes para mostrar un *detector experimental de anomalías compatibles con humo*, pero no una prueba inequívoca de incendio. Para mejorar especificidad sin ocultar humo frío, hacen falta **datos externos etiquetados y sensores calibrados**, y quizá otra modalidad física (por ejemplo, medida de gases o infrarrojo térmico) con valoración de coste, energía y alcance. No añadir sensores ficticios en la implementación actual.

## 5. Qué queda en el Edge para la entrega

- Repetir una clonación limpia en el PC de la demo; comprobar 1.000 clientes MQTT, 0.5 CPU / 512 MiB, PDR y p95; SOS y aislamiento de Cloud.
- Mantener la limitación documentada en informe y diapositivas; no presentar métricas sintéticas como rendimiento de incendio real.
- Trabajar con la persona de Cloud para que el panel represente `unconfirmed_fire_risk` B2 como **NO corroborado** (issue #10), sin confundirlo con sospecha corroborada.
- No usar test sellado 1121–1132 para continuar iterando en esta entrega; permanecerá sin mirar al no haber candidato aprobado.

**Conclusión:** el problema se ha medido y caracterizado, pero **no corregido** dentro de los criterios predefinidos. El resultado defendible es una limitación explícita y reproducible, no afirmar una solución inexistente.
