# Reproducción y contrato

Todos los comandos se ejecutan desde la raíz. Usa Python 3.12. Se puede sustituir `python` por `py -3.12` en Windows. Los ficheros de métricas entregados están en `resultados/`; utiliza otro directorio para guardar una repetición cuando el comando admita `--out`.

## Inferencia y evaluación

```bash
python -m lab.demo
python -m unittest discover -s tests -v
python data/scenarios/comprobar.py data/scenarios
python -m lab.evaluate --out resultados/nueva_prueba
python -m lab.evaluate --originales --out resultados/nueva_prueba
python -m lab.scale
```

El peso entrenado está en `models/forest.json`. El motor lee los árboles exportados y usa la biblioteca estándar. El comprobador original verifica los ficheros del compañero. El evaluador calcula métricas por muestra y por episodio. El escalado local incluye el coste de generar datos y procesarlos; su rendimiento no incluye MQTT. Los tiempos de ejecución varían entre máquinas.

- **Clasificación.** Seis clases, ventana causal de medias exponenciales con constantes de 30 y 300 s; ocho variables derivadas de partículas, temperatura y humedad. Ninguna variable usa un valor futuro, nombre de escenario, id, hora absoluta, etiqueta o bandera de evento. La etiqueta sintética de fuego comienza con la llegada teórica de humo o frente al nodo, incluso si la señal todavía es débil. Los nodos periféricos y las curvas casi sin cambio dificultan la clasificación por muestra.
- **Diseño.** Seis familias por semilla; cinco nodos por episodio de aprendizaje. Se conserva la relación espacial de los cinco perfiles y se varían el foco y la orientación. Las etiquetas de polvo, sol y niebla se asignan por intervalo físico simulado. El archivo de escenarios del equipo se reserva para una prueba adicional. El entrenador usa muestreo por clase dentro de cada semilla, pesos de clase equilibrados, 19 árboles, profundidad máxima 8 y hojas de al menos 14 ejemplos.
- **Métricas.** `confusion.csv` contiene filas de clase verdadera y columnas de clase predicha. Macro-F1 da el mismo peso a cada clase. En `episodios_test.csv`, una celda vacía en el retardo representa ausencia de ese aviso. El retardo usa tiempo virtual desde t0 y la primera sospecha corroborada en cualquier nodo. Las medias de retardo solo incluyen incendios detectados. Los falsos positivos del resumen son episodios negativos con alguna sospecha corroborada. Un preaviso se analiza por separado. En `escenarios_equipo.csv` se dan también recuentos y resultados del canal de salud y del SOS.
- **Comparación justa.** El clasificador y las reglas ambientales evalúan exactamente la misma secuencia. Ambos usan la misma persistencia, malla, estados de salud y confirmación espacial. Las reglas comparan PM2,5 filtrada con 35,5, razón con 0,30 y HR con 90 % o cambio térmico con 1,5 °C. El detector Z-score histórico empleaba flujo de calor y queda en la copia Git de referencia.
- **Integración.** El punto de entrada efectivo es `python -m edge.main`. `Engine.handle` valida, rechaza paquetes repetidos o atrasados, mantiene el historial por ejecución/nodo y evalúa. `lab/demo.py`, MQTT y el replay de los JSONL llaman a ese punto común. El entrenamiento usa el mismo extractor de variables.

## Modelos y datos revisados

Para volver a entrenar de forma determinista desde el generador, instala `lab/requirements-train.txt` en un entorno virtual, o usa el servicio de entrenamiento.

```bash
docker compose run --rm --build trainer
docker compose run --rm trainer python -m lab.evaluate --model /exchange/candidate.json --validation --out /exchange/validacion
docker compose run --rm promote
docker compose restart edge
```

El primer comando escribe `candidate/candidate.json`. La evaluación de candidato utiliza semillas 301–306 independientes del test de la entrega (201–230). Revisa los fallos, falsas alarmas, latencia y cambios de macro-F1 antes de escogerlo. `promote` verifica el contrato, el hash, la forma de los árboles y ejemplos de inferencia; después sustituye atómicamente el fichero de pesos. El reinicio del gateway vuelve a cargarlo y comienza un historial de filtros nuevo. Para recuperar la versión entregada, copia `models/forest.json` desde el ZIP y reinicia Edge.

