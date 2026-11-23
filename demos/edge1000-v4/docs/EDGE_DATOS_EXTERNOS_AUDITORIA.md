# Auditoría externa de datos — decisión sobre Edge AI V4
**Fecha:** 23/11/2026. **NO cambia** el Random Forest `rf-a288fc78989a`, los tópicos MQTT ni el modo de alarmas. Los archivos crudos no se suben al repositorio.

## Dictamen
Los datasets externos aportan mediciones físicas reales y datos de calidad instrumental, pero **ninguno** contiene PM2.5, PM10, temperatura y humedad **medidos conjuntamente** más una etiqueta de incendios independientes de las alarmas de los sensores. No es válido introducirlos en el RF V4 rellenando PM10 con una fórmula y presentar el resultado como validación real. Los modelos se mantienen en simulación hasta evaluar datos externos apropiados.

## Fuentes efectivamente inspeccionadas

| Archivo aportado | Tamaño útil | Entradas y etiquetas | Uso válido |
| --- | --- | --- | --- |
| RESISTO `indendios_timerseries_zenodo_202411151103.csv` | **497.749** filas, **229** sensores, **4** sitios | Temp., RH, presión y ubicación; `fire_alert_status`: 0=496.789, 1=4, 2=956 | Distribuciones reales, control de calidad y salud. **No** contiene PM2.5 ni PM10; estado 2 **no significa ignición verificada** |
| `Final_phase_I_public_data.xlsx` | **1.680** registros, resolución un minuto, 28 series | PM2.5, CO, CO2 y T/RH de cámara; aerosoles y gases generados **sin combustión** | Prueba de contaminación alta sin fuego, NO clase negativa natural del bosque |
| `Final_phase_II_public_data.xlsx` | **1.987** registros, un minuto, **33** quemas | PM2.5, CO, CO2, T/RH y `burn` | Señal real de humo de biomasa controlada; **no PM10 ni instante exacto de ignición por fila** |
| `AE_paper_10_sec_data.xlsx` | **12.176** filas, 10 s, **58** identificadores `burn` | CO, CO2, NOx, CH4, HCN y otros gases; sin partículas | Explorar CO/CO2 fuera del RF V4 |
| `konza_2017_11_10.csv` | **196** filas, un minuto | CO, CO2, NO2, referencias y sensores | Comparación de gases en plumas de quemas prescritas, sin PM |
| `tallgrass_2017_11_15.csv` | **251** filas, un minuto | CO, CO2, NO2, referencias y sensores | Comparación de gases en otra jornada, sin PM |
| `63343.pdf` | 10 páginas | Landis et al. (2021), artículo base de EPA Phase I/II | Justificar sesgo de sensor y necesidad de calibración |

**Calidad RESISTO:** humedad `-1` en **277.092/497.749 (55,67 %)**; **68** fechas en año 2000; **12.905** coincidencias sensor+timestamp (IDs de fila no duplicados). La mediana de las medianas de intervalos **por sensor** es ~3.583 s; por tanto, no es una malla de sensores reales cada 10 s. MD5 del CSV = `75a9b666692241e847dd084deb5bf22d`, idéntico al publicado por Zenodo.

**Resultado EPA concreto:** En Fase I, **1.367/1.680 (81,4 %)** de las medidas de referencia tenían PM2.5 >=35,5 ug/m3 **sin fuego**; en Fase II, **1.880/1.987 (94,6 %)** con humo. Este es un **conteo de PM**, NO una predicción ni falso positivo del RF. Concentraciones medianas: Fase I PM2.5 ~266,3 ug/m3 y CO ~11,7 ppm, Fase II PM2.5 ~274,9 ug/m3 y CO ~2,63 ppm. Fase I incluye gases inyectados deliberadamente, de modo que entrenar `Fase I = negativo` frente a `Fase II = fuego` tendría confusión de dominio severa. En las **33 quemas** Phase II, la correlación descriptiva de medianas por episodio PM2.5 vs CO es **r≈0,485**; no prueba mejora de un clasificador.

**Metadata:** los archivos EPA publican PM2.5 como «micrograms per cubic meter (mg m-3)», incongruencia en la abreviatura; el artículo expresa ug/m3. Zenodo describe presión en hPa mientras el campo termina en `_pa` y los valores son ~101000 (Pa). No cambiar unidades sin documentar.

## Decisiones para cerrar Edge

1. **No añadir CO/CO2 ahora**: cambiaría contrato, extracción de 8 features, entrenamiento, test, latencia/carga y documentación sin prueba de mejora. CO es hipótesis de V5, que requerirá datos medidos simultáneamente PM2.5+PM10+T+RH+CO y etiquetas por incendio verificadas externamente.
2. **No reentrenar V4** con los datasets aportados; seguir con `rf-a288fc78989a`. El gate de entrenamiento ya rechazó un candidato inferior con +7.634 muestras sintéticas, prueba de control de calidad, NO generalización a campo.
3. **Mantener V4 y B2 opcional**: el RF+filtros+persistencia+vecino sano funciona en demo; B2 solo produce evento `unconfirmed_fire_risk`, no incendio corroborado.
4. **Documentar Issue #11 sin solución**: PM de fondo elevado en toda la malla puede disparar `suspected_fire`. Dos mitigaciones dejaron pérdidas inaceptables de sensibilidad y se rechazaron (PR #12). Los nuevos datos confirman la ambigüedad física, no corrigen automáticamente la IA.
5. **Solo cierre técnico pendiente**: repetir la carga **1.000 clientes ×60 ciclos = 60.000** mensajes durante 10 min, guardar PDR, p95/p99, CPU/RAM/OOM/SQLite y revisar PR #9 + integración Cloud del equipo. En el portátil ya se demostró 1.000×6 (6.000/6.000), fast_fire 47.981/47.981 y 9 sospechas con SOS, B2 con alerta no corroborada.
6. **No presentarlo como sensor forestal validado**, sino como sistema completo IoT de detección experimental de anomalías compatibles con humo, conforme a Track A de la asignatura. No se probó radio física ni 1.000 nodos reales.

## Fuentes
- B. Soret, *Module 3 — Project Guidelines*, 2026, pp. 3–4 (Track A); *Module 1 IoT Part I*, pp. 71–73 (MQTT).
- IREC, Zenodo RESISTO, https://doi.org/10.5281/zenodo.14169469
- M. S. Landis et al., *Atmospheric Environment* 247 (2021) 118165, https://doi.org/10.1016/j.atmosenv.2020.118165
- EPA, https://catalog.data.gov/dataset/final_wildland_fire_sensor_challenge_public_data
- EPA, https://catalog.data.gov/dataset/chamber-study-2021-measurement-data
- EPA/Whitehill, https://catalog.data.gov/dataset/summary-of-evaluation-of-commercially-available-air-sensor-performance-in-biomass-burning-
- PR #9, PR #12, Issues #10, #11, #13 — https://github.com/guillen-eng/WildfireSense_Proyecto_IoT
