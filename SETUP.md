# Guía de instalación y ejecución — PokéGrading

Stack: **FastAPI** (backend) · **React + Vite** (frontend) · **PostgreSQL** (base de datos)

> **Verificada el 2026-06-13** — todos los pasos fueron ejecutados y probados en Ubuntu con Python 3.12.3 y Node 20.

---

## Opción rápida: script único

```bash
bash start.sh
```

El script `start.sh` en la raíz del proyecto hace todo automáticamente:
verifica prerrequisitos, instala dependencias (Python y pnpm), aplica migraciones y arranca ambos servidores. Presiona **Ctrl+C** para detenerlos.

```bash
bash start.sh --setup-only   # solo instala, no arranca servicios
bash start.sh --start-only   # solo arranca (asume que ya está instalado)
```

Los logs quedan en `.logs/backend.log` y `.logs/frontend.log`.

---

## Instalación manual paso a paso

### Requisitos previos

| Herramienta | Versión mínima | Verificar |
|---|---|---|
| Python | 3.12 | `python3.12 --version` |
| python3.12-venv | — | `sudo apt install python3.12-venv` |
| Node.js | 18 | Instalar vía nvm (ver abajo) |
| pnpm | 10 | Gestor de paquetes del frontend |
| PostgreSQL | 14 | `sudo apt install postgresql postgresql-client` |

> **¿Por qué pnpm y no npm?** pnpm usa enlaces duros en lugar de copias, es más rápido, ocupa menos disco y evita el problema de hoisting de dependencias que puede ocultar dependencias no declaradas. Es el gestor recomendado para este proyecto.

---

### 1. Clonar el repositorio

```bash
git clone <url-del-repositorio>
cd PokeGrading-DrMundoSolutions
```

---

### 2. Base de datos (PostgreSQL)

```bash
sudo apt install postgresql postgresql-client
sudo systemctl start postgresql

sudo -u postgres psql -c "CREATE USER pokegrading WITH PASSWORD 'changeme';"
sudo -u postgres psql -c "CREATE DATABASE pokegrading_dev OWNER pokegrading;"
```

Verificar que está corriendo:

```bash
pg_isready
# /var/run/postgresql:5432 - accepting connections
```

> Para usar credenciales distintas crea un archivo `.env` en la raíz:
>
> ```env
> DATABASE_URL=postgresql+psycopg2://<usuario>:<contraseña>@localhost:5432/<base_de_datos>
> JWT_SECRET_KEY=una-clave-secreta-larga-y-aleatoria
> ```

---

### 3. Backend (Python / FastAPI)

#### 3.1 Crear entorno virtual

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

> Si falla con `ensurepip is not available`:
> ```bash
> sudo apt install python3.12-venv
> ```

#### 3.2 Instalar dependencias

```bash
pip install -r requirements.txt
pip install -e .
```

#### 3.3 Aplicar migraciones

```bash
alembic upgrade head
```

Output esperado (6 migraciones):
```
INFO  Running upgrade  -> 001, create users table
INFO  Running upgrade 001 -> 002, create catalog_cards table
INFO  Running upgrade 002 -> 5b9c8ddf442f, add_country_language_to_users
INFO  Running upgrade 5b9c8ddf442f -> 25aa234c2b99, add_display_fields_to_cards
INFO  Running upgrade 25aa234c2b99 -> bd596323e1ca, add_card_images_table_and_remove_url_cols
INFO  Running upgrade bd596323e1ca -> e269249ec3a9, create_submissions_table
```

#### 3.4 Arrancar el servidor

```bash
uvicorn pokegrading.main:app --reload
```

```bash
curl http://localhost:8000/health
# {"status":"ok","version":"1.0.0"}
```

URLs:
- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

### 4. Frontend (React + Vite)

#### 4.1 Instalar Node.js vía nvm (si no está instalado)

```bash
curl -o /tmp/nvm-install.sh https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh
bash /tmp/nvm-install.sh

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

nvm install 20
```

#### 4.2 Instalar pnpm

```bash
npm install -g pnpm
```

#### 4.3 Instalar dependencias e iniciar

Abre una **nueva terminal** (el backend debe seguir corriendo):

```bash
cd frontend
pnpm install
pnpm dev
```

App disponible en http://localhost:5173. Vite redirige `/api` a `http://localhost:8000` automáticamente.

---

### 5. Tests

Los tests usan **SQLite en memoria** — no requieren PostgreSQL corriendo.

```bash
source .venv/bin/activate
pytest
```

Output esperado: **94 tests, 0 fallos, cobertura ~95%**

```
========================= 94 passed in 8.85s =========================
Required test coverage of 75% reached. Total coverage: 95.12%
```

Reporte HTML de cobertura:

```bash
pytest --cov-report=html
# Abre htmlcov/index.html
```

---

### 6. Calidad de código (opcional)

```bash
black src/ tests/      # formato
isort src/ tests/      # imports
ruff check src/ tests/ # lint
pre-commit install     # hooks automáticos en cada commit
```

---

## Tabla de verificación

| Componente | Comando | Respuesta esperada |
|---|---|---|
| Backend health | `curl http://localhost:8000/health` | `{"status":"ok","version":"1.0.0"}` |
| Swagger UI | http://localhost:8000/docs | Página con endpoints |
| Frontend | http://localhost:5173 | Aplicación React |
| Tests | `pytest` | 94 passed, cobertura ≥ 75% |
