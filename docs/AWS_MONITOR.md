# AWS va server kuzatuvi

Bot ichidagi yengil monitor (`services/server_monitor.py`) ikki ishni qiladi. Barcha
ogohlantirishlar `ADMIN_ID` ga Telegram orqali, **Redis/worker'siz** (`direct=True`) yuboriladi.

| Nima | Qachon | Ogohlantirish |
|------|--------|---------------|
| Disk ≥ 85%, bo'sh RAM < 150 MB | har 15 daqiqa | 🚨 paydo bo'lganda, 6 soatdan keyin eslatma, ✅ tiklanganda |
| Postgres / Redis javob bermasa | har 15 daqiqa | 🚨 / ✅ |
| Worker navbati > 500 | har 15 daqiqa | 🚨 (worker ishlamayapti) |
| AWS kredit kam qolsa (≤ 30 kunga yetadi yoki qolgan ≤ 20%) | har kuni 09:00 (Toshkent) | ⚠️ **har kuni** eslatadi; ≤ 7 kun qolsa 🚨 |

`/aws` buyrug'i (faqat `ADMIN_ID`/`MANAGER_ID`, shaxsiy chatda) server va kredit holatini
darhol ko'rsatadi (AWS qismi 30 daqiqa keshlanadi).

## AWS tomonini sozlash (bir marta, ~10 daqiqa)

AWS kaliti serverga qo'yilgani uchun **minimal huquqli** alohida IAM foydalanuvchi ishlating.

1. **Billing ma'lumotiga IAM kirishini yoqing** (root bilan): Account → *IAM user and role
   access to Billing information* → **Activate IAM Access**. Cost Explorer'ni ham yoqing
   (Billing → Cost Explorer → Launch; birinchi ma'lumot ~24 soatda paydo bo'ladi).
2. **Siyosat (policy)** yarating, masalan `kinobot-cost-readonly`:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       { "Effect": "Allow", "Action": ["ce:GetCostAndUsage"], "Resource": "*" }
     ]
   }
   ```
3. **IAM foydalanuvchi** yarating (masalan `kinobot-monitor`): *konsolga kirish yo'q*, faqat
   shu siyosat, so'ng **Access key** (use case: *Application running outside AWS*).
4. Kalitni serverdagi `~/kino_bot/.env` ga o'zingiz yozing (`chmod 600 .env` allaqachon).
   Chatga, git'ga yoki skrinshotga **qo'ymang**:
   ```
   AWS_ACCESS_KEY_ID=...
   AWS_SECRET_ACCESS_KEY=...
   AWS_CREDIT_TOTAL_USD=200
   AWS_CREDIT_START=2026-01-01
   AWS_CREDIT_EXPIRES=2026-12-31
   ```
   Kredit miqdori va sanalar: Billing → *Credits* sahifasida.
5. Qayta ishga tushiring: `docker compose --profile app up -d --build bot worker`
6. Botda `/aws` yuboring.

## Qanday hisoblanadi

- **Sarflangan kredit** = `AWS_CREDIT_START` dan beri Cost Explorer'dagi `Credit` yozuvlari yig'indisi.
- **Qolgan** = `AWS_CREDIT_TOTAL_USD` − sarflangan.
- **Balans yetadi** = qolgan / oxirgi 7 kunlik o'rtacha kunlik xarajat (kredit hisobga olinmagan).
- "Kam qoldi" sharti: balans yetadigan kun yoki `AWS_CREDIT_EXPIRES` gacha qolgan kun (**kichigi**) ≤ 30,
  yoki qolgan summa boshlang'ich kreditning ≤ 20% i. Shu holat davom etar ekan, har kuni 09:00 da eslatma keladi.
- Kredit yetarli bo'lsa (yuqoridagi shartlar bajarilmasa) bot jim turadi; `/aws` bilan istalgan payt ko'rasiz.
- Cost Explorer ma'lumoti **24 soatgacha kechikadi**; hisob taxminiy.

## Narx

Cost Explorer API'ga har so'rov ~$0.01. Sutkada 1 marta tekshiruv = 2 so'rov ≈ **$0.6/oy**;
`/aws` natijasi 30 daqiqa keshlanadi.

## Cheklovlar (bilib qo'ying)

- Monitor bot jarayoni ichida ishlaydi: **bot o'zi yiqilsa yoki instance o'chsa u ham jim bo'ladi.**
  Buning uchun AWS tomonida CloudWatch alarm (`StatusCheckFailed`) va **AWS Budgets** ogohlantirishini
  pochtaga ulang — ular serverdan mustaqil ishlaydi.
- Kredit tugasa AWS akkauntni to'xtatishi mumkin; **backup har 6 soatda Telegramga ketadi**, shuning
  uchun ma'lumot saqlanadi. Muhim eslatma: backup yuborilayotganini vaqti-vaqti bilan tekshiring.
- Kalit sizib chiqsa IAM'da darhol o'chiring (huquqi faqat o'qish, lekin xarajat ma'lumotini ochadi).

## Yakuniy to'xtatish rejimi (`/shutdown`)

Kredit tugab qolganda boshqa serverga o'tishni osonlashtiradi. **Faqat `ADMIN_ID`** ishlata oladi va faqat qat'iy tasdiq bilan:

1. `/shutdown` — bot AWS'dan kredit holatini qayta so'raydi. Kredit kam bo'lmasa (≤ 30 kun yoki ≤ 20%) yoki AWS'dan javob kelmasa — **rad etadi**.
2. Kredit kam bo'lsa, 2 daqiqa amal qiladigan bir martalik kod beradi: `TASDIQLAYMAN A1B2C3`. Kodni aynan shu ko'rinishda yuborish kerak. Xato/muddati o'tgan kod so'rovni bekor qiladi.
3. Tasdiqda kredit yana tekshiriladi, so'ng: yangi so'rovlar to'xtatiladi → **yangi zaxira** (`pg_dump`) → **`.env`** hujjat sifatida → ikkalasi yetib borgach `state/shutdown.lock` yoziladi → bot to'xtaydi.
4. Zaxira yoki `.env` yuborilmasa — to'xtatish **bekor qilinadi**, bot ishlashda davom etadi.

Qulf fayli bor ekan, `bot` va `worker` konteynerlari qayta ishga tushsa ham (reboot, `restart: always`) Telegramga ulanmaydi — yangi serverdagi bot bilan bir token ustida to'qnashmaydi.

Eski serverda qayta yoqish: `rm state/shutdown.lock && docker compose --profile app restart bot worker`.

⚠️ `.env` Telegram orqali yuboriladi (BOT_TOKEN, parollar, AWS kalitlari). Ko'chgach Telegramdagi xabarni o'chiring va tokenlarni yangilang.
