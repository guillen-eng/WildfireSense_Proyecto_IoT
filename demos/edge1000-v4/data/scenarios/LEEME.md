# Archivos de prueba por escenario (semilla 42)

Cada escenario tiene:
- `<nombre>.jsonl`: un mensaje por línea, ordenados por `ts`, con el contrato `id, ts, tx, seq, kind, v, boot_id, values{PM2.5, PM10, temperature, humidity}`. Es la salida de los sensores, antes de la red (sin jitter, pérdidas, duplicados ni desorden).
- `<nombre>_verdad.json`: t0, nodos implicados y qué debe pasar. NO se le da al detector.

## Qué debe pasar
| Archivo | Nodos | Periodo | Resultado esperado |
|---|---|---|---|
| fuego_lento | 49 (7x7 alrededor del nodo 496 = N3) | 30 s | Alarma. Primera lectura sostenida >35,5 en N3 a t0+21 min; vecinos entre t0+54 y t0+157 min |
| fuego_rapido | 49 | 5 s | Alarma. N3 supera 35,5 a t0+1,9 min; N4 a t0+3,9; los nodos alcanzados dejan de enviar |
| polvo_tractor | 25 (nodo 700) | 10 s | Sin alarma. Razón PM2.5/PM10 ~0,25 en el pico, 4 min |
| niebla | 25 | 60 s | Sin alarma. HR hasta ~95 %, PM2.5 aparente +12, T sin subida |
| sol_directo | 25 | 60 s | Sin alarma. T +4 °C en 30 min y error de hasta 2,8 °C |
| sos_boton | 9 (nodo 900) | 60 s (5 s en emergencia) | Alarma sos_alert inmediata a las 20:00 |
| fallo_congelado | 9 (nodo 100) | 10 s | Nodo 100 SOSPECHOSO; sin alarma |
| fallo_ruido | 9 (nodo 300) | 10 s | Nodo 300 SOSPECHOSO; sin alarma |
| fallo_silencio | 9 (nodo 500) | 10 s | Nodo 500 FALLO por silencio; sin alarma |

Alias del escenario de fuego: N3 = nodo 496, N4 = 497 (este), N5 = 528 (sur), N6 = 529 (sureste). Tiempo: `ts` en ms desde 2026-07-15 00:00 UTC; en `_verdad.json` los instantes están en segundos desde las 00:00.

## Comprobar que los archivos son correctos
`python3 comprobar.py .` (comprueba los propios datos: umbrales, razones, destrucción de nodos, SOS, congelado, silencio). Debe terminar con `RESULTADO TODO OK`.

## Regenerar con otra semilla
`python3 generador.py salida 7` (hacen falta ≥30 semillas para las métricas).

## Supuestos (sin fuente, ver el documento de escenarios)
`tx` = `ts`; `kind` = periodic salvo SOS; periodos de lectura por archivo; velocidades de avance (1 y 20 m/min); forma de la subida de humo; razón PM2.5/PM10 del humo (0,6 y 0,8); ciclo diario de T y HR; fondo de PM2.5 de 5-10 µg/m3. Cada nodo tiene un pequeño sesgo propio (PM ±1,5 µg/m3, T ±0,3 °C). La barbacoa no está incluida.
