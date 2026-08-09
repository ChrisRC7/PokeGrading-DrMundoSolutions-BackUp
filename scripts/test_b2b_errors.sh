#!/usr/bin/env bash
#
# test_b2b_errors.sh — Prepara, uno por uno, cada escenario de error/estado del
# API B2B (US-005) para probarlos en Swagger, y luego REVIERTE cada cambio.
#
# Es INTERACTIVO: aplica un escenario, te pide probarlo en Swagger
# (http://localhost:8000/docs → POST /api/b2b/v1/catalog/lookup) y al presionar
# Enter lo deshace antes de pasar al siguiente. Al salir (incluso con Ctrl-C)
# restaura SIEMPRE el estado base (key activa, sin expiración, customer activo,
# límite 1000, sin contadores, sin cartas MULTI).
#
# Uso:
#   ./scripts/test_b2b_errors.sh
#
set -uo pipefail

# ── Conexión a la BD ──────────────────────────────────────────────────────────
export PGPASSWORD="${PGPASSWORD:-chris}"
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5433}"
PGUSER="${PGUSER:-pokegrading}"
PGDATABASE="${PGDATABASE:-pokegrading_dev}"

KEY_PREFIX="5b63fbc4"        # prefijo de tu API key activa
CUSTOMER_NAME="Tienda Demo"  # nombre del customer dueño de la key

psql_exec() {
  psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -v ON_ERROR_STOP=1 -q -c "$1"
}

pause() {
  echo ""
  read -r -p "  ↳ Pruébalo en Swagger y presiona [Enter] para REVERTIR... " _
}

restore_base_state() {
  echo ""
  echo "── Restaurando estado base ─────────────────────────────────────────"
  psql_exec "UPDATE api_keys SET status='active', expires_at=NULL, grace_period_until=NULL,
             rate_limit_cards_per_window=1000 WHERE key_prefix='${KEY_PREFIX}';"
  psql_exec "UPDATE b2b_customers SET status='active' WHERE name='${CUSTOMER_NAME}';"
  psql_exec "DELETE FROM b2b_rate_limit_counters;"
  psql_exec "DELETE FROM catalog_cards WHERE set_name='MULTI';"
  echo "  ✔ Estado base restaurado (key activa, customer activo, límite 1000)."
}

# Garantiza la restauración pase lo que pase (Ctrl-C, error, fin normal).
trap restore_base_state EXIT

banner() {
  echo ""
  echo "════════════════════════════════════════════════════════════════════"
  echo " $1"
  echo "════════════════════════════════════════════════════════════════════"
}

# ──────────────────────────────────────────────────────────────────────────────
echo "Recuerda usar tu API key completa en el header  X-API-Key:"
echo "    pkg_live_${KEY_PREFIX}_<tu-secreto>"
echo ""
echo "Endpoint:  POST http://localhost:8000/api/b2b/v1/catalog/lookup"

# ── E) multiple_match ─────────────────────────────────────────────────────────
banner "E) multiple_match  →  200 con status='multiple_match'"
psql_exec "INSERT INTO catalog_cards (id, name, set_name, card_number, edition, language, finish, status, version, created_by, created_at)
           SELECT gen_random_uuid(), 'Multi Test', 'MULTI', '1/1', 'Unlimited', 'en', 'holo', 'active', 1, u.id, now()
           FROM users u LIMIT 1;"
psql_exec "INSERT INTO catalog_cards (id, name, set_name, card_number, edition, language, finish, status, version, created_by, created_at)
           SELECT gen_random_uuid(), 'Multi Test', 'MULTI', '1/1', 'Unlimited', 'en', 'reverse holo', 'active', 1, u.id, now()
           FROM users u LIMIT 1;"
echo "  Body:"
echo '    { "cards": [ { "set": "MULTI", "number": "1/1" } ] }'
echo "  Esperado: results[0].status = \"multiple_match\" con 2 candidates."
pause
psql_exec "DELETE FROM catalog_cards WHERE set_name='MULTI';"
echo "  ✔ Cartas MULTI eliminadas."

# ── D12) 429 RATE_LIMIT_EXCEEDED ──────────────────────────────────────────────
banner "D12) 429 RATE_LIMIT_EXCEEDED"
psql_exec "UPDATE api_keys SET rate_limit_cards_per_window=2 WHERE key_prefix='${KEY_PREFIX}';"
psql_exec "DELETE FROM b2b_rate_limit_counters;"
echo "  Límite temporal = 2 cartas por ventana."
echo "  Body (3 cartas, SIN Idempotency-Key):"
echo '    { "cards": [ {"set":"1","number":"1/123"}, {"set":"1","number":"2/132"}, {"set":"1","number":"1/18"} ] }'
echo "  Esperado: HTTP 429, code=RATE_LIMIT_EXCEEDED, header Retry-After."
pause
psql_exec "UPDATE api_keys SET rate_limit_cards_per_window=1000 WHERE key_prefix='${KEY_PREFIX}';"
psql_exec "DELETE FROM b2b_rate_limit_counters;"
echo "  ✔ Límite restaurado a 1000 y contadores limpiados."

# ── D13a) 401 API_KEY_REVOKED ─────────────────────────────────────────────────
banner "D13a) 401 API_KEY_REVOKED"
psql_exec "UPDATE api_keys SET status='revoked' WHERE key_prefix='${KEY_PREFIX}';"
echo "  Body: cualquiera, p.ej. { \"cards\": [ {\"set\":\"1\",\"number\":\"1/123\"} ] }"
echo "  Esperado: HTTP 401, code=API_KEY_REVOKED."
pause
psql_exec "UPDATE api_keys SET status='active' WHERE key_prefix='${KEY_PREFIX}';"
echo "  ✔ Key reactivada."

# ── D13b) 401 API_KEY_SUSPENDED ───────────────────────────────────────────────
banner "D13b) 401 API_KEY_SUSPENDED"
psql_exec "UPDATE api_keys SET status='suspended' WHERE key_prefix='${KEY_PREFIX}';"
echo "  Esperado: HTTP 401, code=API_KEY_SUSPENDED."
pause
psql_exec "UPDATE api_keys SET status='active' WHERE key_prefix='${KEY_PREFIX}';"
echo "  ✔ Key reactivada."

# ── D14) 401 API_KEY_EXPIRED ──────────────────────────────────────────────────
banner "D14) 401 API_KEY_EXPIRED"
psql_exec "UPDATE api_keys SET status='active', expires_at='2020-01-01', grace_period_until='2020-01-02'
           WHERE key_prefix='${KEY_PREFIX}';"
echo "  Caducada y fuera del periodo de gracia."
echo "  Esperado: HTTP 401, code=API_KEY_EXPIRED."
pause
psql_exec "UPDATE api_keys SET expires_at=NULL, grace_period_until=NULL WHERE key_prefix='${KEY_PREFIX}';"
echo "  ✔ Expiración eliminada."

# ── D15) 403 CUSTOMER_SUSPENDED ───────────────────────────────────────────────
banner "D15) 403 CUSTOMER_SUSPENDED"
psql_exec "UPDATE b2b_customers SET status='suspended' WHERE name='${CUSTOMER_NAME}';"
echo "  Esperado: HTTP 403, code=CUSTOMER_SUSPENDED."
pause
psql_exec "UPDATE b2b_customers SET status='active' WHERE name='${CUSTOMER_NAME}';"
echo "  ✔ Customer reactivado."

banner "Listo. Todos los escenarios D y E probados."
# El trap EXIT ejecuta restore_base_state una última vez por seguridad.
