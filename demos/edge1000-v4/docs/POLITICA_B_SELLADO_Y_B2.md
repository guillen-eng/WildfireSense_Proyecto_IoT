# WildfireSense — resultado B1 y preregistro B2 (22/11/2026)

## B1 rechazado con datos sellados
GitHub Actions: https://github.com/guillen-eng/WildfireSense_Proyecto_IoT/actions/runs/45047919874
Semillas 601–612 (no usadas para elegir el candidato B1). B1 era 120 s, score >=0.80, PM2.5 rápido - lento >=8 µg/m³ y temperatura rápida - lenta >=0 °C.

- Incendios aislados normales reconocidos: 22/24; falsos entre negativos normales: 0/48.
- **Con fondo de partículas alto: 6/48 negativos produjeron alarma no corroborada. B1 NO supera el gate previamente fijado.**
- Alta humedad (>=97 %): 12/24; sesgo PM2.5 de -30 %: 1/24; mezcla muy gruesa: 0/24.
- Mantener EDGE_ISOLATED_ESCALATION=0 y no presentar B1 como aprobado.

## B2 — ÚNICA alternativa conservadora preseleccionada antes del nuevo ensayo
En la fase de desarrollo anterior (semillas 301–306), B2 detectó 6/12 incendios aislados con 0/24 negativos falsos en cada uno de los dos controles normales y de fondo alto. La puerta adicional de temperatura al menos +0.5°C da prioridad a especificidad frente a sensibilidad; no es un umbral normativo, solo un candidato de ingeniería.

Config fija: isolated_enabled=True; isolated_persist_s=120; isolated_min_fire_score=0.80; isolated_min_pm25_rise=8; isolated_min_temperature_rise=0.5.

**Nuevo ensayo sellado (solo una vez): semillas 801–812.** Criterios de aprobación predefinidos:

1. Negativos aislados, normales y con fondo elevado: cero alertas unconfirmed_fire_risk.
2. Episodios de fuego: cero alertas unconfirmed_fire_risk previas a la ignición simulada.
3. Incendios aislados normales: al menos 6 de 24 reconocidos con aviso no corroborado.
4. Red con cinco nodos sanos: cero falsas alertas no corroboradas en negativos.

Las condiciones de humo grueso, humedad y sesgo del sensor se publicarán como límites, no se usarán para reajustar este mismo candidato. Si B2 falla, se congela la política B como prototipo experimental desactivado; no se continuará ajustando sobre el mismo generador.

Advertencia: incluso si se cumplen los criterios, **no hay validación con incendios reales**, ni calibración externa ni garantías de seguridad. Un aprobado significaría solamente aptitud para demo académica limitada, sujeta a pruebas de Docker MQTT y revisión del equipo.
