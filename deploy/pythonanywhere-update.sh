#!/bin/bash
# Force-update EngineerTraining on PythonAnywhere and restart the site.
set -euo pipefail

USERNAME="${USER:?}"
PROJECT_DIR="${PROJECT_DIR:-$HOME/EngineerTraining}"
VENV_NAME="${VENV_NAME:-EngineerTraining}"
PA_DOMAIN="${PA_DOMAIN:-${USERNAME}.pythonanywhere.com}"
START_CMD="$PROJECT_DIR/deploy/pythonanywhere-start.sh"

cd "$PROJECT_DIR"
git fetch origin
git reset --hard origin/master
find "$PROJECT_DIR" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
find "$PROJECT_DIR" -type f -name '*.pyc' -delete 2>/dev/null || true
chmod +x "$START_CMD"

# shellcheck disable=SC1091
source "$HOME/.virtualenvs/$VENV_NAME/bin/activate"
pip install -r requirements.txt -q

python - <<'PY'
from app.main import app
paths = sorted({getattr(r, "path", "") for r in app.routes})
need = ["/activity/clear", "/activity/clear-older", "/health"]
missing = [p for p in need if p not in paths]
print("routes_ok", not missing)
if missing:
    print("missing", missing)
    raise SystemExit(1)
for p in need:
    print(" ", p)
PY

if pa website get --domain "$PA_DOMAIN" >/dev/null 2>&1; then
  pa website delete --domain "$PA_DOMAIN" || true
fi
pa website create --domain "$PA_DOMAIN" --command "$START_CMD"

echo
echo "Updated. Open https://$PA_DOMAIN/health"
echo "Then try https://$PA_DOMAIN/activity"
