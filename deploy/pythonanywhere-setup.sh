#!/bin/bash
# One-time setup on PythonAnywhere Bash console.
set -euo pipefail

USERNAME="${USER:?Run this script on PythonAnywhere}"
REPO_URL="${REPO_URL:-https://github.com/asmeal4/EngineerTraining.git}"
PROJECT_DIR="${PROJECT_DIR:-$HOME/EngineerTraining}"
VENV_NAME="${VENV_NAME:-EngineerTraining}"
PA_DOMAIN="${PA_DOMAIN:-${USERNAME}.pythonanywhere.com}"

echo "=== Project: $PROJECT_DIR ==="
if [[ -d "$PROJECT_DIR/.git" ]]; then
  cd "$PROJECT_DIR"
  git pull
else
  git clone "$REPO_URL" "$PROJECT_DIR"
  cd "$PROJECT_DIR"
fi

echo "=== Virtualenv: $VENV_NAME ==="
VENV_DIR="$HOME/.virtualenvs/$VENV_NAME"
if [[ ! -d "$VENV_DIR" ]]; then
  mkdir -p "$HOME/.virtualenvs"
  if command -v mkvirtualenv >/dev/null 2>&1; then
    mkvirtualenv --python=python3.10 "$VENV_NAME"
  else
    python3.10 -m venv "$VENV_DIR"
  fi
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt
pip install --upgrade pythonanywhere

echo "=== Environment file ==="
ENV_FILE="$PROJECT_DIR/deploy/pythonanywhere.env"
if [[ ! -f "$ENV_FILE" ]]; then
  cp "$PROJECT_DIR/deploy/pythonanywhere.env.example" "$ENV_FILE"
  SECRET_KEY="$(python -c "import secrets; print(secrets.token_hex(32))")"
  sed -i "s/change-this-to-a-long-random-string/$SECRET_KEY/" "$ENV_FILE"
  echo "Created $ENV_FILE"
  echo "Edit DEFAULT_PASSWORD in that file before sharing the site."
fi

chmod +x "$PROJECT_DIR/deploy/pythonanywhere-start.sh"
START_CMD="$PROJECT_DIR/deploy/pythonanywhere-start.sh"

echo "=== Website: $PA_DOMAIN ==="
if pa website get --domain "$PA_DOMAIN" >/dev/null 2>&1; then
  pa website reload --domain "$PA_DOMAIN"
  echo "Website reloaded."
else
  pa website create --domain "$PA_DOMAIN" --command "$START_CMD"
  echo "Website created."
fi

echo
echo "Open: https://$PA_DOMAIN"
echo "After code changes: pa website reload --domain $PA_DOMAIN"
echo "Logs: /var/log/$PA_DOMAIN.error.log"
