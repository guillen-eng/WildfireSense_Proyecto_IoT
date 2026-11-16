# Auditoría preliminar de los escenarios entregados (semilla 42)

**Fuente:** archivo entregado por el equipo `Escenarios_WildfireSense_datos.zip`, revisado el 16-11-2026. El ZIP original no se incorpora al repositorio hasta acordar publicación/procedencia y tamaño. El conjunto es **sintético**, no incendios observados.

## Inventario comprobado

| Escenario | Mensajes | Nodos | Cadencia virtual base |
| --- | ---: | ---: | --- |
| fuego_lento | 41.160 | 49 | 30 s |
| fuego_rapido | 40.740 | 49 | 5 s |
| polvo_tractor | 9.000 | 25 | 10 s |
| niebla | 7.500 | 25 | 60 s |
| sol_directo | 3.750 | 25 | 60 s |
| fallo_congelado | 3.240 | 9 | 10 s |
| fallo_ruido | 4.860 | 9 | 10 s |
| fallo_silencio | 3.222 | 9 | 10 s |
| sos_boton | 551 | 9 | 60 s; emergencia 5 s |
| **Total** | **114.023** | **zonas locales** | **variada** |

Hay 114.011 mensajes periódicos y 12 mensajes de emergencia. El comprobador incluido `comprobar.py` imprimió `RESULTADO TODO OK` sobre este ZIP; solo comprueba consistencia del generador y sus reglas, **no validez física ni detección con ML**.

La cuadrícula conceptual es de 32×32 = 1024 posiciones a 126 m, pero estos archivos solo contienen ventanas locales de 9/25/49 nodos; **no incluyen 24 horas para 1024 nodos**. Solo hay **una semilla: 42**.

## Formato del compañero y adaptador

Formato original: `id` entero, `ts` y `tx` en milisegundos de tiempo **simulado**, `seq`, `kind` (`periodic`/`emergency`), `v=1`, `boot_id`, `values.PM2.5/PM10/temperature/humidity`.

`ml/import_teammate_scenarios.py` genera **offline**, desde el ZIP o directorio:
- `readings.jsonl`: mensajes del contrato v1 (`run_id, node_id, timestamp, seq, measurements`), **sin etiquetas**, y sin fingir un `emitted_at` real.
- `truth.csv`: etiquetas externas por `(run_id,node_id,seq)`, `group_id`, `split` y `exposure_state`.
- `import_report.json`: auditoría de conversiones, cuentas de clases y escenarios.

Las 12 emergencias no forman parte del entrenamiento ambiental; se validarán por separado como SOS. El adaptador asigna **una etiqueta binaria provisional**: `label=1` después de la **llegada teórica de humo o de frente de fuego** consignada en `nodos_detalle`. `label=0` antes de la exposición o en escenarios no incendiarios. No utiliza el umbral PM2.5=35,5 para etiquetar. Con la semilla 42, el resultado contiene **48.340 positivos y 65.671 negativos**. Esta política de etiquetado necesita aprobación del equipo; el humo modelado puede ser muy débil y no observable en un sensor real. No equivale a una alarma ni a un incendio confirmado.

## Comandos PowerShell, desde la raíz de esta rama

Colocar el ZIP original en `data/Escenarios_WildfireSense_datos.zip` (carpeta local ignorada por Git), preparar entorno Python e importar:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r ml\requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s ml\tests -v
.\.venv\Scripts\python.exe -m ml.import_teammate_scenarios --input data/Escenarios_WildfireSense_datos.zip --output ml/data/semilla42
.\.venv\Scripts\python.exe -m ml.build_features --readings ml/data/semilla42/readings.jsonl --truth ml/data/semilla42/truth.csv --output ml/data/semilla42/features_pending.csv
```

Esto **NO entrena** el modelo: la columna `split` queda `pending`. El entrenador Random Forest exige divisiones válidas por grupos independientes. Para datos de varias semillas reunidos en un ZIP común, se puede pasar `--test-seeds 7,13,19` (solo si existen esas semillas), que mantiene juntas todas las ejecuciones que compartan semilla; el porcentaje y selección de semillas deben quedar registrados en el experimento.

## Problemas a resolver ANTES de estimar calidad del ML

1. **Una sola semilla / dos focos de fuego con forma fija.** No permite una evaluación independiente defendible. Regenerar al menos 30 semillas **y variar parámetros de viento, foco, intensidades, fondo, velocidad y localización**, no solo el RNG.
2. **Cadencias asociadas al escenario.** Fuego rápido a 5 s, lento a 30 s y algunos no-fuego a 60 s. Un modelo puede inferir el tipo de escenario indirectamente por el historial temporal o las diferencias entre lecturas. Generar/normalizar una cadencia base común para los experimentos ML; separar el caso event-driven de la evaluación ML principal. No interpolar ciegamente eventos rápidos a partir de datos a 60 s.
3. **Etiquetas de exposición teórica.** Debemos confirmar qué significa un positivo: pluma modelada, contaminación realmente detectable o fuego que llega al nodo. Conservar por separado `exposure_state` y metadatos de evento.
4. **Independencia espacial/temporal.** No dividir filas aleatoriamente. Particionar por episodio/semilla y reservar escenarios/focos/campañas enteras para pruebas de generalización.
5. **No se prueba la red.** El ZIP fija `tx=ts` simulados y no contiene pérdidas/jitter/duplicados reales de MQTT. Medir eso en experimentos separados.
6. **Validación física pendiente.** Velocidades de frente, atenuación de humo, relaciones PM y variabilidad meteorológica son hipótesis; el checker no las calibra con datos de campo.

El trabajo de Edge AI puede comenzar con `features.py` y pruebas de pipeline. **No desplegar ni atribuir precisión real** al modelo hasta recibir nuevas ejecuciones y cerrar el protocolo.
