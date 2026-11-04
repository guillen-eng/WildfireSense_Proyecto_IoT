# README_EQUIPO — Guía de trabajo de WildfireSense (desde cero)

Esta guía está pensada para **Joan, Lola, Abel y Yousuf**, incluso si es la primera vez que utilizáis Git, GitHub Desktop, Visual Studio Code y Docker. Seguid el orden. No hace falta saber comandos Git para las operaciones normales.

**El objetivo:** que todos puedan ver el mismo código, avanzar simultáneamente sin sobrescribir cambios y comprobar qué se ha probado realmente.

- Proyecto: https://github.com/guillen-eng/WildfireSense_Proyecto_IoT
- Descripción del sistema, arquitectura, arranque y pruebas: [README.md](README.md).
- Esta guía es un manual de colaboración, **no una autorización para desplegar un detector de incendios real**.

---

## Índice

1. [Qué significan los términos de GitHub](#1-qué-significan-los-términos-de-github)
2. [Instalar las herramientas en Windows](#2-instalar-las-herramientas-en-windows)
3. [Entrar al repositorio y clonar tu copia](#3-entrar-al-repositorio-y-clonar-tu-copia)
4. [Primera comprobación de Docker](#4-primera-comprobación-de-docker)
5. [Cómo trabaja cada persona cada día](#5-cómo-trabaja-cada-persona-cada-día)
6. [Crear una tarea y una rama](#6-crear-una-tarea-y-una-rama)
7. [Editar archivos, revisar cambios y hacer commit](#7-editar-archivos-revisar-cambios-y-hacer-commit)
8. [Subir una rama y abrir una Pull Request](#8-subir-una-rama-y-abrir-una-pull-request)
9. [Revisar, probar, integrar y actualizar tu ordenador](#9-revisar-probar-integrar-y-actualizar-tu-ordenador)
10. [Qué hacer cuando dos personas cambian lo mismo](#10-qué-hacer-cuando-dos-personas-cambian-lo-mismo)
11. [Docker: cómo funciona y cómo usarlo sin perder datos](#11-docker-cómo-funciona-y-cómo-usarlo-sin-perder-datos)
12. [Cómo repartimos el trabajo y medimos el avance](#12-cómo-repartimos-el-trabajo-y-medimos-el-avance)
13. [Errores frecuentes y soluciones](#13-errores-frecuentes-y-soluciones)
14. [Ejercicio de incorporación y checklist](#14-ejercicio-de-incorporación-y-checklist)

---

## 1. Qué significan los términos de GitHub

| Término | En palabras sencillas |
|---|---|
| **Git** | Programa que registra cambios en los archivos y permite volver a versiones anteriores. |
| **GitHub** | Sitio en Internet que almacena el repositorio y permite colaborar. |
| **Repositorio** (repo) | Carpeta de proyecto con su historial Git; es nuestro código común. |
| **Local** | Tu copia en tu propio ordenador. |
| **Remoto** (`origin`) | La copia publicada en GitHub. |
| **`main`** | Rama principal que queremos mantener funcional y revisada. |
| **Rama** (*branch*) | Línea de trabajo paralela, para una funcionalidad, arreglo o documento. |
| **`Changes`** | Archivos que has modificado, añadido o eliminado y aún no has guardado en un commit. |
| **`Commit`** | Guarda en el historial **local** una versión de los cambios seleccionados. No los sube a Internet. |
| **`Publish branch`** | Publica por primera vez tu rama en GitHub. |
| **`Push origin`** | Envía a GitHub nuevos commits de una rama ya publicada. |
| **`Fetch origin`** | Comprueba qué cambios nuevos hay en GitHub, sin necesariamente incorporarlos a tus archivos. |
| **`Pull origin`** | Descarga e incorpora a tu rama local los cambios del remoto correspondiente. |
| **Pull Request** (PR) | Solicitud de revisión para incorporar una rama a otra (habitualmente a `main`). |
| **Merge** | Unión de cambios de la PR con la rama de destino. No es lo mismo que Push. |
| **Conflicto** | Dos cambios incompatibles en una misma parte de un archivo; una persona debe elegir cómo combinarlos. |
| **Issue** | Tarea, fallo o decisión registrada y discutible. |
| **`.gitignore`** | Archivo que indica qué archivos **no versionados** no debemos incluir en Git. |

**Regla de oro:** *guardar (Ctrl+S)*, *commit* y *push* son **tres acciones diferentes**. Guardar cambia un archivo en tu ordenador; commit registra una versión; push la comparte.

### Esquema de una tarea normal

~~~text
main (código compartido)
      |
      +--> feature/nombre-tarea  (trabajas en tu ordenador)
                |
                +--> Cambios → Commit → Push origin
                                           |
                                        GitHub
                                           |
                                     Pull Request
                                           |
                                Revisión + pruebas
                                           |
                                        Merge
                                           |
                                        main
~~~

Si haces un commit por error **no se publica automáticamente en `main`**. Eso reduce el riesgo de afectar a los demás.

## 2. Instalar las herramientas en Windows

### Paso A. Cuenta de GitHub

1. Entra en https://github.com/ y crea una cuenta o inicia sesión.
2. El responsable del repositorio entra en `Settings → Collaborators → Add people` y te invita con tu usuario de GitHub.
3. Acepta la invitación desde GitHub o el correo que recibas.
4. Abre https://github.com/guillen-eng/WildfireSense_Proyecto_IoT y comprueba que puedes ver los archivos.

**Nota:** el repositorio es público para *leer*, pero para publicar cambios como colaborador debes tener permisos de escritura. Si aún no te han invitado, puedes clonar y leer, pero no hacer push al repositorio oficial.

### Paso B. GitHub Desktop

1. Descarga la versión de Windows desde https://desktop.github.com/.
2. Instálala y abre `GitHub Desktop`.
3. Menú `File → Options → Accounts`: inicia sesión con GitHub (la ubicación exacta puede variar ligeramente según la versión).
4. Si te pide nombre y correo de Git, configura los datos con los que quieres identificar tus commits. El correo puede ser uno `noreply` de GitHub si prefieres no publicar una dirección personal.
5. **No pulses `Create new repository`:** el repositorio WildfireSense ya existe.

### Paso C. Visual Studio Code

1. Descarga VS Code desde https://code.visualstudio.com/.
2. Instálalo.
3. En GitHub Desktop, `File → Options → Integrations`, selecciona **Visual Studio Code** como editor externo, si aparece.
4. Para abrir el código: `Repository → Open in Visual Studio Code`.

VS Code sirve para **editar archivos**. GitHub Desktop sirve para **guardar, compartir y revisar cambios**. No son programas rivales.

### Paso D. Docker Desktop

1. Comprueba que tu ordenador permite virtualización y cumple los requisitos de Docker Desktop; en Windows es habitual utilizar **WSL 2**.
2. Sigue https://docs.docker.com/desktop/setup/install/windows-install/.
3. Si Docker te solicita instalar o actualizar WSL 2, sigue las instrucciones oficiales y reinicia Windows si es necesario.
4. Abre **Docker Desktop** y espera hasta que el motor esté iniciado.
5. En PowerShell o la terminal de VS Code escribe:

~~~powershell
docker --version
docker compose version
docker info
~~~

Si `docker info` devuelve información del servidor, el motor responde. Si devuelve un error de conexión, abre Docker Desktop y verifica WSL/virtualización; **no intentes ejecutar aún WildfireSense**.

**¿Necesitamos instalar Python local?** No para ejecutar los contenedores: los Dockerfiles incluyen sus entornos Python. Puedes instalar Python para desarrollo, pero no es obligatorio para este arranque.

**¿Necesitamos una máquina virtual adicional?** No. Docker Desktop ya permite ejecutar los servicios definidos en Compose y es suficiente para el prototipo local.

## 3. Entrar al repositorio y clonar tu copia

**Clonar** significa descargar por primera vez el repositorio junto con su historial Git.

1. Abre GitHub Desktop.
2. Selecciona `File → Clone repository`.
3. Abre la pestaña `URL` y pega:

~~~text
https://github.com/guillen-eng/WildfireSense_Proyecto_IoT
~~~

4. En `Local path` elige una **carpeta nueva** donde guardar tu copia. Por ejemplo:

~~~text
C:\Users\TU_USUARIO\Desktop\WildfireSense_Proyecto_IoT
~~~

5. Pulsa `Clone` y espera a que termine.
6. En la parte superior verás `Current repository: WildfireSense_Proyecto_IoT`.
7. Pulsa `Current branch` y selecciona **`main`**.
8. Pulsa `Fetch origin` y, si aparece `Pull origin`, púlsalo para actualizar.

**No copies una carpeta ajena encima de un clon sin antes coordinarlo.** El código que hay en `main`, una vez integrada la PR inicial, debe ser el punto de partida común.

**No trabajes en la carpeta del proyecto antiguo** si también tienes una versión `WildfireSense_inicio`. Solo las modificaciones hechas dentro del **clon de GitHub** aparecerán en GitHub Desktop.

### ¿Cómo sé dónde está la carpeta correcta?

En GitHub Desktop: `Repository → Show in Explorer`. Se abre exactamente la carpeta que Git controla.

### ¿Y si ahora mismo `main` solo tiene un README?

En la fase inicial de configuración, la importación está en la rama `setup/import-current-prototype` y su Pull Request. **Hasta que esa PR se fusione**, `main` puede contener solo el README inicial. Eso no significa que el código se haya perdido. No intentes clonar una segunda vez para resolverlo.

## 4. Primera comprobación de Docker

Este paso se realiza **cuando `main` ya contiene el prototipo integrado**. Antes de ello, puedes consultar la PR sin ejecutar el sistema.

1. Abre `Repository → Open in Visual Studio Code`.
2. Comprueba en el explorador de VS Code que ves `docker-compose.yml` en la raíz.
3. En VS Code abre `Terminal → New Terminal`.
4. Comprueba que Docker Desktop está iniciado.
5. Ejecuta:

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.edge.yml -f docker-compose.cloud.yml config --quiet
~~~

Si no muestra errores, la configuración es coherente **a nivel de Compose**. Esto NO garantiza que las aplicaciones funcionen.

### Arrancar los servicios principales

Antes, comprueba que no existe otro WildfireSense en funcionamiento utilizando los puertos **1883** (MQTT) y **8090** (dashboard).

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.edge.yml -f docker-compose.cloud.yml up -d --build mosquitto edge cloud
~~~

**Qué significa:**

- `docker compose`: utiliza Docker Compose.
- `-f`: elige los archivos de configuración que se combinan.
- `up`: crea e inicia los servicios.
- `-d`: los deja en segundo plano.
- `--build`: reconstruye las imágenes de nuestros servicios cuando corresponde.
- `mosquitto edge cloud`: son los tres servicios que queremos iniciar.

Comprobar si están en marcha:

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.edge.yml -f docker-compose.cloud.yml ps
Invoke-RestMethod "http://127.0.0.1:8090/api/health"
~~~

Abrir http://127.0.0.1:8090 en el navegador. En una instalación nueva el dashboard puede estar **vacío**: las alertas antiguas están en una base local que no se versiona.

**Si ves una página, NO significa automáticamente que el detector científico esté validado**. Solo has confirmado una parte del funcionamiento técnico.

### Apagar sin borrar datos

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.edge.yml -f docker-compose.cloud.yml stop mosquitto edge cloud
~~~

**No utilices** `docker compose down -v`, `docker system prune` ni borres `cloud/data` para «arreglar» un fallo: pueden eliminar datos que interesa conservar.

### Comprobar las pruebas unitarias

En la raíz del clon, con Docker Desktop iniciado:

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.edge.yml run --rm --no-deps --build --entrypoint python edge -m unittest discover -s tests -v
~~~

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.cloud.yml run --rm --no-deps --build --entrypoint python cloud -m unittest discover -s tests -v
~~~

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.scenario.yml --profile escenario run --rm --no-deps --build --entrypoint python scenario -m unittest discover -s tests -v
~~~

Estos comandos inician contenedores **temporales** y no requieren arrancar MQTT. El resultado esperado es `OK` al final de cada suite, **pero cada persona debe comprobarlo en su ordenador**.

> Si el proyecto muestra un error, copia el mensaje completo, el comando usado y el nombre de la rama en una Issue o en el grupo. No digas simplemente «Docker no funciona».

## 5. Cómo trabaja cada persona cada día

**No programar directamente en `main`.** Usaremos una rama por tarea.

### Al comenzar el día

1. Abre GitHub Desktop.
2. Selecciona el repositorio correcto.
3. Si vas a empezar **una tarea nueva**, cambia a `main` desde `Current branch`.
4. Pulsa `Fetch origin` y luego `Pull origin` si aparece. Ahora tu `main` local está actualizado.
5. Crea una **nueva rama desde ese `main` actualizado**.
6. Abre VS Code y trabaja únicamente en esa tarea.

**Si continúas una tarea en tu rama existente**, NO tienes que crear otra rama cada día. Sigue trabajando en ella; usa `Fetch origin` / `Pull origin` cuando corresponda y coordina cualquier integración desde `main`. No cambies a `main` con modificaciones sin guardar.

### Al terminar el día

1. En VS Code guarda los archivos (`Ctrl+S`).
2. Ejecuta las pruebas de la parte modificada si es posible.
3. Abre GitHub Desktop y revisa `Changes`.
4. Escribe un commit con sentido (qué se cambió).
5. Pulsa `Push origin`; si es la primera publicación de la rama, `Publish branch`.
6. Actualiza la Issue con lo conseguido, lo pendiente y cómo comprobarlo.

**¿Verán mis compañeros los cambios inmediatamente?** Solo cuando los publiques. Y **no aparecerán automáticamente en su copia local**: ellos deben hacer Fetch/Pull o consultar tu rama/PR.

## 6. Crear una tarea y una rama

### Antes de programar: crear una Issue

En GitHub:

1. Abre el repositorio.
2. Selecciona `Issues → New issue`.
3. Título: concreto; ejemplo `Definir contrato MQTT de las lecturas`.
4. Descripción: problema, decisión pendiente, archivos afectados y cómo sabremos que está terminado.
5. Asigna un responsable. Una tarea puede tener colaboradores, pero debe existir alguien responsable de cerrarla.
6. Crea la Issue.

Plantilla útil:

~~~markdown
## Objetivo
Qué problema queremos resolver.

## Alcance
Qué vamos a modificar y qué no.

## Criterio de aceptación
- [ ] Existe una explicación/implementación verificable.
- [ ] Se ejecutan las pruebas pertinentes.
- [ ] README o documentación actualizados si cambia el uso.

## Evidencias
Comandos, resultados o enlaces a experimentos.
~~~

**No consideramos terminada una tarea solo porque haya un archivo nuevo.**

### Crear una rama en GitHub Desktop

1. Actualiza `main` como se indica arriba.
2. Pulsa `Current branch → New branch`.
3. Escribe un nombre descriptivo:

~~~text
docs/mqtt-contract
feature/edge-evaluation
fix/cloud-startup
test/docker-clean-clone
~~~

4. Confirma que la rama se crea **desde `main`** y pulsa `Create branch`.
5. Ya puedes editar sin alterar `main`.

**Regla:** un arreglo, funcionalidad o documento por rama. Evita mezclar cambios grandes y no relacionados.

## 7. Editar archivos, revisar cambios y hacer commit

### Cambiar un archivo que ya existe

1. Abre VS Code desde GitHub Desktop.
2. Edita el archivo.
3. Guarda con `Ctrl+S`.
4. Vuelve a GitHub Desktop → pestaña `Changes`.
5. Selecciona cada archivo para ver sus diferencias.

### Añadir un archivo nuevo

1. En VS Code, botón derecho en la carpeta adecuada → `New File`.
2. Escribe un nombre y extensión, por ejemplo `docs/decisiones.md`.
3. Guarda contenido.
4. GitHub Desktop mostrará el archivo como **nuevo**.

**No hace falta subir archivos a GitHub uno por uno en el navegador.** GitHub Desktop detecta todas las modificaciones dentro de la carpeta clonada.

### ¿Qué significan los colores?

En el diff normalmente se resaltan en **verde las líneas añadidas** y en **rojo las eliminadas**. Esto no significa «código correcto» o «incorrecto», solo «se añadió» o «se quitó».

### Antes del commit

Comprueba lo siguiente:

- Estás en tu **rama de tarea**, no en `main`.
- Los archivos modificados pertenecen a esa tarea.
- No hay contraseñas, `.env`, bases SQLite, logs masivos ni archivos de otro compañero que no querías incluir.
- Si la modificación afecta a código, has ejecutado tests relevantes y has anotado el resultado real.

GitHub Desktop permite **marcar o desmarcar archivos** para decidir cuáles entran en el commit. No marques por inercia todos los cambios si no entiendes qué son.

### Crear el commit

En la parte inferior izquierda:

- `Summary (required)`: mensaje breve, por ejemplo `docs: define MQTT reading fields and units`.
- `Description`: opcional; explica el motivo de cambios complejos.
- Pulsa `Commit to <nombre-de-tu-rama>`.

Puedes hacer **varios commits** durante una tarea. Es preferible a acumular cientos de modificaciones en uno solo.

**Después del commit, los cambios siguen siendo locales.** Todavía tienes que publicar o hacer push.

## 8. Subir una rama y abrir una Pull Request

### Publicar por primera vez

En GitHub Desktop pulsa **`Publish branch`**. Tu rama aparecerá en GitHub y los compañeros podrán verla.

### Enviar nuevos commits

Si la rama ya existe en GitHub, después del commit pulsa **`Push origin`**. Esto envía tus cambios, pero **NO los incorpora a `main`**.

### Abrir Pull Request

1. En GitHub Desktop, `Branch → Create Pull Request`, o entra en GitHub y elige `Compare & pull request`.
2. Comprueba los campos:
   - `base: main` → dónde quieres integrar.
   - `compare: tu-rama` → qué cambios propones.
3. Añade un título concreto, por ejemplo `Documenta contrato MQTT v1`.
4. En la descripción, explica qué cambiaste, por qué, qué comandos ejecutaste y qué resultado obtuviste.
5. Si no está listo para que se fusione, usa **`Draft pull request`**.
6. Pulsa `Create pull request`.

**Si la PR ya existe**, no abras otra para la misma rama: haz commit y push. La PR **se actualiza automáticamente** con los nuevos commits.

**Ejemplo real:** la importación inicial de WildfireSense es la **[PR #1](https://github.com/guillen-eng/WildfireSense_Proyecto_IoT/pull/1)** desde `setup/import-current-prototype` a `main`. Tener una PR abierta **no quiere decir que ya se haya fusionado**.

### Plantilla de descripción de PR

~~~markdown
## Objetivo
Qué Issue resuelve y por qué.

## Cambios
- Qué archivos y comportamiento cambian.

## Pruebas realizadas
- Comando:
- Resultado:
- Entorno:

## Qué NO está comprobado
Limitaciones, datos sintéticos, pruebas pendientes.

## Revisores
Persona que revisará el cambio.
~~~

## 9. Revisar, probar, integrar y actualizar tu ordenador

### Revisar una PR de otro compañero

1. En GitHub abre `Pull requests` y selecciona la PR.
2. Lee la descripción.
3. En `Files changed` compara los cambios.
4. Si no entiendes una decisión, pregunta en `Conversation` o en la línea afectada.
5. Comprueba que no se hayan modificado archivos ajenos sin motivo.
6. Si procede, descarga la rama para ejecutar los tests. **No afirmes que pasan sin haberlos ejecutado.**
7. Aprueba o solicita cambios según el resultado.

**Para la primera importación:** `No conflicts with base branch` solo significa que Git puede combinar las ramas; **no demuestra que Docker o los tests funcionen**.

### Fusionar

Cuando otro integrante haya revisado la PR y se hayan cumplido los criterios:

1. Abre la PR en GitHub.
2. Pulsa `Merge pull request`, si está permitido.
3. Confirma la integración.
4. Comprueba que la PR figura `Merged`.

**No pulses Merge para «guardar» cambios.** Guardar corresponde a Commit; publicar, a Push; Merge integra la rama en `main`.

### Actualizar tu copia después de un merge

1. En GitHub Desktop selecciona `Current branch → main`.
2. Pulsa `Fetch origin`.
3. Pulsa `Pull origin` si aparece.
4. Comprueba que el cambio está ahora en los archivos locales.
5. Comienza la siguiente tarea creando una **rama nueva desde el `main` actualizado**.

No continúes trabajando sobre una rama antigua ya fusionada para tareas no relacionadas.

### ¿Y si tu compañero sigue en otra rama mientras yo cambio `main`?

No importa: su trabajo no desaparece. Sin embargo, si la tarea dura muchos días, será necesario coordinar cómo incorporar las novedades de `main` a su rama antes del merge. No hagáis `force push` ni reescribáis historial compartido por vuestra cuenta.

## 10. Qué hacer cuando dos personas cambian lo mismo

### Caso sencillo: archivos distintos

Joan cambia `edge/logic.py` y Abel cambia `cloud/app.py`. Si no hay dependencias rotas, Git suele poder integrar ambos cambios automáticamente.

### Caso complicado: el mismo archivo y las mismas líneas

Dos personas cambian `docker-compose.yml` de maneras incompatibles. Git puede mostrar un **merge conflict**.

Procedimiento para novatos:

1. **Detente:** no pulses botones de resolución sin saber qué cambios mantendrás.
2. Avisa a quien modificó el mismo archivo.
3. En GitHub Desktop revisa el aviso de conflicto y abre el archivo en VS Code.
4. Identifica qué necesita cada cambio: puede que haya que conservar **ambos**, no elegir uno arbitrariamente.
5. Elimina los marcadores de conflicto `<<<<<<<`, `=======`, `>>>>>>>` **solo después** de resolver el contenido.
6. Guarda, valida Docker/ejecuta tests.
7. Completa el merge en GitHub Desktop y vuelve a publicar los cambios.

**Nunca borres una carpeta completa para resolver un conflicto.** Nunca uses `Force push` o `Discard all changes` como primera solución.

### Si GitHub Desktop pregunta qué hacer con cambios sin guardar al cambiar de rama

Puede ofrecer `Leave changes` o `Bring changes`; su significado depende del estado y de la operación. Si no estás seguro, lo mejor es **quedarte en la rama, revisar Changes y hacer primero un commit adecuado**. No cambies de rama a ciegas.

## 11. Docker: cómo funciona y cómo usarlo sin perder datos

### Conceptos que debemos saber explicar

- **Dockerfile:** receta que construye el entorno de un servicio.
- **Imagen:** resultado preparado a partir del Dockerfile (por ejemplo, Python más dependencias).
- **Contenedor:** proceso aislado que ejecuta esa imagen.
- **Servicio Compose:** definición de contenedor, entorno, red, puertos y volúmenes.
- **Broker MQTT:** Mosquitto, intermediario entre productores y consumidores de mensajes.
- **Volumen/montaje:** lugar donde se guardan datos fuera del sistema de archivos efímero del contenedor.
- **Puerto:** forma de acceder al contenedor desde el ordenador. Aquí MQTT usa `127.0.0.1:1883` y el dashboard `127.0.0.1:8090`.
- **Log:** salida de un contenedor para ver qué ocurre y diagnosticar errores.

### Qué estamos ejecutando realmente

~~~text
Simulator / Scenario / LoadLab
           |
      MQTT Mosquitto
           |
          Edge  --------> Cloud local --> Dashboard
    (Z-score + SOS)     (alertas SQLite)
           |
      [Shadow: observador opcional de lecturas, independiente]
~~~

Los cuatro **NO utilizáis el mismo contenedor remoto**: cada persona tiene su propia instalación de Docker en su PC, con el mismo código. Las bases locales y los resultados generados **no se sincronizan mediante Git**.

### Comandos útiles (siempre desde la raíz del repositorio)

Para iniciar la configuración principal:

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.edge.yml -f docker-compose.cloud.yml up -d --build mosquitto edge cloud
~~~

Para ver contenedores:

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.edge.yml -f docker-compose.cloud.yml ps
~~~

Para revisar los últimos logs:

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.edge.yml -f docker-compose.cloud.yml logs --tail 80 mosquitto edge cloud
~~~

Para detenerlos sin borrar sus datos:

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.edge.yml -f docker-compose.cloud.yml stop mosquitto edge cloud
~~~

Para generar datos **offline** sin MQTT:

~~~powershell
docker compose -f docker-compose.yml -f docker-compose.loadlab.yml --profile carga run --rm --no-deps --build loadlab --nodes 50 --mode mixed_proxy --no-pace
~~~

### ¿Qué papel tienen los siete archivos Compose?

| Archivo | Para qué se usa |
|---|---|
| `docker-compose.yml` | Base: broker y simulador sencillo |
| `docker-compose.edge.yml` | Añade Edge |
| `docker-compose.cloud.yml` | Añade Cloud local |
| `docker-compose.scenario.yml` | Añade Scenario y cambia la magnitud del Edge a temperatura para ese experimento |
| `docker-compose.shadow.yml` | Añade monitor experimental Shadow |
| `docker-compose.loadlab.yml` | Añade generador sintético LoadLab |
| `docker-compose.benchmark.yml` | Añade análisis offline de resultados |

En el comando, `-f` selecciona **qué combinación** ejecutas. **No todos los servicios se inician siempre**.

**Cuidado con la interpretación:** `docker compose config --quiet` valida el archivo Compose, pero no comprueba que el detector sea científicamente correcto.

### Seguridad local

La configuración actual de Mosquitto permite `allow_anonymous true` y está destinada únicamente a pruebas con el puerto ligado a `127.0.0.1`. No copiar esta configuración a un servidor público sin estudiar autenticación, cifrado y controles de acceso.

## 12. Cómo repartimos el trabajo y medimos el avance

### Responsabilidades propuestas (revisarlas en reunión)

| Persona/pareja | Área principal | Ejemplo de entregable |
|---|---|---|
| Joan y Lola | Datos, sensores, Edge, detección/ML | Contrato de variables, evaluación y pruebas del Edge |
| Abel y Yousuf | Cloud, integración, red y métricas | Arranque reproducible, latencia/CPU y modelo de comunicaciones |
| Los cuatro | Requisitos, revisión, documentación y demo | Decisiones compartidas y repositorio probado |

**Esto no sustituye el Work Plan aprobado ni asigna automáticamente Issues.** El reparto definitivo se decide entre los cuatro, teniendo en cuenta la carga real de cada tarea.

### Tablero GitHub Projects recomendado

Columnas: `Backlog → To do → In progress → In review → Done`.

Cada Issue debe tener:

- Un responsable.
- Un objetivo y alcance comprensibles.
- Una rama/PR si requiere cambios de código.
- Criterios de aceptación.
- Una evidencia: tests, captura, resultado de medición, documento o comentario verificable.

### No confundir estados

- **Hay código:** archivo creado, pero no implica prueba ni integración.
- **Implementado:** código ejecutable y comportamiento especificado.
- **Probado:** existe prueba reproducible con resultado documentado.
- **Validado:** hay evidencia pertinente para el requisito **real**. Una perturbación inventada no valida la detección de incendios.
- **Integrado:** está en `main` después de revisión.
- **Hecho (Done):** cumple los criterios de aceptación acordados y está documentado.

### Propuesta de primeras Issues

1. `Documentar requisitos y límites del sistema` — separar alerta ambiental de incendio confirmado.
2. `Definir contrato MQTT y unidades de variables` — acordar sensores/campos y versionado.
3. `Reproducir Docker en los cuatro equipos` — comprobar Health, dashboard y pruebas.
4. `Auditar procedencia/licencias de datasets históricos` — registrar fuentes y límites.
5. `Definir protocolo experimental de detección` — métricas y baselines antes de umbrales.
6. `Automatizar pruebas unitarias básicas en GitHub Actions` — después de estabilizar los comandos.

Evita abrir veinte Issues sin prioridades. Es mejor tener pocas con criterios verificables.

## 13. Errores frecuentes y soluciones

| Mensaje o síntoma | Qué significa | Qué hacer |
|---|---|---|
| `No local changes` en GitHub Desktop | No hay modificaciones sin commit | Verifica si editaste dentro del clon; si acabas de hacer commit, es normal |
| `Publish branch` | La rama solo existe localmente | Pulsa para publicarla en GitHub |
| `Push origin` | Tienes commits locales sin publicar | Pulsa para enviarlos |
| `Fetch origin` | GitHub Desktop va a comprobar cambios remotos | Pulsa; después `Pull origin` si aparece |
| `Nothing to pull` | Tu rama local ya está al día con su remoto | Puedes continuar |
| `Permission denied` / `403` al hacer push | No tienes permisos o falta autenticar | Comprueba invitación como colaborador, cuenta y sesión |
| `main` no muestra el código | La importación todavía no se ha fusionado | Abre la rama de importación/PR #1; no vuelvas a copiarlo todo |
| `Port is already allocated` | El puerto 1883 o 8090 está ocupado por otra copia | Detén la instancia antigua y vuelve a intentar |
| `Cannot connect to the Docker daemon` | Docker Desktop/WSL no responde | Abre Docker Desktop y revisa `docker info` |
| Dashboard vacío | La copia local no tiene alarmas almacenadas | Es normal al clonar; comprueba `/api/health` |
| Un test falla | Hay incompatibilidad o error en código/configuración | Copia comando, salida y rama en una Issue; no marques Done |
| Merge conflict | Dos cambios incompatibles | Coordinar, revisar en VS Code y ejecutar tests |
| Alguien ha borrado un archivo | Puede recuperarse del historial Git | No hagas limpieza masiva; consulta a otro integrante |
| Se ha publicado una contraseña real | Eliminar del último commit no basta | **Revocar/rotar la credencial** y limpiar el historial según corresponda; avisar al equipo |

### ¿Por qué aparece un SOS o una alerta antigua en un dashboard?

Porque Cloud utiliza una base **SQLite local persistente**. No es un estado global compartido por los cuatro. Los contadores pueden reflejar experimentos anteriores. Identifica cada ejecución con su configuración y evita utilizar contadores acumulados como resultados de un experimento aislado.

### ¿Por qué en una prueba aparece `sensible_heat_flux` y en otra `air_temperature_c`?

Porque el detector Edge admite seleccionar magnitudes según entorno/configuración, y Scenario lo cambia para sus ensayos. **Flujo de calor sensible W/m² no es temperatura del aire °C**. No los trates como intercambiables; esta decisión necesita contrato y justificación.

## 14. Ejercicio de incorporación y checklist

### Ejercicio sencillo para un nuevo integrante (sin tocar código crítico)

**Objetivo:** demostrar que sabe clonar, usar una rama, crear commit y abrir PR.

1. Clona el repositorio después de que se haya integrado la PR inicial.
2. Actualiza `main`.
3. Crea una Issue: `Docs: añadir explicación breve de mi componente`.
4. Crea la rama `docs/tuusuario-componente` desde `main`.
5. Dentro de una carpeta `docs/` (créala si no existe), añade un pequeño archivo `mi-componente.md` describiendo un componente sin modificar el código.
6. Guarda y revisa `Changes`.
7. Escribe el commit `docs: explain my WildfireSense component`.
8. Pulsa `Publish branch`.
9. Abre una PR hacia `main`.
10. Pide a un compañero que revise y comente.
11. Fusionad solo después de verificar el contenido.
12. Vuelve a `main` → `Fetch origin` → `Pull origin`.

**No hagáis los cuatro el ejercicio editando el mismo archivo.** Cada uno usará un nombre de archivo distinto y su propio usuario en el nombre de rama.

### Checklist individual

- [ ] Tengo cuenta de GitHub y acceso al repositorio.
- [ ] Tengo GitHub Desktop, VS Code y Docker Desktop instalados.
- [ ] Sé dónde está mi carpeta clonada.
- [ ] Sé seleccionar `main` y actualizar con Fetch/Pull.
- [ ] Sé crear una rama nueva desde `main`.
- [ ] Sé distinguir Guardar, Commit y Push.
- [ ] Sé abrir una Pull Request y leer `Files changed`.
- [ ] Sé ejecutar `docker compose config --quiet`.
- [ ] Sé iniciar, detener y revisar logs de los servicios.
- [ ] He superado al menos una prueba Docker y he anotado el resultado.
- [ ] Sé explicar por qué un detector de anomalías experimental no equivale a detección validada de incendios.

---

## Acuerdo mínimo del equipo

1. **`main` es nuestra versión revisada; no trabajar directamente allí.**
2. **Una Issue y una rama por tarea**, salvo correcciones menores acordadas.
3. **Commit + Push para compartir**; abrir PR para integrar.
4. **Revisar el trabajo de otro compañero** antes del merge.
5. **Tests antes de afirmar que funciona.**
6. **Nunca subir secretos ni borrar resultados ajenos.**
7. **Las decisiones técnicas se justifican y documentan.**
8. **Si no se ha comprobado, se marca como pendiente, no como completado.**

**Documentación principal:** [README.md](README.md).  
**PR inicial del prototipo:** [PR #1](https://github.com/guillen-eng/WildfireSense_Proyecto_IoT/pull/1).  
**Documentación oficial:** [GitHub Desktop](https://docs.github.com/es/desktop) · [Docker Desktop para Windows](https://docs.docker.com/desktop/setup/install/windows-install/) · [Docker Compose](https://docs.docker.com/compose/).
