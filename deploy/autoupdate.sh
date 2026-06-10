#!/usr/bin/env bash
# Auto-update del bot: si hay commits nuevos en la rama, actualiza, corre las
# pruebas y reinicia el servicio. Si las pruebas fallan, revierte y avisa al
# webhook (no se despliega código roto).
#
# Pensado para ejecutarse como root vía systemd timer (ver DEPLOY.md §4.1).
set -euo pipefail

REPO=/home/tradebot/tradebot_alex
BRANCH=claude/awesome-galileo-rgtta1
RUN_AS=tradebot

as_user() { sudo -u "$RUN_AS" bash -c "cd '$REPO' && $*"; }

notify() {
    # Aviso opcional al webhook (Rook) usando las credenciales del .env
    local url token
    url=$(grep -E '^WEBHOOK_URL=' "$REPO/.env" 2>/dev/null | cut -d= -f2- || true)
    token=$(grep -E '^WEBHOOK_TOKEN=' "$REPO/.env" 2>/dev/null | cut -d= -f2- || true)
    [ -z "$url" ] && return 0
    curl -sS -m 10 -X POST "$url" \
        -H "Content-Type: application/json" \
        ${token:+-H "X-Webhook-Secret: $token"} \
        -d "{\"event\":\"autoupdate\",\"text\":\"$1\"}" >/dev/null || true
}

as_user "git fetch origin '$BRANCH' --quiet"
LOCAL=$(as_user "git rev-parse HEAD")
REMOTE=$(as_user "git rev-parse 'origin/$BRANCH'")

if [ "$LOCAL" = "$REMOTE" ]; then
    exit 0   # nada nuevo
fi

echo "Actualizando $(echo "$LOCAL" | cut -c1-7) -> $(echo "$REMOTE" | cut -c1-7)"
as_user "git pull --ff-only origin '$BRANCH'"
as_user "venv/bin/pip install -q -r requirements.txt"

if ! as_user "venv/bin/python -m pytest tests/ -q"; then
    echo "Las pruebas fallaron: revirtiendo a $LOCAL"
    as_user "git reset --hard '$LOCAL'"
    notify "⚠️ Auto-update revertido: las pruebas fallaron en $(echo "$REMOTE" | cut -c1-7). El bot sigue en la versión anterior."
    exit 1
fi

systemctl restart tradebot
echo "Bot actualizado a $(echo "$REMOTE" | cut -c1-7) y reiniciado"
notify "🔄 Bot actualizado a $(echo "$REMOTE" | cut -c1-7) y reiniciado (pruebas OK)."
