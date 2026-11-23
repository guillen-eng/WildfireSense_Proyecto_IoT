# Resultados reproducibles — cierre Edge AI (22 noviembre 2026)

## Fuente y alcance
- GitHub Actions: https://github.com/guillen-eng/WildfireSense_Proyecto_IoT/actions/runs/45045579972
- Commit de la corrida: `a0b35a8949c3aa72b33430d09b142565cbf2dc31`
- **54 tests superados**; barrido de sensibilidad + seis pruebas de estrés ejecutados en Python 3.12, sin reentrenar, modificar `forest.json`, usar Cloud ni medir red radio.
- Artefacto descargable desde Actions: `edge-ai-evidence-v4-a0b35a8949c3aa72b33430d09b142565cbf2dc31`: incluye `configurations.csv`, `episodes.csv`, `study.json`, `stress_summary.csv`, `stress_episodes.csv`, `stress.json`.
- Selección/sensibilidad sobre **301–306**: 12 episodios de incendio y 24 no incendio. Estrés sintético sobre **401–406**: 12 + 24. La evaluación previa sobre **201–230** (60 + 120) se conserva como referencia histórica, no se utiliza para sintonizar.

## 1. Sensibilidad de umbrales (familia sintética conocida)

| Política (solo cambia un parámetro) | Incendios detectados | Negativos con sospecha alta | Negativos con preaviso | Detectados <= 5 / 15 / 30 min | Retardo medio |
| --- | ---: | ---: | ---: | --- | ---: |
| **V4 baseline**: score 0.65, PM2.5 18, ratio 0.36, persistencia 30, vecino 180, reset 60 | **12/12** | **0/24** | **0/24** | **6 / 8 / 12** | **629.99 s** |
| Score 0.55 | 12/12 | 0/24 | 1/24 | 6 / 8 / 12 | 622.32 s |
| Score 0.75 | 12/12 | 0/24 | 0/24 | 6 / 7 / 11 | 742.49 s |
| PM2.5 12 | 12/12 | 0/24 | 2/24 | 6 / 8 / 12 | 610.82 s |
| PM2.5 24 | 12/12 | 0/24 | 0/24 | 6 / 6 / 7 | 1079.99 s |
| Fracción fina 0.25 o 0.45 | 12/12 | 0/24 | 0/24 | 6 / 8 / 12 | 629.99 s |
| Persistencia 10 s | 12/12 | 0/24 | 3/24 | 6 / 9 / 12 | 585.82 s |
| Persistencia 60 s | 12/12 | 0/24 | 0/24 | 6 / 7 / 12 | 712.49 s |
| Vecino 60 o 300 s; limpieza 30 o 120 s | 12/12 | 0/24 | 0/24 | 6 / 8 / 12 | 629.99 s |

**Interpretación honesta:** cambios más permisivos adelantan algo ciertas señales, pero pueden introducir preavisos en negativos. Los resultados invariables ante ratios y ventanas vecinas **no prueban** que los valores 0.36/180 s sean óptimos; esos cortes no quedan identificados con esta familia de datos. No se ha seleccionado un nuevo umbral por este estudio: **la baseline V4 queda sin modificar**, pendiente de acuerdo sobre coste de errores.

## 2. Estrés sintético fuera de los valores habituales del generador (NO campo)

| Perturbación deliberada | Incendios con primera sospecha **tras t0** | Episodios no incendio con sospecha alta | Detecciones <= 5 / 15 / 30 min | Interpretación |
| --- | ---: | ---: | --- | --- |
| Nuevas semillas, sin perturbación | **12/12** | **0/24** | 6 / 9 / 12 | Control dentro de la misma familia |
| Fondo PM2.5 +25 y PM10 +30 µg/m³ | **0/12** | **24/24** | 0 / 0 / 0 | Fuerte fragilidad: genera sospechas en negativos; algunas alarmas ocurren incluso *antes* de la ignición simulada, por lo que `high_detected` post-t0 no equivale a «nunca avisó» |
| PM10 al menos 3.5×PM2.5 | **0/12** | **0/24** | 0 / 0 / 0 | Control adversarial deliberado: ratio ≤0.286 bloquea `fine_fraction >= 0.36`, no prueba frecuencia real de ese tipo de mezcla |
| Humedad forzada >=97% | **10/12** | **0/24** | 5 / 6 / 6 | Pérdida de sensibilidad y aumento fuerte de retardo |
| PM2.5 subestimado multiplicando por 0.70 | **9/12** | **0/24** | 2 / 6 / 7 | Fragilidad a calibración; PM2.5 es clave para filtro y clasificación |
| Un solo nodo transmitiendo | **0/12** con sospecha **corroborada** | **0/24** | 0 / 0 / 0 | **Esperado por diseño**: falta vecino, no autoriza ignorar los preavisos de `advisory` |

**Limitación:** el test transforma lecturas producidas por el mismo generador y no usa medidas reales etiquetadas. No son distribuciones ambientales calibradas ni modelos de mezcla de aerosoles con validación científica; son **sondas de fragilidad**. Los modos `coarse_mixture` y `single_node` se construyeron intencionadamente para comprobar condiciones de rechazo. Sus resultados NO sirven para extrapolar tasas de incendio real.

## 3. Decisión técnica provisional, revisable por el equipo

1. **No sustituir todavía el Random Forest `rf-a288fc78989a`**. El clasificador no es el único origen de las limitaciones: algunos cortes de decisión y la ausencia de un vecino provocan fallos estructurales.
2. **No bajar ciegamente score, PM2.5 o persistencia**: con la validación actual aparecen más falsos preavisos y no desaparece la dependencia del generador.
3. Investigar controles **relativos al fondo local** y datos negativos más diversos, con protocolo fijado antes del test final. No usar las semillas 401–406 para afirmar que un nuevo filtro generaliza; reservar escenarios/semillas nuevos para la evaluación posterior.
4. Para un solo nodo, conservar el `environmental_risk` como `advisory` y dejar explícito que **nunca existe corroboración**. Una alerta alta por un solo nodo requeriría una política distinta, denominada apropiadamente `unconfirmed_high_risk` o similar, nunca `suspected_fire` corroborado.
5. **No fusionar** a V4 antes de decidir la política de alertas y terminar los ensayos de regresión; la PR es borrador.

## 4. Qué falta para cerrar científicamente Edge AI

- [ ] Acordar costes relativos: falso preaviso vs. fuego tardío vs. sospecha alta falsa.
- [ ] Seleccionar estrategia para un nodo aislado (advisory permanente vs. escalado tras evidencia reforzada con etiqueta NO corroborada).
- [ ] Si se decide mejorar robustez al fondo: definir y probar un criterio adaptativo sobre conjunto de desarrollo nuevo; revalidar sobre **conjunto distinto y congelado**, nunca usar el mismo estrés para elegir y evaluar.
- [ ] Documentar sensores físicos que se simulan, sus límites de calibración, qué no se simula (LoRa, energía, campo).
- [ ] CI + Docker E2E con los 1.000 clientes, PDR, p95/p99, memoria, SOS, Cloud desconectada. El trabajo de Cloud y la división en dos portátiles pertenecen a otras PR, no a esta.