Equivalente local: `python -m lab.train --output candidate/candidate.json` y `python -m lab.promote candidate/candidate.json`. El proceso de exportación compara las predicciones con scikit-learn antes de escribir el candidato. En esta entrega se repitió el entrenamiento y se comprobó igualdad de los bytes del modelo.

Para incorporar histórico nuevo, un revisor debe proporcionar `candidate/reviewed.jsonl`. Cada línea lleva `group` (grupo de entrenamiento con prefijo `reviewed-train-`), `class` (una de las seis clases) y `message` (telemetría v1 sin etiqueta). Mantener una ejecución en un único grupo, con series ordenadas y sin filas compartidas con validación/test. Por ejemplo, si una medición ha sido revisada, la estructura es:

```json
{"group":"reviewed-train-campana-A","class":"normal","message":{"schema_version":1,"type":"reading","run_id":"campana-A","node_id":"node_0001","seq":1,"timestamp":"2026-07-15T08:00:00Z","timebase":"wall","measurements":{"pm25_ug_m3":8,"pm10_ug_m3":16,"air_temperature_c":21,"relative_humidity_pct":58}}}
```

```bash
docker compose run --rm trainer python -m lab.train --extra /exchange/reviewed.jsonl --output /exchange/candidate.json
docker compose --profile periodic up -d --build retrain
```

El servicio opcional comprueba el histórico una vez al día y genera un candidato cuando cambia el contenido. El panel no etiqueta automáticamente las lecturas; el histórico agregado no permite reconstruir las señales por sensor. Se promueven solo candidatos revisados. Este ciclo funciona en el laboratorio mediante carpeta compartida. Para dos máquinas físicas se debe definir el transporte y la verificación de los artefactos.

## Transporte y almacenamiento

| Tema MQTT 3.1.1 | Emisor y consumidor | QoS y comportamiento |
|---|---|---|
| `wildfiresense/readings/node_XXXX` | Sensor → Edge | QoS 0. Telemetría v1, campos y unidades en `telemetria_v1.json`. Se conservan `seq`, `run_id`, `boot_id` si existe y reloj. |
| `wildfiresense/events/sos` | Pulsador → Edge | QoS 1, `type=sos` o `kind=emergency` en raw. Sale inmediatamente, con independencia de la confianza del clasificador. |
| `wildfiresense/edge/alerts` | Edge → receptor y usuarios locales | QoS 1, `type=environmental_alert` con `decision=environmental_risk` o `suspected_fire`; `type=sos_alert` para SOS. Las sospechas incluyen el vecino y las señales. |
| `wildfiresense/edge/health` | Edge → mantenimiento local | QoS 1. Transiciones OK, SOSPECHOSO o FALLO. Permanecen en la base del Edge. |
| `wildfiresense/cloud/analysis` | Edge → histórico central | QoS 1. Una muestra de cada diez entradas válidas a nivel de flota; ventana de 5 s reales o 512 valores. Con enlace disponible, la nube recibe esas PM2,5 y calcula media/máximo; con enlace degradado, el Edge calcula y guarda el resumen. |
| `wildfiresense/edge/ping`, `wildfiresense/cloud/pong` | Edge ↔ aplicación central | Eco cada 2 s. Enlace disponible si el último eco tiene ≤6 s de antigüedad y RTT ≤250 ms; incluye retardo de aplicación. |
| `wildfiresense/cloud/ack` | Receptor → Edge | Acuse de aplicación tras escritura en SQLite. Permite vaciar la cola y tolerar el reenvío QoS 1. |
| `wildfiresense/edge/status` | Edge → observador | Estado retenido y actualizado cada 2 s. Incluye modelo, nodos, latencia, huecos, CPU, bytes y acuses pendientes. |

