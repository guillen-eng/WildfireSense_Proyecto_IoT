# WildfireSense V4 — Reentrenamiento controlado y validación de candidatos

## Por qué es necesario

La guía de Module 3 (Track A, pp. 3–4) identifica **seis componentes**. El sexto es la IA en Cloud: reentrenar sobre histórico revisado y distribuir nuevas versiones. En V3 ya había `lab.train`, `lab.refresh` y `lab.promote`, pero faltaba impedir que una versión de peor calidad sustituyera el detector desplegado.

Esta V4 añade una **puerta de validación (model gate)** y separa los papeles:

1. **Edge**: modelo actual `models/forest.json`, inferencia local, SOS siempre independiente.
2. **Reentrenamiento**: servicio `trainer` / proceso `retrain` con `scikit-learn` fuera del Edge. Solo recibe archivos etiquetados para entrenamiento, separados de mensajes MQTT y de etiquetas de los tests.
3. **Candidato**: `candidate/candidate.json` identificado por un hash corto de contenido (`rf-...`); **no es una firma criptográfica de autenticidad**. No queda automáticamente desplegado.
4. **Validador**: `validator` compara el modelo actual y el candidato sobre semillas **301–306** destinadas a selección de modelos. Las semillas 201–230 quedan reservadas para test final. No se usan muestras individuales aleatorias del mismo episodio en ambos lados.
5. **Promoción**: el servicio `promote` ahora ejecuta el mismo gate y **solo escribe el modelo si pasa las condiciones**. La decisión de ejecutar ese servicio sigue siendo humana. Para cargar el nuevo modelo hay que reiniciar el contenedor Edge; no hay actualización automática en caliente.

### Criterios experimentales de promoción

- `macro-F1 candidato >= macro-F1 actual - 0,01` (caída máxima absoluta 1 pp).
- `accuracy candidato >= accuracy actual - 0,01` (caída máxima 1 pp).
- Ningún episodio de incendio menos detectado en el conjunto de validación.
- Ningún episodio negativo adicional con sospecha corroborada.
- Retraso medio de las detecciones **no más de 10 s peor** que el actual.
- Comprobación de integridad y estructura: versión/hash, contrato de ocho características, árboles acíclicos, probabilidades de hojas.

Son **criterios de laboratorio**, no umbrales legales, de seguridad ni garantía de generalización. Para un despliegue físico se deben revisar con datos independientes y análisis de seguridad.

## Demostración reproducible en Docker Desktop

Todos los comandos se ejecutan desde la carpeta V4. Es posible usar el límite opcional de Edge, pero el servicio de entrenamiento está separado. El contenedor `training` necesita Internet para instalar los paquetes científicos la primera vez; el **Edge no necesita esos paquetes**.

```powershell
# Solo si se quiere probar el circuito Cloud AI; no afecta a la IA actual
# 1) Construir la imagen de entrenamiento
# Usa el proyecto Compose V4 completo, no mezclado a ciegas con V3

docker compose --profile training build trainer

# 2) Generar un histórico SIMULADO y etiquetado, únicamente para comprobar
# que el flujo de entrenamiento funciona. No son datos de campo revisados.
docker compose --profile training run --rm trainer python -m lab.make_reviewed_demo --out /exchange/demo_synthetic.jsonl

# 3) Entrenar otro candidato, todavía sin desplegar
docker compose --profile training run --rm trainer python -m lab.train --output /exchange/candidate.json --extra /exchange/demo_synthetic.jsonl

# 4) Validar contra el modelo activo. En este ejemplo es esperable el rechazo:
# el candidato observado baja la accuracy y tarda más en detectar.
docker compose --profile training run --rm validator

# Consulta candidate/gate_report.json. Si "approved": false,
# NO ejecutar promote. No se ha tocado models/forest.json.
```

**Atención:** `lab.make_reviewed_demo` escribe en modo **creación exclusiva**; no sobrescribe un archivo ya existente. Para repetir la generación, cambia el nombre del archivo o elimina explícitamente la copia generada. Nunca reemplace un `reviewed.jsonl` real con datos de demostración.

Para comprobar un candidato idéntico al actual (caso sin nuevos datos), puedes entrenar usando las semillas de entrenamiento sin `--extra`. El gate debería aprobarlo, pero la promoción sería un **no-op** porque la versión no cambia:

```powershell
docker compose --profile training run --rm trainer
# Nota: este comando sustituye candidate/candidate.json, no models/forest.json.
docker compose --profile training run --rm validator
```

### Proceso real recomendado cuando existan etiquetas revisadas

1. Guardar **datos ambientales con sus etiquetas verificadas externamente** en `candidate/reviewed.jsonl`, sin utilizar las predicciones del detector como verdad de terreno.
2. Hacer que `retrain` (`--profile periodic`) lea ese histórico. El proceso requiere revisión humana y controles de privacidad, integridad y procedencia. No implementar aún scraping o autoetiquetado.
3. Revisar `candidate/gate_report.json` y dejar registro de la decisión humana.
4. Solo si está aprobado, ejecutar `docker compose --profile training run --rm promote` para promover de forma atómica.
5. Ejecutar `docker compose restart edge` para cargar la nueva versión; confirmar `model` en el tópico `wildfiresense/edge/status` y probar SOS + fuego rápido + confusores. La reinicialización del proceso borra estados en RAM, por lo que la promoción debe programarse fuera de un incidente real.
6. El proceso `promote` crea una copia de la versión previa con nombre `models/forest.rf-<digest>.json` antes de reemplazar el modelo activo. Para revertir se requiere seleccionar manualmente esa versión y reiniciar Edge. **No se ha implementado rollback automático ni firma digital de distribución**.

## Ensayo realizado en esta entrega

- Histórico de demostración: **7.634 observaciones 100 % sintéticas**, semilla 125, escenarios `fast_fire`, `slow_fire` y `dust`. Esta semilla no aparece en entrenamiento original (101–124), prueba (201–230) ni validación (301–306).
- Candidato entrenado: `rf-ce396a5fd4c2` (207.873 bytes); original `rf-a288fc78989a`.
- En las 36 escenas de validación: baseline accuracy 81,36 %, macro-F1 76,03 %, 12/12 incendios detectados, 0/24 negativos; tiempo medio 629,99 s.
- Candidato: accuracy 79,77 %, macro-F1 75,96 %, 12/12 incendios detectados, 0/24 negativos; tiempo medio 654,15 s.
- **Gate: RECHAZADO**, por caída de accuracy mayor que 1 pp y retraso medio adicional de 24,16 s. El modelo original se mantiene.

Ese rechazo es **una mejora del proceso de ingeniería**, no una mejora de precisión del detector. Un candidato entrenado con más datos sintéticos no tiene por qué funcionar mejor.

## Fuentes técnicas

- Material docente, *Module 3 — Project Guidelines*, Track A, pp. 3–4, aportado al proyecto.
- [Documentación scikit-learn: cross-validation y separación por grupos](https://scikit-learn.org/stable/modules/cross_validation.html).
- [Documentación oficial Eclipse Paho: API y callbacks MQTT](https://eclipse.dev/paho/clients/python/docs/).
