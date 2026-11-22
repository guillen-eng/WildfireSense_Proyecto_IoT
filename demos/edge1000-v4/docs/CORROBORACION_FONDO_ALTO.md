# P0 — Detección corroborada frente a PM ambiental elevado
**Registro del experimento:** 22/11/2026, **antes de ejecutar el barrido nuevo**.

**Problema reproducido:** el baseline V4 clasifica como `suspected_fire` 24/24 episodios negativos en una perturbación sintética adversa `PM2.5 +25, PM10 +30 µg/m³` aplicada en toda la malla. Dos vecinos afectados por la misma contaminación **no constituyen evidencia independiente de incendio**.

**Hipótesis:** además de la evidencia absoluta clasificada por RF y persistencia (V4), exigir para **ambos nodos** una subida temporal reciente de PM2.5 filtrado respecto a su propio fondo lento (`pm25_fast - pm25_slow`) reducirá las alarmas provocadas por fondos altos persistentes. La señal debe registrarse *causalmente*, sin datos futuros, y caducar. Esta puerta únicamente condicionará `suspected_fire`, sin silenciar `environmental_risk`, `unconfirmed_fire_risk` B2 ni SOS.

**Por qué:** la EPA recomienda observar tendencias del PM2.5 para reconocer cambios en humo, pero **no** establece un umbral de ignición; las altas concentraciones también pueden tener fuentes no forestales y los sensores ópticos requieren calibración. Véase:
- EPA (2026), *Using Air Quality Sensors for Smoke: Understanding Sensor Data*: https://www.epa.gov/system/files/documents/2026-06/air-quality-sensors-for-smoke-factsheet.pdf
- Holder et al. (2020), *Field Evaluation of Low-Cost Particulate Matter Sensors for Measuring Wildfire Smoke*, https://doi.org/10.3390/s20174796
- Beatriz Soret, *Module 3 — Project Guidelines*, pp. 2–4: evaluación cuantitativa de Edge AI y latencia.
Ninguno prescribe la cifra de subida (2/4/8 µg/m³) ni el TTL de este experimento.

## Código y límites

- Se añade un `DetectionPolicy.corroboration_trend_enabled=False` **desactivado por defecto**. El bosque `rf-a288fc78989a` y el contrato de mensajes **no cambian**.
- Registrar última hora por nodo en que hubo una subida PM rápida-lenta >= corte, siempre que el nodo esté sano y con señal de fuego ML.
- Proponer `min_rise ∈ {2, 4, 8} µg/m³` y `trend_ttl ∈ {180, 300, 600} s` (nueve configuraciones) en un **conjunto de desarrollo nuevo**: semillas **901–906**, por episodios separados, en los seis escenarios originales y perturbaciones `high_background`, `coarse_mixture`, `high_humidity`, `pm25_underread`. Selección sin ponderar literalmente 24/24 como datos reales.
- Si solo hay un nodo sin vecino, el gate corroborado continúa sin poder crear `suspected_fire`. B2 sigue siendo su propio mecanismo experimental y no cambia.
- No se activará en el gateway hasta demostrar mejoras. El experimento siempre generará CSV con baseline y cada candidato.

## Criterios prefijados de selección (desarrollo)

Prioridad 1: **cero episodios negativos** con `suspected_fire` en modo `high_background` y sin incremento de falsos positivos respecto a baseline en `normal`.

Prioridad 2: conservar detección de al menos 10/12 episodios de fuego de la familia normal de 901–906 y limitar la pérdida de detecciones por 15 minutos a un máximo de 2 respecto a V4.

Prioridad 3: si varias alternativas cumplen, preferir la menor demora p95 y el valor mínimo que proteja contra falso fondo, para no imponer cortes innecesarios. Desempate: mayor detección temprana, luego valor de corte más pequeño. **Si ninguna cumple, no activar ninguna.**

## Test sellado (si hay candidato)

- Semillas **1101–1112**, sin uso anterior, nuevo ensayo de una sola configuración seleccionada con los datos de desarrollo.
- Para aprobar el modo de **demo sintética** debe mantener 0 episodios negativos con `suspected_fire` en `normal` y `high_background`, detectar >=20/24 incendios originales, y no perder más de 4 detecciones antes de 15 minutos respecto a la baseline. Se registrarán además falsas detecciones **antes de ignición** y robustez en `coarse_mixture`, `high_humidity`, `pm25_underread`.
- Si falla, el modo permanece desactivado; **no reajustar parámetros con el test sellado**.

**Alcance:** sigue siendo un generador sintético perturbado. La decisión NO certifica detección de incendios forestales reales; exige calibración y evaluación externa para desplegarla fuera de clase.

**Integración:** este trabajo se crea apilado sobre la PR #9 para no pisar Cloud PR #7 ni la topología de 2 portátiles PR #8.
