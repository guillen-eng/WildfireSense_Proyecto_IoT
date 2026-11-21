# WildfireSense — Plan de finalización en tres semanas

Fecha de referencia: **viernes 20/11/2026**. Último viernes de las tres semanas: **11/12/2026**. El lunes 23 es un **hito intermedio**, no el cierre de proyecto.

## Estado real de partida

- Modelo Random Forest multiclase ya entrenado y exportado a JSON (~200 kB), inferencia en Edge sin paquetes de ML.
- Simulación offline de 1.000 nodos. En el Docker Desktop del equipo: 1.000 clientes MQTT, 6.000/6.000 mensajes recibidos a 100 mensajes/s con límite de 0,5 CPU y 512 MiB.
- Demo de 47.981 lecturas, SOS y corroboración por vecino; autonomía Edge ante Cloud caída y sincronización posteriores demostradas.
- Cloud es receptor **local** con SQLite y panel, no nube remota. Todos los resultados del clasificador se refieren a incendios **sintéticos**.
- Esta nueva versión incorpora agrupación no destructiva de avisos en incidentes (`/api/incidents`) y recall con límites temporales (`lab.early_detection`).

## Semana 1 · 20–27 noviembre — consolidar producto y control de cambios

| Trabajo | Entregable | Verificación |
|---|---|---|
| Demo del lunes 23 | Vídeo corto + 3 comandos + panel | Demo 1.000 nodos, MQTT, SOS, Cloud sin red |
| Centralizar el código | Rama `feature/edge-v3-incidentes` en GitHub; PR hacia rama de integración | Sin sobrescribir el trabajo del equipo, sin duplicar escenarios ni datos |
| Integrar panel de incidentes | API `/api/incidents`; tarjeta y tabla | Tests agrupación de vecindad/tiempo/ejecución, conservar eventos originales |
| Registrar protocolos de ensayo | Informe CSV/JSON con semillas, equipo, límites, periodo, RTT | Ejecutar 3 repeticiones a 100 y 800 msg/s, registrar PDR, p95/p99, RAM |
| Probar falsas alarmas | Polvo, niebla, sol, ruido, sensor congelado | Verificar recepción de todos los mensajes y ausencia de sospechas corroboradas |

**Decisión del equipo antes del 27/11:** ¿cuál es el tiempo máximo tolerable para un aviso de **un nodo aislado**? La demo mantiene preaviso con 30 s, y sospecha alta solo con vecino sano. No activar alarmas críticas por un único nodo sin decisión explícita.

## Semana 2 · 28 noviembre–4 diciembre — robustez y evaluación de IA

| Trabajo | Entregable | Verificación |
|---|---|---|
| Fallos de transporte | Simulador configurable: pérdida (1/5/10 %), duplicados, jitter, reordenación, cortes | Comparar PDR / latencia / gaps y rechazos; pruebas automatizadas |
| Métricas de detección temprana | Recall antes de 5/15/30/60 min, retrasos p50/p95, falsos episodios/h | Partición por semilla y episodio; nunca entrenar y evaluar en las mismas escenas |
| Robustez de sensores | Calidad, silencio, datos congelados, ruido, sensores con más latencia | Tests causales y sin fuga de `ground_truth`; SOS independiente |
| Definición de incidentes | Ventanas y radios revisados contra escenarios | Un incendio puede producir múltiples focos; documentar falsos agrupamientos |
| Rendimiento | Perfil con 0,5 CPU / 512 MiB bajo varios tráficos y replicas | Repeticiones y evitar afirmar tiempos por paquete o radio si solo es LAN |

**Decisiones antes del 04/12:** ubicación del Edge (PC, Raspberry Pi o equivalente), número de nodos por radio/gateway, y si el informe admite demo totalmente virtual. Si hay placa real disponible, probar inferencia y memoria en ella.

## Semana 3 · 5–11 diciembre — integración, entrega y defensa

| Trabajo | Entregable | Verificación |
|---|---|---|
| Repositorio único | PR integrados, `README` raíz, instalación sin dependencias ocultas, `.gitignore` | Clonación limpia y `docker compose up -d --build` |
| Informe final | 8–12 páginas: arquitectura, contrato, IA, datos, evaluación, problemas, contribuciones | Revisión bibliografía, figuras y reproducibilidad; límites honestos |
| Pruebas E2E | SOS, incendios lento/rápido, negativos, Cloud down/recover, 1.000 clientes | Script que falle con exit code si no se cumplen objetivos |
| Demo final | Guion 5–7 min con fallback offline; capturas/archivo de resultados | Ensayo con equipo, tiempos reales y plan si Docker falla |
| Documentación de riesgos | Latencia, seguridad, energía, limitaciones de sensores ópticos | Diferenciar simulación de validación real, Cloud local de Cloud remoto |

## Criterios de aceptación mínimos

1. Demo de 1.000 clientes conectados a MQTT durante 60 s, sin lecturas perdidas en prueba local controlada, bajo límite de 0,5 CPU / 512 MiB.
2. SOS sin depender del modelo ni de Cloud; el Edge conserva los avisos offline y los reenvía una vez confirmado el receptor.
3. Comparación ML / reglas por episodios independientes y tiempos límite; incluir confusores sin incendio.
4. Separar **mensajes de alerta**, **incidentes agrupados** e **incendios reales** (estos últimos NO validados).
5. Repositorio del equipo con PR y scripts reproducibles; ninguna modificación silenciosa de `main`.

## Riesgos a controlar

- Las 60/60 detecciones son simulaciones con reglas generativas similares a las de entrenamiento. No representan sensibilidad real.
- No se han medido cobertura radio, consumo eléctrico, pérdida real de WiFi/LoRa, humo de campo, ni calibración por fabricante.
- Agrupar por proximidad y tiempo puede unir incendios independientes o dividir uno en varios. Mantener todos los eventos crudos como evidencia.
- PDR MQTT a 100 msg/s no garantiza PDR a 800 msg/s limitado; ambas pruebas deben registrarse por separado.

## Revisión del plan al 20/11/2026 — V4

- **Añadido y probado:** `lab.model_gate`, validación por 36 episodios sintéticos de semillas 301–306; el candidato con 7.634 muestras extra **fue rechazado** por peor exactitud y retardo. El modelo en uso permanece igual.
- **Añadido y probado offline:** `lab.compare_reorder` y buffer experimental con SOS bypass; 4.677 lecturas adicionales aceptadas bajo retardo 10 s / pérdida 5 % / duplicados 2 %. No se ha activado en el gateway MQTT.
- **Pendiente inmediato:** comprobar la interfaz V3 y el flujo Cloud AI V4 en Windows/Docker; el panel de incidentes debe funcionar en el navegador, el reporte del gate debe persistir y los contenedores conservar su estado.
- **Antes del 27/11:** PR de integración, decidir la política para nodo aislado (no ascender de advisory a high por defecto), evaluar datos independientes/sensor físico disponible, y comprobar que un candidato rechazado no modifica el modelo en el Edge.
- **Antes del 04/12:** decidir si una ventana de reordenación es admisible por latencia y memoria; solo implementarla en tiempo real tras pruebas con reloj y vaciado por inactividad.
- **Antes del 11/12:** documentación final, reentrenamiento a partir de etiquetas revisadas o declaración explícita de que solo hay pipeline sintético, pruebas E2E en máquina limpia y defensa.
