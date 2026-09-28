# Guía: encender el proyecto en tu computador

Esta guía explica cómo encender back_exogena en tu máquina, qué hace cada comando
y qué hacer cuando algo falla. No necesitas instalar Python ni PostgreSQL: todo
corre dentro de Docker.

---

## 1. Conceptos básicos

| Palabra | Qué es | Comparación |
|---|---|---|
| **Docker** | Programa que corre aplicaciones en "cajas" aisladas | Un contenedor de barco: lleva todo lo necesario y funciona igual en cualquier puerto |
| **Imagen** | La plantilla de una caja, construida con el `Dockerfile` | El molde |
| **Contenedor** | Una caja encendida, creada a partir de la imagen | El producto hecho con el molde |
| **Docker Compose** | Enciende varias cajas juntas según `docker-compose.yml` | El director: "prende la base de datos, luego la app" |
| **Volumen** | Disco donde la base de datos guarda los datos; sobrevive aunque apagues las cajas | Un disco duro externo |
| **make** | Programa de atajos: `make up` ejecuta varios comandos largos por ti | Un control remoto con botones |

En este proyecto se encienden **dos cajas**:

- **`back-exogena-app`**: el backend (FastAPI) en http://localhost:8000
- **`back-exogena-db`**: un PostgreSQL **local** para desarrollar. No es la base de datos
  de AWS; es una copia vacía en tu computador para probar sin riesgo.

---

## 2. Lo que necesitas instalar (una sola vez)

1. **Docker Desktop**: https://www.docker.com/products/docker-desktop/
2. **Git** (en Windows incluye la terminal **Git Bash**): https://git-scm.com/
3. **make**:
   - **Windows**: abre PowerShell y ejecuta
     ```powershell
     winget install ezwinports.make
     ```
     Luego **cierra y vuelve a abrir VS Code** para que la terminal lo reconozca.
   - **macOS**: ya viene incluido (si no, `xcode-select --install`).
   - **Linux**: `sudo apt install make`.

> En Windows, `make` funciona desde **PowerShell** o desde **Git Bash**. Los atajos usan
> por dentro comandos de Linux (`sh`, `sed`, `cp`…) que vienen con Git; el `Makefile`
> los encuentra solo, por eso Git debe estar instalado.

---

## 3. La primera vez

1. Abre **Docker Desktop** y espera a que diga **"Engine running"** (abajo a la izquierda).
2. Abre una terminal en la carpeta del proyecto (en VS Code: **Ctrl + ñ**).
3. Ejecuta:

   ```bash
   make up
   ```

Eso es todo. `make up` hace esto por ti:

1. Revisa que Docker esté encendido (si no, te avisa).
2. Si no existe el archivo `.env`, lo crea copiando `.env_example` y le pone una
   clave `JWT_SECRET` aleatoria y segura.
3. Construye la imagen y enciende las dos cajas **en segundo plano**, así la terminal
   queda libre.
4. Espera a que la base de datos y la app estén listas.
5. Aplica las migraciones: crea o actualiza las tablas.
6. Te muestra los enlaces.

La **primera vez tarda unos minutos** porque descarga y construye todo. Las siguientes
veces tarda segundos.

Cuando termine, abre:

- http://localhost:8000/health → debe mostrar `{"status":"ok"}`
- http://localhost:8000/docs → la documentación interactiva. Con **"Try it out"**
  puedes registrar un usuario (`POST /auth/register`), crear notas, etc.

> El archivo `.env` es **personal** y **nunca se sube a git** (está en `.gitignore`).

---

## 4. El día a día

```bash
make up       # al empezar el día
make logs     # si quieres ver qué pasa en la app (Ctrl+C para dejar de verlos)
make down     # al terminar
```

- **Cuando editas código**, la app se recarga sola porque tu carpeta está conectada al
  contenedor. Si algún cambio no se refleja: `make restart`.
- **Cuando agregas una librería** en `requirements/`: `make up` reconstruye la imagen.
- **Cuando cambias un modelo** (una tabla):
  ```bash
  make migration m="agregar nit a terceros"   # genera el archivo de migración
  # revisa el archivo nuevo en alembic/versions/ (siempre, a mano)
  make migrate                                # lo aplica
  make db-check                               # confirma que no quedó nada pendiente
  ```
