#!/usr/bin/env bash
# ngrok authtoken'ni serverdagi .env ga xavfsiz yozish va panelni ishga tushirish (lokal kompyuterdan).
#
#   bash scripts/set_ngrok_token.sh
#
# Token: https://dashboard.ngrok.com/get-started/your-authtoken  (ekranda ko'rinmaydi, ssh stdin orqali uzatiladi).
# Ixtiyoriy: bepul doimiy domen (https://dashboard.ngrok.com/domains) — havola o'zgarmaydi.
set -euo pipefail

HOST="${KINO_HOST:-104.166.88.8}"
USER="${KINO_USER:-root}"
SSH_KEY="${KINO_SSH_KEY:-$HOME/.ssh/kino_bot_deploy}"

[[ -f "$SSH_KEY" ]] || { echo "❌ SSH kalit topilmadi: $SSH_KEY (KINO_SSH_KEY bilan yo'lni bering)"; exit 1; }

read -r -s -p "NGROK_AUTHTOKEN (ko'rinmaydi): " TOKEN; echo
read -r -p "Doimiy domen, masalan nomi.ngrok-free.app (ixtiyoriy, Enter): " DOMAIN

[[ "$TOKEN" =~ ^[A-Za-z0-9_]{20,}$ ]] || { echo "❌ Token formati noto'g'ri"; exit 1; }
[[ -z "$DOMAIN" || "$DOMAIN" =~ ^[A-Za-z0-9.-]+\.(ngrok-free\.(app|dev)|ngrok\.(app|dev|io))$ ]] || { echo "❌ Domen formati noto'g'ri"; exit 1; }

LINES=("NGROK_AUTHTOKEN=$TOKEN")
[[ -n "$DOMAIN" ]] && LINES+=("NGROK_EXTRA=--url=$DOMAIN")

echo "⏳ Serverga yozilmoqda ($HOST)..."
printf '%s\n' "${LINES[@]}" |
ssh -i "$SSH_KEY" "$USER@$HOST" '
  set -e
  cd /root/kino_bot
  umask 077
  grep -vE "^(NGROK_AUTHTOKEN|NGROK_EXTRA)=" .env > .env.new || true
  cat >> .env.new
  mv .env.new .env
  chmod 600 .env
'

echo "✅ .env yangilandi. Panel qayta ishga tushirilmoqda..."
ssh -i "$SSH_KEY" "$USER@$HOST" '
  cd /root/kino_bot
  docker compose --profile app up -d --force-recreate ngrok webapp >/dev/null 2>&1
  sleep 10
  docker compose --profile app ps --format "table {{.Name}}\t{{.Status}}" | grep -E "ngrok|webapp|dockerproxy"
  docker compose --profile app logs --since 30s webapp 2>&1 | grep -E "Panel havolasi|ngrok|Traceback|ERROR" || true
'
unset TOKEN
echo
echo "Botda /panel yuboring (yoki chat menyusidagi «📊 Server» tugmasini oching)."
