# WildfireSense V4 — despliegue en DOS ordenadores (laboratorio)

**Estado:** propuesta de despliegue, todavía NO probada con los dos portátiles físicos. Rama `feature/two-pc-edge-cloud-topology` creada desde V4 (PR #6). No sustituye a `docker-compose.yml` de la demo de un solo ordenador.

## 1. Alcance y justificación

Esta topología de **dos ordenadores físicos** se ha acordado con la profesora. La guía *Module 3 — Project Guidelines*, pp. 3–4, pide separar los seis componentes lógicos, justificar el reparto Edge/Cloud y medir latencia/overhead; ofrece contenedores/VM como herramienta. El acuerdo de usar dos portátiles es **una decisión específica del equipo**, no una frase literal de la guía.

| Ordenador | Componentes | Responsabilidad |
| --- | --- | --- |
| **PC1 — Edge** | 1. Simulador, 2. Mosquitto (MQTT), 3. Gateway Edge, 4. Random Forest local | Recibir lecturas; procesar, SOS y preavisos sin Cloud; persistir cola SQLite |
| **PC2 — Cloud** | 5. Receptor MQTT, SQLite, API y panel; 6. Entrenador/validador offline | Recibir y confirmar almacenamiento, agrupar incidentes, consultar histórico; evaluar candidatos |
| **Red LAN privada** | MQTT/TCP 1883 entre PC1 y PC2 | Medir RTT real de aplicación y costes de tráfico entre equipos |

```text
PC1 (EDGE)                                    PC2 (CLOUD)
1000 nodos simulados -> Mosquitto :1883 <---- Cloud MQTT subscriber
                           |                       |
                     Edge + RF                 SQLite + API
                       |                         Panel :8090 (local PC2)
                  SQLite journal              Trainer/Validator
                       |
              SOS + alarmas locales
```

**Motivo de dejar Mosquitto en PC1:** que una caída del PC2 o de la conexión PC1–PC2 no corte la adquisición de lecturas ni la inferencia crítica. Los ACK de aplicación regresan por el mismo broker al Edge; este borra elementos pendientes solo al recibir el ACK del receptor. El RTT de ping/pong incluye ahora la comunicación entre ordenadores (no la propagación de radio de los sensores).

**Importante:** aquí `Cloud` sigue siendo un **servicio local en otro portátil**, NO AWS/Azure ni una Cloud pública.

## 2. Requisitos previos

- Ambos portátiles con Docker Desktop (Windows) o Docker Engine/Compose v2, en la **misma red LAN privada y fiable**. Docker debe estar iniciado y no deben existir otros contenedores ocupando 1883 en PC1 ni 8090 en PC2.
- Clonar **la misma rama de esta prueba** en ambos. En PowerShell:
  ```powershell
  git clone --branch feature/two-pc-edge-cloud-topology https://github.com/guillen-eng/WildfireSense_Proyecto_IoT.git WildfireSense_2PC
  cd WildfireSense_2PC/demos/edge1000-v4
  ```
- Comprobar direcciones IPv4 mediante `ipconfig`. Ejemplo ficticio: PC1 = `192.168.1.50`, PC2 = `192.168.1.60`. Sustituir **SIEMPRE** por las IP reales. Preferir reserva DHCP en el router para que no cambie PC1.
- Sincronizar los relojes de ambos equipos por Windows Time/NTP. En PowerShell: `w32tm /query /status` (en cada uno). La lectura `cloud_rtt_ms` usa reloj monótono, pero comparar marcas temporales entre equipos requiere relojes sincronizados.
- La configuración actual de Mosquitto acepta conexiones anónimas sin TLS. **Solo usar una LAN privada y aislada**: sin reenvío de puertos del router, sin Wi-Fi público, y restringiendo 1883 por firewall al IP del PC2. Para despliegue exterior hacen falta autenticación y cifrado.

## 3. PC1 — arrancar broker y Edge

En PowerShell **del ordenador Edge**, en `demos/edge1000-v4`:

```powershell
$env:EDGE_MQTT_BIND_IP = "192.168.1.50"   # IP LAN REAL del PC1
docker compose -f docker-compose.two-pc-edge.yml config --quiet
docker compose -f docker-compose.two-pc-edge.yml up -d --build mosquitto edge
docker compose -f docker-compose.two-pc-edge.yml ps
```

En Windows, como administrador, restringir el puerto de entrada al equipo Cloud (sustituir IP). Verificar que el perfil de red es **Privado** y que la política general bloquea el tráfico entrante no permitido:

```powershell
New-NetFirewallRule -DisplayName "WildfireSense MQTT PC2" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 1883 -RemoteAddress 192.168.1.60 -Profile Private
```

**Atención:** añadir una regla de permiso no elimina otras reglas anteriores que permitan 1883 a todo el mundo. Revisar reglas existentes y confirmar el alcance efectivo del firewall. Docker Desktop puede implementar redirección de puertos; verificar accesibilidad desde PC2 y desde un tercer equipo no autorizado si hay dudas.

Si Docker Desktop no admite asociar el puerto a la IP concreta, se puede usar `$env:EDGE_MQTT_BIND_IP = "0.0.0.0"` **solo después** de verificar las restricciones del firewall en la LAN. No exponer el broker a Internet.

## 4. PC2 — arrancar Cloud y dashboard

En PowerShell **del ordenador Cloud**, también en `demos/edge1000-v4`:

```powershell
$env:EDGE_MQTT_HOST = "192.168.1.50"      # IP LAN REAL del PC1
Test-NetConnection $env:EDGE_MQTT_HOST -Port 1883
docker compose -f docker-compose.two-pc-cloud.yml config --quiet
docker compose -f docker-compose.two-pc-cloud.yml up -d --build cloud
docker compose -f docker-compose.two-pc-cloud.yml ps
Invoke-RestMethod http://127.0.0.1:8090/api/health
Invoke-RestMethod http://127.0.0.1:8090/api/stats
```

Abrir en el navegador **del PC2**: http://127.0.0.1:8090. El HTTP solo escucha en el bucle local del PC2; no abre la web a toda la red. En Cloud debe aparecer `mqtt_connected: true` cuando consiga suscribirse.

En PC1, consultar el estado del Edge mediante el broker:

```powershell
docker compose -f docker-compose.two-pc-edge.yml exec mosquitto mosquitto_sub -h 127.0.0.1 -t wildfiresense/edge/status -C 1
```

Buscar `cloud_available: true`, `cloud_rtt_ms`, `model` y `backlog`. La primera detección de Cloud puede necesitar varios ciclos ping/pong.

## 5. Pruebas E2E entre los dos equipos

**A. Carga normal de 1.000 clientes** (PC1, con Cloud ya arrancado en PC2):

```powershell
docker compose -f docker-compose.two-pc-edge.yml run --rm simulator python -m lab.mqtt_run --clients 1000 --nodes 1000 --cycles 6 --period 10 --speed 1 --scene normal
```

Comprobar en la salida `publishing_clients=1000`, 6.000 lecturas ofrecidas y los contadores de recepción. **No afirmar PDR=100 % hasta medirlo en esta nueva topología física.** Anotar p95/p99, `cloud_rtt_ms`, `up_publish_bytes`, CPU/RAM e IP de ambos equipos.

**B. Alarmas y SOS** (PC1):

```powershell
docker compose -f docker-compose.two-pc-edge.yml run --rm simulator
```

Comprobar logs del Edge, histórico `/api/alerts` e incidentes `/api/incidents` en PC2.

**C. Caída real del receptor Cloud**:

1. En PC2: `docker compose -f docker-compose.two-pc-cloud.yml stop cloud`.
2. En PC1: ejecutar otra vez la demo y observar `ALARMA LOCAL` en logs de Edge; después de unos segundos `cloud_available=false` y `backlog>0`.
3. En PC2: `docker compose -f docker-compose.two-pc-cloud.yml start cloud`.
4. En PC1: comprobar que el backlog desciende hasta cero **cuando el Cloud confirme la escritura**. Comparar IDs almacenados antes/después en PC2 y comprobar que no se generan duplicados.

**D. Persistencia**: reiniciar `cloud` y `edge` y comprobar que sus SQLite y el histórico sobreviven. **No ejecutar `docker compose down -v`**.

El modo MQTT de los dos portátiles mide una red LAN real, pero **no es una simulación de LoRa ni una validación de incendios reales**.

## 6. Cloud AI: transferencia de modelos pendiente

Se incluyen `trainer` y `validator` **en PC2**, pero NO se incluye `promote` en ese Compose. La razón es fundamental: un `models/forest.json` promocionado en PC2 **no cambia el archivo físico ni el proceso Edge que corre en PC1**.

Para cerrar el componente de retorno de pesos se necesita un procedimiento explícito: candidato aprobado por gate, identificación SHA-256, transferencia autenticada (p. ej. SSH/SCP dentro de LAN), copia de seguridad/rollback del modelo de PC1 y reinicio controlado del Edge. No ejecutar la promoción sin esos controles; no activar candidatos durante un incidente.

La rama Cloud `feature/cloud-v4-reliability` (PR #7) mejora almacenamiento/CI. Esta rama de dos PC nace de PR #6 y **no incorpora todavía los cambios de PR #7**. Se deben integrar mediante una PR revisada, no copiando archivos a mano.

## 7. Criterios para dar por terminada esta fase

- [ ] Dos portátiles y sus IP documentadas; `docker compose config` funciona en ambos.
- [ ] Cloud se conecta al broker de PC1 y el panel de PC2 muestra estados reales del Edge.
- [ ] La demo de 1.000 clientes pasa, con tiempos y recursos medidos en el **despliegue de dos portátiles**.
- [ ] Con Cloud apagado, Edge continúa recibiendo y generando SOS/avisos.
- [ ] Al reconectar Cloud se recuperan eventos sin duplicados, con ACK de aplicación.
- [ ] SQLite conserva los datos tras reinicios; no se ha borrado el historial anterior.
- [ ] Evidencia de tráfico entre PCs (Wireshark, filtro `tcp.port == 1883`) y coste en bytes/RTT.
- [ ] Decidido y documentado el mecanismo de entrega de un modelo aprobado desde PC2 a PC1.