Cada lectura del simulador tiene `sent_unix_ns` del instante real inmediatamente anterior al PUBLISH. El gateway añade a los avisos `rx_ts` al entrar en el callback y mide por separado el tiempo de decisión. Se presupone un reloj compartido en el laboratorio. El timestamp del fenómeno y el del transporte permanecen separados. La latencia envío → fin de callback incluye espera de red y cálculo (en eventos también la persistencia local), pero excluye la visualización en pantalla. El p95 de proceso se toma al terminar la decisión, antes de persistir/publicar. La retención para percentiles está acotada a 50.000 muestras; en la prueba nominal abarca las 6.000 lecturas. El motor retiene hasta 4.096 pares ejecución–nodo; las expulsiones se contabilizan. La secuencia de un nuevo arranque se admite si avanza el instante de medición. Los mensajes fuera de orden se descartan. La salud por silencio solo cubre nodos vistos previamente. Para supervisar sensores que nunca llegan a arrancar se necesitaría un inventario de instalación y plazo de puesta en marcha.

Las muestras operativas del reenvío no contienen coordenadas. Las ventanas usan muestreo sistemático a nivel de flota; si interesan máximos por nodo, hay que definir otro muestreo. Las ventanas sin cerrar están en memoria. Los avisos y resúmenes cerrados sobreviven a un reinicio. Se guarda su histórico en SQLite; hay que acordar política de retención para meses de operación. En esta versión el escenario por botón incluye secuencias repetidas del mismo incidente humano y se conserva una salida por secuencia nueva.

## Repetir la verificación por TCP y los bytes de MQTT

Instala el cliente local con `python -m pip install --no-index -r requirements.txt` desde la raíz. Necesitas además el ejecutable del broker Mosquitto 2.x en el PATH para estos dos comandos. En Ubuntu se puede instalar el paquete `mosquitto`; en Windows también puedes indicar `--broker "C:\Program Files\mosquitto\mosquitto.exe"`. El laboratorio automatizado con 1.000 sockets se ha probado en Linux (selectors/epoll); para Windows usa el contenedor Linux del simulador en Docker Desktop para la carga de 1.000 conexiones.

```bash
python -m lab.verify_stack --out resultados/mi_red
python -m lab.measure_wire --out resultados/mi_red/tramas.json
```

El primer comando usa puertos libres y bases temporales. Arranca el broker, la nube y el Edge, ejecuta primero un minuto nominal con 1.000 clientes, apaga el receptor central, ejecuta fuego rápido a ×12 con 1.000 clientes, vuelve a arrancar la nube y verifica igualdad de identificadores entre ambas bases. La prueba distingue el fallo de la nube del fallo del broker local. El segundo comando cuenta bytes reales de los dos flujos TCP con un intermediario local instrumentado en una prueba corta. Desglosa PUBLISH, CONNECT, CONNACK, PUBACK y DISCONNECT. En una captura adicional con Wireshark puede usarse el filtro `mqtt` o `tcp.port == 1883` en la interfaz del broker. La captura de tramas Ethernet, IP, TCP, retransmisiones y radio queda fuera de estas cifras.

En el ensayo nominal, `in_publish_bytes` reconstruye el tamaño de PUBLISH de recepción y `up_publish_bytes` suma los PUBLISH de avisos y analítica hacia el broker (incluidos reintentos). Para comparar con enviar todo continuadamente se puede dividir ambos. Ese cociente describe tráfico de aplicación durante la ventana, excluye heartbeat/estado/ACK y no mide energía. La prueba corta `tramas_mqtt.json` es una medición directa independiente.

## Integración en el repositorio del grupo

El directorio raíz de este ZIP es una copia ejecutable para la demo. Las ramas públicas de origen están enumeradas en `referencia/revisiones.txt`; el bundle conserva sus objetos Git. Para revisar sin modificar el repositorio remoto, desde un repositorio Git local usa `git bundle list-heads ruta/al/WildfireSense_origen.bundle`. Para integrar en el repo compartido, conviene crear una rama a partir de main, mantener `data/scenarios/` y revisar en una PR el nuevo servicio, el contrato y los cambios del dashboard. En la copia del generador se movió la lectura de argumentos bajo la guarda de script para poder importar las ecuaciones. Los nueve JSONL y sus verdades mantienen los bytes de origen. Las cifras del antiguo MVP y de los experimentos de flujo de calor se documentan por separado de esta evaluación.
