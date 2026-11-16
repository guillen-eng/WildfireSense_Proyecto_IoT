# Interfaz de entrega del compañero de escenarios

Este documento NO crea incendios sintéticos ni supone que ya hay etiquetas. La responsabilidad de producir episodios reproducibles es del compañero.

**Por cada ejecución entregará:**
1. readings.jsonl, una lectura JSON por línea con el contrato de docs/MQTT_CONTRACT.md y orden cronológico por nodo, SIN etiquetas.
2. truth.csv, una fila por lectura con run_id,node_id,seq,label,group_id,split. label=1 solo cuando el nodo/instante cumple la definición de fuego sintético acordada. Documentar si significa exposición al humo, presencia del fuego o intervalo de detección; no confundir significados.
3. nodes.csv: run_id,node_id,x_m,y_m y CRS/coordenadas; y un manifiesto con área, viento, foco, semilla, versión, t0 y parámetros de simulación.
4. Descripciones de normal, slow_fire, fast_fire, dust, fog y direct_sun; SOS y fallos de red/sensor son pruebas independientes.

**Separación de datos:** split=train/test se determina por episodios completos, nunca por filas aleatorias. group_id identifica la unidad independiente; series procedentes de la misma plantilla o sesión real deben quedar dentro de un mismo split. Grupos train y test no se solapan; ambos contienen ejemplos positivos y negativos.

**Flujo offline:** readings.jsonl + truth.csv -> ml.build_features -> CSV de 18 features + label/group_id/split -> ml.train_random_forest -> modelo y métricas.

Las features se calculan sin usar la etiqueta; esta se une posteriormente usando (run_id,node_id,seq). Las mediciones invalidas, huecos, reinicios y duplicados deben reportarse. La precisión sobre datos sintéticos NO demuestra detección real de incendios forestales.
