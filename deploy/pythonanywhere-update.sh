#!/bin/bash
# Force reinstall website command for EngineerTraining on PythonAnywhere.
set -euo pipefail

echo "USER=$USER"
PROJECT_DIR="$HOME/EngineerTraining"
VENV="$HOME/.virtualenvs/EngineerTraining"
DOMAIN="${PA_DOMAIN:-$USER.pythonanywhere.com}"
START="$PROJECT_DIR/deploy/pythonanywhere-start.sh"

if [[ ! -d "$PROJECT_DIR/.git" ]]; then
  echo "ERROR: $PROJECT_DIR not found. Clone first."
  exit 1
fi

cd "$PROJECT_DIR"
echo "=== git reset ==="
git remote -v
git fetch origin
git reset --hard origin/master
git log -1 --oneline

echo "=== clean pyc ==="
find "$PROJECT_DIR" -type d -name '__pycache__' -print0 2>/dev/null | xargs -0 rm -rf
find "$PROJECT_DIR" -type f -name '*.pyc' -delete 2>/dev/null || true

echo "=== venv ==="
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -r requirements.txt -q
pip install -U pythonanywhere -q

echo "=== verify routes in this code ==="
python - <<'PY'
from app.main import app, ACTIVITY_BUILD
paths = {getattr(r, "path", None) for r in app.routes}
print("BUILD", ACTIVITY_BUILD)
for p in ("/activity", "/activity/clear", "/health"):
    print(p, "OK" if p in paths else "MISSING")
if "/health" not in paths or "/activity" not in paths:
    raise SystemExit(2)
PY

chmod +x "$START"
echo "=== start command ==="
echo "$START"
head -n 5 "$START"

echo "=== recreate website $DOMAIN ==="
pa website delete --domain "$DOMAIN" 2>/dev/null || true
pa website create --domain "$DOMAIN" --command "$START"
pa website get --domain "$DOMAIN" || true

echo
echo "DONE. Wait 5 seconds then open:"
echo "  https://$DOMAIN/health"
echo "Expect: build activity-clear-v3"
