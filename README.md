# WildfireSense — Proyecto IoT y Edge Intelligence

> **Estado del repositorio:** prototipo académico en desarrollo. La comunicación MQTT, un detector Edge experimental, el almacenamiento local de alertas y un dashboard están implementados. **No está validada la detección de incendios forestales reales.**

Proyecto de la asignatura IoT y V2X. Equipo: **Joan, Lola, Abel y Yousuf**.

📘 **¿Eres nuevo en el equipo? Empieza por [README_EQUIPO.md](README_EQUIPO.md).** Incluye instalación paso a paso, GitHub Desktop, Docker, ramas, commits, pull requests y resolución de problemas.

## 1. Objetivo y alcance

WildfireSense estudia una arquitectura IoT con procesamiento **Edge** y un receptor **Cloud local** para identificar anomalías ambientales que *podrían* ser compatibles con situaciones de riesgo y generar avisos de prueba.

El objetivo de ingeniería es diseñar, implementar, justificar y evaluar el reparto de procesamiento entre sensores/simulación, Edge y Cloud: latencia, tráfico, coste computacional, confiabilidad de las alarmas y posibilidad de funcionamiento autónomo del Edge.

**Límites actuales:**

- Una anomalía ambiental **no equivale** a un incendio confirmado.
- Los umbrales existentes son **experimentales** y no representan límites físicos o reglamentarios validados.
- Se usan registros ambientales históricos, perturbaciones sintéticas y datos completamente sintéticos. Los eventos inyectados **no son incendios medidos**.
- MQTT es la comunicación implementada. **LoRa/LoRaWAN o V2X reales no están implementados**; su estudio/simulación queda pendiente.
- El componente denominado Cloud es, por ahora, **un servicio local**, no un despliegue en una infraestructura remota.

## 2. Arquitectura disponible

~~~text
Escenario histórico + perturbaciones de prueba    Simulador básico
                      \                           /
                       \                         /
                   MQTT: wildfiresense/readings/#
                                |
                           Mosquitto
                                |
                           Edge (Python)
                    detector Z-score experimental
                        + canal SOS separado
                                |
                   MQTT: wildfiresense/edge/alerts
                                |
                       Cloud local (Python)
                         SQLite + API HTTP
                                |
                  Dashboard http://127.0.0.1:8090

Servicios opcionales independientes:
- Shadow: escucha lecturas y registra detecciones CUSUM en logs.
- LoadLab: genera cargas sintéticas multivariables; por defecto trabaja
  offline. Solo publica lecturas MQTT si se indica --publish.
- Benchmark: analiza resultados previamente guardados.
~~~

### Qué hace cada bloque

| Componente | Función | Estado |
|---|---|---|
| Mosquitto | Broker local MQTT, puerto 1883 | Implementado para pruebas locales |
| Simulador | Generación básica de mensajes | Implementado |
| Scenario | Replay histórico y perturbaciones controladas | Implementado; no valida incendios reales |
| Edge | Lecturas MQTT, detector Z-score y mensajes SOS | Implementado; criterios provisionales |
| Shadow | Prueba CUSUM por separado sin emitir alarmas oficiales | Experimental |
| LoadLab | Generación de temperatura, humedad, PM2.5 y CO; prueba de carga offline o por MQTT | Experimental; publicación MQTT requiere validación |
| Cloud | Recepción de alertas, SQLite, API y dashboard | Implementado localmente |
| Benchmark | Scripts para evaluar experimentos ya registrados | Implementado parcialmente; resultados requieren revisión |

## 3. Organización del repositorio

~~~text
WildfireSense_Proyecto_IoT/
├── README.md                    # Documento general
├── README_EQUIPO.md             # Guía de trabajo para los cuatro
├── .gitignore                   # Exclusiones del control de versiones
├── docker-compose.yml           # Broker y simulador básico
├── docker-compose.edge.yml      # Servicio Edge
├── docker-compose.cloud.yml     # Servicio Cloud local
├── docker-compose.scenario.yml  # Escenarios
├── docker-compose.shadow.yml    # Monitor CUSUM
├── docker-compose.loadlab.yml   # Carga sintética
├── docker-compose.benchmark.yml # Análisis offline
├── PRUEBA_INTEGRACION.ps1       # Script legado; requiere revisión
├── mosquitto/                   # Configuración MQTT
├── simulator/                   # Simulación básica
├── scenario/                    # Datos históricos, configuración, pruebas
├── edge/                        # Procesamiento Edge y tests
├── shadow/                      # Detector secundario
├── loadlab/                     # Generación sintética y tests
├── cloud/                       # API, SQLite local y dashboard
└── benchmark/                   # Herramientas de evaluación
~~~

Algunas carpetas de resultados se generan al ejecutar los servicios; su ausencia en un clon nuevo **es normal**. Las bases SQLite y los archivos masivos de ejecución no forman parte del código fuente.

## 4. Requisitos

Este procedimiento está orientado a **Windows 10/11**.

