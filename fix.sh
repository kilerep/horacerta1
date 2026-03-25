#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

APP_MODULES="${APP_MODULES:-accounts companies timeclock}"
VENV_DIR="${VENV_DIR:-.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
RESET_MIGRATIONS="${RESET_MIGRATIONS:-0}"
REBUILD_VENV="${REBUILD_VENV:-1}"
RESTART_SERVICES="${RESTART_SERVICES:-1}"
STRICT_DATABASE_URL="${STRICT_DATABASE_URL:-0}"

mkdir -p "$BACKUP_DIR"
export STRICT_DATABASE_URL

echo "[1/8] Backup de banco"
if [[ -f "$PROJECT_DIR/db.sqlite3" ]]; then
  cp "$PROJECT_DIR/db.sqlite3" "$BACKUP_DIR/db.sqlite3.$(date +%Y%m%d_%H%M%S).bak"
  echo " - backup sqlite criado"
elif [[ -n "${DATABASE_URL:-}" ]] && command -v pg_dump >/dev/null 2>&1; then
  pg_dump "$DATABASE_URL" > "$BACKUP_DIR/postgres.$(date +%Y%m%d_%H%M%S).sql"
  echo " - backup postgres criado"
else
  echo " - backup de banco ignorado (sem sqlite local e/ou pg_dump indisponivel)"
fi

echo "[2/8] Recriar venv"
if [[ "$REBUILD_VENV" == "1" ]]; then
  rm -rf "$VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "[3/8] Instalar dependencias"
python -m pip install --upgrade pip setuptools wheel
if [[ -f requirements.txt ]]; then
  pip install -r requirements.txt
else
  pip install "Django>=5,<7" psycopg2-binary
fi
# fallback explicito pedido no incidente
pip install psycopg2-binary || true

echo "[4/8] Diagnostico django"
python manage.py check

echo "[5/8] Migracoes"
if [[ "$RESET_MIGRATIONS" == "1" ]]; then
  echo " - reset seguro de migrations habilitado"
  for app in $APP_MODULES; do
    app_migrations="$PROJECT_DIR/$app/migrations"
    if [[ -d "$app_migrations" ]]; then
      find "$app_migrations" -maxdepth 1 -type f -name "*.py" ! -name "__init__.py" -delete
      find "$app_migrations" -maxdepth 1 -type f -name "*.pyc" -delete || true
    fi
  done
  python manage.py makemigrations $APP_MODULES
else
  python manage.py makemigrations
fi

python manage.py migrate --fake-initial
python manage.py migrate

echo "[6/8] Validacoes finais"
python manage.py check
if python manage.py migrate --help | grep -q -- "--check"; then
  python manage.py migrate --check
fi

echo "[7/8] Smoke test urls"
python manage.py shell -c "from django.test import Client; c=Client(); urls=['/empresa/','/empresa/contratos/']; bad=[]; \
[(bad.append((u, r.status_code)) if (r:=c.get(u, follow=False)).status_code not in (200,302,403) else None) for u in urls]; \
print('SMOKE_OK' if not bad else f'SMOKE_FAIL:{bad}'); \
import sys; sys.exit(0 if not bad else 1)"

echo "[8/8] Restart de servicos"
if [[ "$RESTART_SERVICES" == "1" ]] && command -v systemctl >/dev/null 2>&1; then
  sudo systemctl restart gunicorn || true
  sudo systemctl restart nginx || true
  sudo systemctl restart horacerta || true
fi

echo "Recuperacao finalizada com sucesso."
