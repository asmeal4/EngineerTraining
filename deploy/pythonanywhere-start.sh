#!/bin/bash
# ASGI entrypoint for PythonAnywhere (DOMAIN_SOCKET is provided by the platform).
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${APP_DIR}/deploy/pythonanywhere.env"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%$'\r'}"
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
      export "${BASH_REMATCH[1]}=${BASH_REMATCH[2]}"
    fi
  done < "$ENV_FILE"
  set +a
fi

VENV_UVICORN="${VENV_UVICORN:-$HOME/.virtualenvs/EngineerTraining/bin/uvicorn}"

exec "$VENV_UVICORN" \
  --app-dir "$APP_DIR" \
  --uds "${DOMAIN_SOCKET}" \
  app.main:app