- **Antes de subir cambios**: `make test`.

---

## 5. Todos los comandos

Escribe `make` sin nada más para ver esta lista en la terminal.

### Día a día

| Comando | Qué hace |
|---|---|
| `make up` | Enciende **todo**: app + base de datos + migraciones. Crea el `.env` si falta |
| `make down` | Apaga todo. Los datos de la base local **se conservan** |
| `make restart` | Reinicia la app |
| `make status` | Muestra qué está encendido y si está sano (`healthy`) |
| `make logs` | Muestra los logs de la app en vivo |
| `make shell` | Abre una terminal **dentro** del contenedor de la app |
| `make psql` | Abre la consola SQL de la base de datos local (sal con `\q`) |
| `make reset` | ⚠️ Borra la base de datos **local** y enciende todo de cero. Pide confirmación |

### Base de datos

| Comando | Qué hace |
|---|---|
| `make migrate` | Aplica las migraciones pendientes |
| `make migration m="..."` | Crea una migración nueva comparando los modelos con la base de datos |
| `make db-check` | Verifica que los modelos y las migraciones coincidan |

### Pruebas y calidad

| Comando | Qué hace |
|---|---|
| `make test` | Corre **todas** las pruebas en Docker con una base desechable. No toca tu base local |
| `make venv` | Crea el entorno de Python local (`.venv`). Opcional: sirve para que VS Code entienda el código y para los comandos de abajo |
| `make test-unit` | Pruebas unitarias rápidas usando el `.venv` (necesita `make venv`) |
| `make lint` | Revisa el estilo del código (necesita `make venv`) |
| `make format` | Corrige el estilo automáticamente (necesita `make venv`) |
| `make clean` | Borra archivos temporales |

### ¿Qué ejecuta cada atajo?

`make` no hace nada mágico: cada atajo es una lista de comandos escrita en el archivo
[`Makefile`](../Makefile). Si alguna vez no tienes `make`, puedes escribir el comando
directamente:

| Atajo | Comando equivalente |
|---|---|
| `make up` | `docker compose up -d --build --wait` y luego `docker compose exec app alembic upgrade head` |
| `make down` | `docker compose down` |
| `make logs` | `docker compose logs -f app` |
| `make migrate` | `docker compose exec app alembic upgrade head` |
| `make migration m="x"` | `docker compose exec app alembic revision --autogenerate -m "x"` |
| `make test` | `docker compose -f docker-compose.test.yml run --rm --build app_test` |

(Sin `make`, el `.env` lo creas tú: copia `.env_example` como `.env` y llena `JWT_SECRET`
con un texto aleatorio de mínimo 32 caracteres.)

---

## 6. Problemas comunes

| Si ves… | Significa | Solución |
|---|---|---|
| `make: command not found` / `"make" no se reconoce` | No tienes `make`, o no reabriste VS Code después de instalarlo | Sección 2 |
| `sh.exe: No such file` o errores raros de `sh` | Git no está instalado, o se instaló en otra ruta | Instala Git (sección 2) y reabre la terminal |
| `ERROR - Docker no esta encendido` | Docker Desktop está cerrado | Ábrelo y espera "Engine running" |
| `port is already allocated` (8000 o 5433) | Otro programa usa ese puerto | Cierra ese programa. Si es una copia vieja de esta app: `make down` |
| `JWT_SECRET … at least 32 characters` | La clave del `.env` es muy corta | Pon un texto aleatorio de 32 o más caracteres, o borra `.env` y ejecuta `make up` |
| `service "app" is not running` | Usaste `make migrate`, `make shell`… con todo apagado | `make up` primero |
| `relation "accounts.users" does not exist` | Faltan las tablas | `make migrate` |
| La app no arranca y no sabes por qué | — | `make logs` y lee el último error |
| Todo está raro y quieres empezar limpio | — | `make reset` (⚠️ borra los datos **locales**) |

---

## 7. Qué NO hace este entorno

- **No se conecta a la base de datos de AWS (RDS).** Usa un PostgreSQL local. La conexión a
  AWS se configura en el despliegue, con los secretos en AWS Secrets Manager.
- **No sube nada a GitHub.** Los commits y pushes se hacen aparte, con git.
