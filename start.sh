#!/usr/bin/env bash
# start.sh — Instala (si hace falta) y arranca PokéGrading completo.
# Uso: bash start.sh [--setup-only | --start-only]

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
FRONTEND="$ROOT/frontend"
LOG_DIR="$ROOT/.logs"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

# ── Colores ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✔${NC}  $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }
err()  { echo -e "${RED}✘${NC}  $*"; exit 1; }
step() { echo -e "\n${YELLOW}▶${NC}  $*"; }

SETUP_ONLY=false
START_ONLY=false
[[ "${1:-}" == "--setup-only" ]] && SETUP_ONLY=true
[[ "${1:-}" == "--start-only" ]] && START_ONLY=true

mkdir -p "$LOG_DIR"

# ══════════════════════════════════════════════════════════════════════════════
# 1. VERIFICAR REQUISITOS DEL SISTEMA
# ══════════════════════════════════════════════════════════════════════════════
step "Verificando requisitos del sistema..."

# Python 3.12
if ! python3.12 --version &>/dev/null; then
    err "Python 3.12 no encontrado. Instálalo: sudo apt install python3.12"
fi
ok "Python $(python3.12 --version 2>&1 | cut -d' ' -f2)"

# PostgreSQL
if ! pg_isready &>/dev/null; then
    warn "PostgreSQL no está corriendo."
    echo "    Instálalo y ejecútalo con:"
    echo "      sudo apt install postgresql postgresql-client"
    echo "      sudo systemctl start postgresql"
    echo "      sudo -u postgres psql -c \"CREATE USER pokegrading WITH PASSWORD 'changeme';\""
    echo "      sudo -u postgres psql -c \"CREATE DATABASE pokegrading_dev OWNER pokegrading;\""
    err "Arranca PostgreSQL antes de continuar."
fi
ok "PostgreSQL disponible ($(pg_isready))"

# nvm / Node.js / pnpm
export NVM_DIR="$HOME/.nvm"
if [ -s "$NVM_DIR/nvm.sh" ]; then
    # shellcheck source=/dev/null
    . "$NVM_DIR/nvm.sh"
fi

if ! command -v node &>/dev/null; then
    warn "Node.js no encontrado. Instalando vía nvm..."
    if ! command -v nvm &>/dev/null; then
        curl -o /tmp/nvm-install.sh \
            https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh
        bash /tmp/nvm-install.sh
        . "$NVM_DIR/nvm.sh"
    fi
    nvm install 20
fi
ok "Node $(node --version)"

if ! command -v pnpm &>/dev/null; then
    warn "pnpm no encontrado. Instalando..."
    npm install -g pnpm
fi
ok "pnpm $(pnpm --version)"

# ══════════════════════════════════════════════════════════════════════════════
# 2. BACKEND — entorno virtual + dependencias
# ══════════════════════════════════════════════════════════════════════════════
if ! $START_ONLY; then
    step "Configurando entorno virtual Python..."

    if [ ! -f "$VENV/bin/activate" ]; then
        python3.12 -m venv --without-pip "$VENV" 2>/dev/null || {
            err "No se pudo crear el venv. Instala: sudo apt install python3.12-venv"
        }
        curl -sS https://bootstrap.pypa.io/get-pip.py | "$VENV/bin/python3.12"
        ok "Entorno virtual creado con pip bootstrapped"
    else
        ok "Entorno virtual ya existe"
    fi

    step "Instalando dependencias Python..."
    if ! "$VENV/bin/pip" show fastapi &>/dev/null; then
        "$VENV/bin/pip" install --quiet -r "$ROOT/requirements.txt"
        "$VENV/bin/pip" install --quiet -e "$ROOT"
        ok "Dependencias instaladas"
    else
        ok "Dependencias ya instaladas"
    fi

    step "Aplicando migraciones de base de datos..."
    cd "$ROOT"
    "$VENV/bin/alembic" upgrade head
    ok "Migraciones aplicadas"

    # ── Frontend — dependencias ──────────────────────────────────────────────
    step "Instalando dependencias del frontend..."
    if [ ! -d "$FRONTEND/node_modules" ]; then
        cd "$FRONTEND" && pnpm install --silent
        ok "Dependencias frontend instaladas"
    else
        ok "node_modules ya existe"
    fi
fi

$SETUP_ONLY && { echo -e "\n${GREEN}Instalación completada.${NC}"; exit 0; }

# ══════════════════════════════════════════════════════════════════════════════
# 3. ARRANCAR SERVICIOS
# ══════════════════════════════════════════════════════════════════════════════
step "Arrancando backend (uvicorn)..."
cd "$ROOT"
"$VENV/bin/uvicorn" pokegrading.main:app --host 127.0.0.1 --port 8000 \
    --reload >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

# Esperar a que el backend responda
for i in {1..15}; do
    if curl -sf http://127.0.0.1:8000/health &>/dev/null; then
        ok "Backend activo en http://localhost:8000  (PID $BACKEND_PID)"
        ok "  Swagger UI → http://localhost:8000/docs"
        break
    fi
    sleep 1
    if [ "$i" -eq 15 ]; then
        warn "Backend tardó demasiado. Revisa $BACKEND_LOG"
    fi
done

step "Arrancando frontend (vite dev)..."
cd "$FRONTEND"
pnpm dev >"$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

for i in {1..15}; do
    if curl -sf http://localhost:5173 &>/dev/null; then
        ok "Frontend activo en http://localhost:5173  (PID $FRONTEND_PID)"
        break
    fi
    sleep 1
    if [ "$i" -eq 15 ]; then
        warn "Frontend tardó demasiado. Revisa $FRONTEND_LOG"
    fi
done

# ══════════════════════════════════════════════════════════════════════════════
# 4. RESUMEN Y APAGADO LIMPIO AL SALIR
# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  PokéGrading corriendo${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo "  Frontend  →  http://localhost:5173"
echo "  Backend   →  http://localhost:8000"
echo "  Swagger   →  http://localhost:8000/docs"
echo "  Logs      →  $LOG_DIR/"
echo ""
echo "  Presiona Ctrl+C para detener todo."
echo ""

cleanup() {
    echo ""
    step "Deteniendo servicios..."
    kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null && ok "Servicios detenidos"
    exit 0
}
trap cleanup INT TERM

wait
