#!/usr/bin/env bash
# AWS kuzatuvi kalitlarini serverdagi .env ga xavfsiz yozish (lokal kompyuterdan ishga tushiring).
#
#   bash scripts/set_aws_keys.sh
#
# Kalitlar so'raladi (secret ekranda ko'rinmaydi), ssh stdin orqali uzatiladi — buyruq tarixi
# va jarayonlar ro'yxatiga (ps) tushmaydi. Bu faylning o'zida hech qanday sir yo'q.
set -euo pipefail

HOST="${KINO_HOST:-13.211.43.222}"
SSH_KEY="${KINO_SSH_KEY:-$HOME/Downloads/kino-bot.pem}"

[[ -f "$SSH_KEY" ]] || { echo "❌ SSH kalit topilmadi: $SSH_KEY (KINO_SSH_KEY bilan yo'lni bering)"; exit 1; }

read -r -p "AWS_ACCESS_KEY_ID: " AKID
read -r -s -p "AWS_SECRET_ACCESS_KEY (ko'rinmaydi): " SECRET; echo
echo "Quyidagi 3 tasi ixtiyoriy (bo'sh qoldirsangiz Enter). Billing → Credits sahifasida ko'rinadi."
read -r -p "Kredit miqdori, \$ (masalan 200): " TOTAL
read -r -p "Kredit boshlangan sana (YYYY-MM-DD): " START
read -r -p "Kredit tugash sanasi (YYYY-MM-DD): " EXPIRES

# Oddiy tekshiruvlar — xato kiritilgan qiymat .env ni buzmasin
[[ "$AKID" =~ ^(AKIA|ASIA)[A-Z0-9]{16}$ ]]  || { echo "❌ Access key formati noto'g'ri (AKIA... + 20 belgi)"; exit 1; }
[[ ${#SECRET} -eq 40 ]]                      || { echo "❌ Secret key 40 belgidan iborat bo'lishi kerak (siz ${#SECRET} kiritdingiz)"; exit 1; }
[[ -z "$TOTAL" || "$TOTAL" =~ ^[0-9]+([.][0-9]+)?$ ]]       || { echo "❌ Kredit miqdori raqam bo'lishi kerak"; exit 1; }
[[ -z "$START" || "$START" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]   || { echo "❌ Boshlanish sanasi YYYY-MM-DD bo'lishi kerak"; exit 1; }
[[ -z "$EXPIRES" || "$EXPIRES" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "❌ Tugash sanasi YYYY-MM-DD bo'lishi kerak"; exit 1; }

echo "⏳ Serverga yozilmoqda ($HOST)..."
# Eski AWS_* qatorlarini olib tashlab, yangilarini stdin'dan qo'shadi; oldingi .env .env.bak ga saqlanadi (600)
LINES=("AWS_ACCESS_KEY_ID=$AKID" "AWS_SECRET_ACCESS_KEY=$SECRET")
[[ -n "$TOTAL" ]]   && LINES+=("AWS_CREDIT_TOTAL_USD=$TOTAL")
[[ -n "$START" ]]   && LINES+=("AWS_CREDIT_START=$START")
[[ -n "$EXPIRES" ]] && LINES+=("AWS_CREDIT_EXPIRES=$EXPIRES")
printf '%s\n' "${LINES[@]}" |
ssh -i "$SSH_KEY" "ubuntu@$HOST" '
  set -e
  cd ~/kino_bot
  umask 077
  cp .env .env.bak
  grep -v "^AWS_" .env.bak > .env.new || true
  cat >> .env.new
  mv .env.new .env
  chmod 600 .env
'

echo "✅ .env yangilandi (kalit: ${AKID:0:4}…${AKID: -4}). Bot qayta ishga tushirilmoqda..."
ssh -i "$SSH_KEY" "ubuntu@$HOST" '
  cd ~/kino_bot
  sudo docker compose --profile app up -d --force-recreate bot >/dev/null 2>&1
  sleep 20
  sudo docker compose --profile app ps --format "{{.Name}} {{.Status}}"
  sudo docker compose --profile app logs --since 40s bot 2>&1 | grep -E "AWS|Application started|Traceback|ERROR" || true
'

unset AKID SECRET
echo
echo "Endi botda /aws yuboring. Eslatma: serverda ~/kino_bot/.env.bak (eski .env nusxasi) qoldi —"
echo "hammasi ishlaganini ko'rgach o'chiring:  ssh -i \"$SSH_KEY\" ubuntu@$HOST 'rm ~/kino_bot/.env.bak'"
