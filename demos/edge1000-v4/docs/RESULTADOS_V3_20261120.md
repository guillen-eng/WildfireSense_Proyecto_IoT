# WildfireSense — Mediciones V3 y alcance de verificación (20/11/2026)

## Baseline conservado

La demo offline del modelo `rf-a288fc78989a` permanece inalterada: 1.000 nodos, 47.981 lecturas, 9 preavisos, 9 sospechas corroboradas, 1 SOS y 1 aviso de salud. **La IA entrenada y el detector crítico no han cambiado.**

Las mediciones de 1.000 clientes MQTT con límites de recursos proceden de Docker Desktop del equipo, **sobre Edge1000 anterior a esta extensión**:

| Métrica | Resultado comprobado |
|---|---:|
| Clientes independientes / publicadores | 1.000 / 1.000 |
| Lecturas enviadas / recibidas | 6.000 / 6.000 |
| Carga nominal | 100 msg/s durante 60 s |
| CPU / RAM máxima configuradas para Edge | 0,5 CPU / 512 MiB |
| p95 procesamiento de Edge | 0,900 ms |
| p95 envío → decisión | 8,876 ms |
| OOM | No |

En el ensayo de Cloud desconectada, Edge procesó 47.981 lecturas, 9 sospechas y 1 SOS; la cola creció a 32 entradas (incluye resúmenes) y volvió a cero al reconectar. El histórico pasó de 57 a 76 alarmas. No se debe atribuir a V3 una nueva prueba Docker que no se ha ejecutado.

## Evaluación temporal (60 episodios de incendio reservados)

| Límite desde ignición sintética | ML | Reglas |
|---|---:|---:|
| Hasta 5 min | 30/60 (50 %) | 17/60 (28,3 %) |
| Hasta 15 min | 45/60 (75 %) | 30/60 (50 %) |
| Hasta 30 min | 59/60 (98,3 %) | 32/60 (53,3 %) |
| Hasta 60 min | 60/60 (100 %) | 50/60 (83,3 %) |
| Detección alguna vez durante todo el episodio | 60/60 | 59/60 |
| Episodios negativos con sospecha corroborada | 0/120 | 15/120 |

Generado con `python -m lab.early_detection`, lectura del CSV existente `resultados/episodios_test.csv`. Es evaluación dentro de una familia sintética, **no sensibilidad para incendios forestales reales**.

## Agrupación de eventos (escenarios originales de la semilla 42)

| Escenario | Avisos `suspected_fire` | Grupos propuestos |
|---|---:|---:|
| `fuego_lento` | 218 | 1 |
| `fuego_rapido` | 41 | 2 (40 avisos + grupo aislado de 1) |

Generado con `python -m lab.incident_demo`. La agrupación se basa en celdas vecinas y tiempo; **no identifica un número de incendios reales**. El escenario rápido ilustra que un único episodio simulado puede dividirse en dos grupos bajo esa hipótesis.

## Degradación de comunicación simulada *offline* (40.740 tramas de fuego rápido)

| Pérdida | Duplicación | Jitter máximo | Entregadas | Aceptadas Edge | Rechazadas por orden/duplicidad | Sospechas |
|---:|---:|---:|---:|---:|---:|---:|
| 0 % | 0 % | 0 s | 40.740 | 40.740 | 0 | 41 |
| 5 % | 2 % | 2 s | 39.474 | 38.732 | 742 | 42 |
| 5 % | 2 % | 10 s | 39.474 | 34.055 | 5.419 | 39 |
| 5 % | 2 % | 90 s | 39.474 | 12.259 | 27.215 | 198 |

El escenario de polvo con 5 % de pérdidas, 2 % de duplicados y 10 s de jitter produjo 0 sospechas corroboradas y 8.588 lecturas aceptadas de 8.755 entregadas.

El jitter de 90 segundos es **muy grande respecto al periodo de 5 segundos** del fichero `fuego_rapido`. Esta condición hace que el motor descarte numerosas lecturas tardías, reinicie estados de sensores y genere un patrón de avisos diferente. No debe extrapolarse a todas las redes ni usarse como medida de rendimiento MQTT. Es una prueba adversarial de llegada fuera de orden para priorizar un diseño cuidadoso de buffering/latencia.

## Comprobaciones automatizadas

- **35 pruebas `unittest` superadas** en Python 3.13 local con Paho 2.1.0 disponible. Incluyen 13 tests Cloud previos, lógica Edge, cierre MQTT y los nuevos casos de agrupación, plazos y alteraciones de entrega.
- `python -m lab.demo` mantiene el mismo conteo de eventos.
- `python -m lab.incident_demo` reproduce las cifras anteriores sobre datos originales.
- `python -m lab.early_detection` reproduce el recall por límite temporal desde el CSV existente.
- **Pendiente**: ejecutar el nuevo frontend/API bajo Docker Desktop Windows. El test HTTP del endpoint sí pasa, pero no equivale a comprobar una sesión del navegador.
