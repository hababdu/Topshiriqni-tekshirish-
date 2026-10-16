# uyvazifa-bot 📚

Telegram guruhda o'qiydigan o'quvchilar uchun uy vazifalarini qabul qiluvchi va baholovchi bot.

## Imkoniyatlar

- **O'quvchi**: guruh a'zosi ekanini bot tekshiradi, ism-familiya bilan ro'yxatdan o'tadi, vazifani tanlab **video / PDF / rasm / ovoz / matn** yuboradi (bir hafta davomida istalgancha).
- **Yopiq kanal = server**: har bir topshirilgan ish avtomatik yopiq Telegram kanalga nusxalanadi (kim, qaysi vazifa, qachon — izoh bilan). Kanal fayllar ombori vazifasini bajaradi.
- **Admin (o'qituvchi)**: yangi vazifa qo'shadi (guruhga e'lon bo'ladi), ishlarni birma-bir ko'rib **0–10 ball** qo'yadi. O'quvchiga baho haqida xabar boradi.
- **Statistika va diagramma**: haftalik hisobot (reyting + diagramma), o'quvchi o'z natijasi va 8 haftalik o'sish grafigini ko'radi.
- **Eslatmalar**: har kuni belgilangan soatda o'sha kuni hech narsa topshirmagan o'quvchilarga bot eslatma yuboradi. Yakshanba kuni 20:00 da adminga tekshirish vaqti kelgani aytiladi.

## Buyruqlar

| Kim | Buyruq | Vazifasi |
|---|---|---|
| Admin | `/vazifa` | yangi vazifa qo'shish |
| Admin | `/tekshir` | ishlarni ko'rib baholash |
| Admin | `/hisobot` , `/hisobot 1` | shu / o'tgan hafta statistikasi (guruhga yuborish tugmasi bor) |
| Admin | `/oquvchilar` | ro'yxatdan o'tganlar |
| Admin | `/bekor` | joriy amalni bekor qilish |
| O'quvchi | `/start` | ro'yxatdan o'tish / menyu |

O'quvchi menyusi: **📤 Vazifa topshirish**, **📋 Vazifalar**, **📊 Mening natijam**.

## O'rnatish

1. **Bot yaratish**: [@BotFather](https://t.me/BotFather) → `/newbot` → tokenni oling.
2. **Yopiq kanal**: yangi *private* kanal oching, botni **administrator** qiling (xabar yuborish huquqi bilan).
3. **Guruh**: botni o'quvchilar guruhiga qo'shing (a'zolikni tekshirish va e'lon yuborish uchun).
4. **ID larni aniqlash**: guruh va kanal ID si (`-100...` bilan boshlanadi), adminning shaxsiy ID si. Buning uchun masalan [@RawDataBot](https://t.me/RawDataBot) yoki [@userinfobot](https://t.me/userinfobot) dan foydalanish mumkin.
5. Sozlamalar:

```bash
cp .env.example .env   # va ichini to'ldiring
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

### Docker bilan

```bash
docker build -t uyvazifa-bot .
docker run -d --restart=always --env-file .env -v $(pwd)/data:/srv/bot/data uyvazifa-bot
```

> `data/` papkasida SQLite bazasi saqlanadi — uni zaxiralab turing. Fayllarning o'zi yopiq kanalda turadi.

## Tuzilishi

```
app/
  main.py        # ishga tushirish
  config.py      # .env sozlamalari
  db.py          # SQLite (o'quvchilar, vazifalar, topshiriqlar, ballar)
  handlers/
    student.py   # ro'yxatdan o'tish, topshirish, natijam
    admin.py     # vazifa, tekshirish, hisobot
  charts.py      # matplotlib diagrammalari
  scheduler.py   # kunlik eslatma va hafta oxiri xabari
  keyboards.py   # tugmalar
  timeutil.py    # hafta/kun hisoblari (dushanbadan boshlanadi)
```

## Eslatma

- Hafta dushanbadan yakshanbagacha hisoblanadi; o'quvchilar faqat **joriy hafta** vazifalariga ish topshiradi.
- Bot shaxsiy xabarda ishlaydi, shuning uchun o'quvchilar botga avval `/start` bosishi kerak (aks holda Telegram bot yozishiga ruxsat bermaydi).
- Bot polling rejimida ishlaydi — domen yoki SSL kerak emas, oddiy VPS yetarli.
