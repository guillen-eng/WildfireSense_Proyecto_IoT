# Integración de V4 en el GitHub del equipo

GitHub: https://github.com/guillen-eng/WildfireSense_Proyecto_IoT

En la última revisión, `main` estaba orientado a escenarios y documentación y existían varias PR abiertas con la base Edge y ML. **No sobrescribir el árbol de `main` ni fusionar las PR ajenas unilateralmente**.

Propuesta técnica segura:

1. Revisar con el equipo cuál será la rama base de integración (`setup/import-current-prototype` u otra acordada, tras revisar sus PR y dependencias).
2. Crear una nueva rama `feature/wildfiresense-v4-model-gate` desde esa base, en un clon limpio.
3. Copiar el **contenido ejecutable** de V4 bajo `demos/edge1000-v4/` como primer PR revisable. No copiar `referencia/WildfireSense_origen.bundle`, historiales ZIP, artefactos de laboratorio locales, SQLite ni evidencia personal. Evitar duplicar `data/scenarios` en el proyecto definitivo: primero conservarlos en la demo autocontenida para verificar, después referenciarlos desde la raíz en una PR posterior.
4. Documentar comando de inicio `cd demos/edge1000-v4; docker compose up -d --build`, pruebas y limitaciones. Las rutas de Compose son relativas al propio directorio de la demo.
5. Abrir PR y revisar con el responsable de escenarios, contrato MQTT, integración Cloud y ML.
6. Solo tras aprobarlo, decidir si se adopta la arquitectura V4 como raíz del repositorio o se migran componentes uno a uno.

**No se ha realizado ningún push a GitHub** desde esta entrega. El directorio V4 es un artefacto exportado, no sustituye el historial Git ni el trabajo de las demás ramas.