1. [GitHub Desktop](https://desktop.github.com/) para trabajar con el repositorio.
2. [Visual Studio Code](https://code.visualstudio.com/) para editar el proyecto.
3. [Docker Desktop](https://www.docker.com/products/docker-desktop/) con motor Linux operativo (habitualmente WSL 2 en Windows).
4. GitHub: una cuenta y permiso de colaborador para enviar cambios al repositorio.

No es necesario instalar Python localmente para ejecutar los servicios con Docker: los Dockerfiles crean sus propios entornos.

Para instrucciones detalladas de instalación y uso, lee **[README_EQUIPO.md](README_EQUIPO.md)**.

## 5. Primera ejecución (Docker)

**Antes de empezar:** abre Docker Desktop y espera a que indique que el motor está en ejecución. Trabaja desde la **raíz del repositorio clonado**, donde se encuentra `docker-compose.yml`.

En VS Code: `Terminal → New Terminal`. En PowerShell, comprueba Docker:

~~~powershell
docker --version
docker compose version
docker info
~~~

Si `docker info` falla, primero resuelve Docker Desktop/WSL 2; no continúes con los servicios.

### 5.1 Validar la configuración sin arrancar nada

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.edge.yml -f docker-compose.cloud.yml config --quiet
~~~

Si vuelve al prompt sin errores, el Compose ha pasado la validación **sintáctica**. No es una prueba funcional del proyecto.

### 5.2 Iniciar broker, Edge y Cloud local

**Atención:** no ejecutes otra copia del mismo proyecto en paralelo usando los puertos 1883 y 8090. Si tienes la versión antigua funcionando, detén sus servicios primero desde su propia carpeta.

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.edge.yml -f docker-compose.cloud.yml up -d --build mosquitto edge cloud
~~~

Comprobar el estado:

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.edge.yml -f docker-compose.cloud.yml ps
Invoke-RestMethod "http://127.0.0.1:8090/api/health"
~~~

Abrir en un navegador:

- Dashboard: **http://127.0.0.1:8090**
- Salud del servicio: **http://127.0.0.1:8090/api/health**
- Estadísticas: **http://127.0.0.1:8090/api/stats**
- Alertas: **http://127.0.0.1:8090/api/alerts**

**Importante:** el dashboard puede aparecer sin alarmas en una instalación recién clonada. Eso es normal: no se versiona la base SQLite local.

Para observar logs:

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.edge.yml -f docker-compose.cloud.yml logs --tail 60 edge cloud
~~~

Para detener **estos servicios** sin borrar la base de datos:

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.edge.yml -f docker-compose.cloud.yml stop mosquitto edge cloud
~~~

No uses `down -v`, `docker system prune` ni borres `cloud/data` salvo que sepas exactamente qué datos quieres eliminar.

## 6. Ejecutar pruebas de código

Estos comandos utilizan contenedores temporales, **no necesitan el broker**, y no arrancan el stack completo. Se ejecutan desde la raíz del repositorio, con Docker Desktop iniciado.

### Tests del Edge

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.edge.yml run --rm --no-deps --build --entrypoint python edge -m unittest discover -s tests -v
~~~

### Tests del Cloud

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.cloud.yml run --rm --no-deps --build --entrypoint python cloud -m unittest discover -s tests -v
~~~

### Tests de Scenario

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.scenario.yml --profile escenario run --rm --no-deps --build --entrypoint python scenario -m unittest discover -s tests -v
~~~

### Tests de LoadLab

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.loadlab.yml --profile carga run --rm --no-deps --build --entrypoint python loadlab -m unittest discover -s tests -v
~~~

El criterio de éxito es que cada suite termine sin fallos (`OK`). **La mera presencia de tests no implica que estén pasando en el equipo de cada integrante.** El script antiguo `PRUEBA_INTEGRACION.ps1` tiene una comprobación de arranque pendiente de revisar y no debe considerarse por sí solo una prueba final fiable.

## 7. Prueba sintética sin publicar en MQTT

LoadLab permite comprobar la generación multivariable de forma **offline**:

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.loadlab.yml --profile carga run --rm --no-deps --build loadlab --nodes 50 --mode mixed_proxy --no-pace
~~~

Los resultados aparecen en `loadlab/results/`. Este comando **no publica mensajes MQTT ni produce alertas del Edge/Cloud**.

La opción `--publish` existe, pero **no debe utilizarse como prueba de detección de incendios reales**: transmite mensajes sintéticos y exige un experimento separado, con un broker levantado y métricas verificadas.

## 8. Datos, variables y criterio de detección

### Datos disponibles

- `scenario/data/` contiene extractos históricos y su manifiesto de procedencia. Esos registros **no establecen verdad-terreno verificada de incendio forestal**.
- `scenario/` introduce perturbaciones controladas sobre el replay para ensayar la cadena MQTT–Edge–Cloud.
- `loadlab/` genera lecturas sintéticas de **temperatura del aire (°C)**, **humedad relativa (%)**, **PM2.5 (µg/m³)** y **CO (ppm)**, con etiqueta de evento guardada *por separado* para evaluación offline.

### Detector oficial actual

El código en `edge/logic.py` implementa un Z-score por sensor: utiliza historial, umbral estadístico y dos anomalías consecutivas. Su variable por defecto es `sensible_heat_flux` (W/m²); al cargar `docker-compose.scenario.yml` se configura `air_temperature_c` (°C).

**No deben confundirse ambas magnitudes.** Este punto, el contrato de mensajes y la elección final de sensores están **pendientes de definición y justificación**.

### Mensajería

- Lecturas: `wildfiresense/readings/#`.
- SOS: `wildfiresense/events/sos`.
- Alertas oficiales del Edge: `wildfiresense/edge/alerts`.
- El Cloud actual se suscribe a las **alertas**, no almacena todas las lecturas.

Ejemplo **de una lectura sintética de prueba** (los valores son ilustrativos):

~~~json
{
  "node_id": "scale_0001",
  "type": "reading",
  "timestamp": "2026-01-01T00:00:00+00:00",
  "source": "wildfiresense_loadlab_synthetic_v1",
  "test_only": true,
  "measurements": {
    "air_temperature_c": 22.0,
    "relative_humidity_pct": 56.0,
    "pm25_ug_m3": 8.0,
    "co_ppm": 0.3
  }
}
~~~

Los umbrales de `loadlab/config.json` pertenecen a **reglas experimentales offline**. No son los umbrales del detector Z-score desplegado ni criterios validados de incendio.

## 9. Estado académico: qué está demostrado y qué falta

| Área | Estado |
|---|---|
| Broker MQTT, servicios Docker, Edge, Cloud y dashboard local | Código implementado; repetir verificación desde un clon limpio |
| Sospechas ambientales mediante Z-score | Experimentos con anomalías, **no validación de incendio real** |
| Comparación CUSUM/Shadow | Prototipos y pruebas experimentales |
| Simulación multivariable y escalable offline | Implementada; verificar escalabilidad MQTT por separado |
| Requisitos y criterios de aceptación científicos | **Pendiente de consolidar** |
| Contrato único de sensores, mensajes, unidades y temporización | **Pendiente** |
| Selección y justificación de sensores y umbrales | **Pendiente** |
| Entrenamiento, evaluación y despliegue de ML en Edge | **Pendiente** |
| Evaluación de CPU/RAM, latencia, pérdidas y ancho de banda | **Pendiente de campaña reproducible** |
| Estudio/simulación justificada de LoRa-lite | **Pendiente** |
| Automatización de tests con GitHub Actions | **Pendiente** |

Las afirmaciones de rendimiento deben acompañarse siempre de: versión del código, configuración, dataset, número de muestras, definición de la métrica y resultado medido.

## 10. Cómo colaborar

**No se trabaja directamente sobre `main`.**

1. Actualizar `main` con `Fetch origin / Pull origin` en GitHub Desktop.
2. Crear una rama nueva desde `main`: por ejemplo `feature/edge-tests`, `docs/requisitos` o `fix/cloud-health`.
3. Modificar solo los archivos de la tarea y ejecutar las pruebas relevantes.
4. Revisar `Changes` y crear un commit descriptivo.
5. Publicar con `Publish branch` o `Push origin`.
6. Abrir una Pull Request hacia `main` y pedir revisión.
7. Fusionar después de comprobar el código y las pruebas.
8. Volver a `main`, actualizar y comenzar la siguiente tarea.

La explicación completa, con capturas mentales de cada botón, errores frecuentes y reglas de grupo, está en **[README_EQUIPO.md](README_EQUIPO.md)**.

## 11. Seguridad y reproducibilidad

- El broker actual permite conexiones MQTT anónimas **solo para demostración local**; el puerto está publicado en `127.0.0.1`. No exponer esta configuración a Internet.
- No subir `.env`, credenciales, bases SQLite locales, logs ni grandes resultados generados automáticamente.
- Conservar configuraciones de los experimentos y **resultados seleccionados** que permitan reproducir las conclusiones.
- Documentar la fuente, fecha y condiciones de redistribución de los CSV de terceros antes de asumir que son de dominio público.
- Cambios en unidades, sensores, umbrales o contratos MQTT requieren discusión y tests, no solo modificar una constante.

## 12. Referencias de uso

- [Guía para el equipo](README_EQUIPO.md)
- [Repositorio WildfireSense](https://github.com/guillen-eng/WildfireSense_Proyecto_IoT)
- [GitHub Desktop — documentación oficial](https://docs.github.com/es/desktop)
- [Docker Desktop para Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
- [Docker Compose — documentación oficial](https://docs.docker.com/compose/)

---

**Advertencia:** WildfireSense es un proyecto de investigación y demostración académica. No debe emplearse como sistema operativo de protección civil o alarma de incendios sin diseño, calibración y certificación adecuados.
