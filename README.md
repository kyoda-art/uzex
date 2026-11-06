# UZEX AI-agent — Telegram bot

UZEX birja bitimlari (2022–2026) bo'yicha savollarga **faqat ma'lumotga asoslangan** javob beradigan Telegram bot.

## Imkoniyatlar

| Menyu bo'limi | Nima qiladi |
|---|---|
| 📊 Market Intelligence | Bozor xulosasi: bitimlar soni, hajm, sotuvchi/xaridorlar |
| 🔎 Anomaly Hunter | Shartnoma medianasidan ±30%+ og'ishgan bitimlar; annulyatsiya ulushi yuqori sotuvchilar |
| 🔮 Future Vision | Oylik hajm prognozi (o'tgan yil mavsumiyligi × o'sish sur'ati) |
| 🌐 Trade Network | Eng yirik sotuvchi–xaridor juftliklari |
| 📑 Smart Reports | Xulosa + eng faol brokerlar |
| 🧠 NEXUS AI | Erkin savol rejimi |
| 🌍 Til / Language | O'zbekcha ↔ Русский (menyu tili) |

**Qo'shimcha imkoniyatlar:**
- **Manba:** har javob oxirida ishlatilgan fayllar ko'rsatiladi (`📎 Manba: deals_2025.csv, usd_rates.csv`).
- **Grafik:** narx dinamikasi, prognoz, yillik xulosa va TOP ro'yxatlar uchun rasm yuboriladi.
- **CSV fayl:** so'rovda `excel`, `csv`, `fayl` so'zi bo'lsa natija CSV ko'rinishida yuboriladi (UTF-8 BOM, Excel'da to'g'ri ochiladi).
- **Oldingi yil bilan solishtirish:** yil ko'rsatilgan javobda tugma bor, u bir yil oldingi natijani chiqaradi.
- **Anomaliya:** narx shartnoma medianasidan necha foiz farq qilgani ko'rsatiladi (`-34% medianadan`).

Erkin savollar ham ishlaydi: "Хлопок narxi 2025", "Dollar kursi 30.10.2026", "Eng yirik sotuvchilar 2026", "Keyingi 3 oy prognoz" va h.k.

**Qoidalar:**
- Raqamlar faqat CSV ma'lumotidan pandas bilan hisoblanadi — model raqam o'ylab topmaydi.
- Birja ma'lumotlari bo'lmagan savollarga: `CHAT_ENABLED=1` bo'lsa (standart) Gemini oddiy suhbat javobini beradi; `CHAT_ENABLED=0` bo'lsa yordam matni chiqadi. Hackathon qat'iy qoidasi uchun `CHAT_ENABLED=0` ni qo'ying.
- Savol qaysi tilda bo'lsa, javob o'sha tilda (o'zbekcha yoki ruscha).
- Eksport bitimlari (USD) bitim kunidagi kurs bo'yicha so'mga o'tkaziladi.
- Annulyatsiyalangan va imzolanmagan bitimlar tahlildan chiqariladi.

## Arxitektura

```
Telegram xabari
   │
   ▼
bot.py  ── menyu tugmalari, CSV/grafik yuborish, "Oldingi yil" tugmasi
   │
   ▼
core/router.py  ── savol → vosita + parametrlar
   │   ├─ Gemini (GEMINI_API_KEY bo'lsa): JSON yo'naltirish
   │   └─ kalit so'zlar (zaxira)
   ▼
core/analytics.py  ── pandas hisob-kitoblari (raqamlar faqat shu yerda)
   │
   ├─ core/formatter.py  → matn (uz/ru) + manba
   ├─ core/charts.py     → PNG grafik
   └─ core/export.py     → CSV fayl
   ▲
core/data.py  ── CSV yuklash, USD→so'm, annulyatsiyani chiqarish
```

Suhbat rejimi (`CHAT_ENABLED`) birja vositasi topilmagan savollarda Gemini bilan oddiy javob beradi.

## Testlar

```bash
python tests/test_core.py
```

Testlar raqamlarni to'g'ridan-to'g'ri hisoblash bilan solishtiradi (yillar yig'indisi, USD kurs bo'yicha konvertatsiya, anomaliya chegarasi, narx oralig'i) va chiqish formatlarini tekshiradi.

## Tuzilishi

```
uzex_bot/
├── bot.py            # Telegram bot (python-telegram-bot)
├── cli.py            # Terminal orqali sinash (Telegram shart emas)
├── core/
│   ├── data.py       # Ma'lumot yuklash (DATA_URL dan ham), tozalash
│   ├── analytics.py  # Tahlil funksiyalari
│   ├── charts.py     # Grafiklar (PNG)
│   ├── export.py     # CSV eksport
│   ├── health.py     # Monitor uchun HTTP javob
│   ├── router.py     # Savol → vosita (Gemini yoki kalit so'zlar)
│   └── formatter.py  # Javob matni (uz/ru)
├── tests/test_core.py  # Asosiy tekshiruvlar
├── DEMO.md           # Demo uchun savollar va kutilgan natijalar
├── render.yaml       # Render Blueprint
├── requirements.txt
└── .env.example
```

## Mahalliy ishga tushirish

1. Ma'lumotni joylashtiring: `uzex_spot_data.zip` ichidagi fayllarni `data/uzex_spot_data/` ga chiqaring.
2. `pip install -r requirements.txt`
3. `cp .env.example .env` — ichiga `TELEGRAM_BOT_TOKEN` (va ixtiyoriy `GEMINI_API_KEY`) ni yozing.
4. `set -a; source .env; set +a`
5. Terminalda sinash: `python cli.py` (Telegram kerak emas)
6. Botni ishga tushirish: `python bot.py`

## GitHub va Render'ga joylash

**1. Ma'lumotni GitHub Release'ga yuklang** (repozitoriyaga emas):
- GitHub'da repo → Releases → "Create a new release" → `uzex_spot_data.zip` ni asset sifatida yuklang.
- Yuklangan faylning to'g'ridan-to'g'ri havolasini nusxalang (`.../releases/download/v1/uzex_spot_data.zip`).

**2. Kodni GitHub'ga yuklang:**
```bash
git init && git add . && git commit -m "UZEX bot"
git branch -M main
git remote add origin https://github.com/<user>/<repo>.git
git push -u origin main
```

**3. Render'da:**
- New → **Blueprint** → repo'ni tanlang (`render.yaml` avtomatik o'qiladi).
- Environment bo'limida qiymatlarni kiriting:
  - `TELEGRAM_BOT_TOKEN` — BotFather tokeni
  - `DATA_URL` — 1-qadamdagi havola
  - `GEMINI_API_KEY` — ixtiyoriy; kalit bo'lmasa qoidalar rejimi ishlaydi
- Deploy. Birinchi ishga tushishda ma'lumot yuklab olinadi (bir necha soniya).

Bot bepul **Web Service** sifatida ishlaydi (webhook rejimi). Render `PORT` va `RENDER_EXTERNAL_URL` ni o'zi beradi, bot Telegram'ga shu manzilni ro'yxatdan o'tkazadi. Bepul servis bo'sh turganda uxlaydi, lekin xabar kelganda uyg'onadi (birinchi javob bir necha soniya kechikishi mumkin).

## Gemini haqida

- `GEMINI_API_KEY` bo'lsa, Gemini savolni tushunib, kerakli tahlil vositasi va parametrlarini (yil, mahsulot, sana) JSON ko'rinishida qaytaradi.
- Kalit bo'lmasa yoki model xato qilsa, bot kalit so'zlarga asoslangan qoidalar bilan ishlaydi.
- Model nomini `GEMINI_MODEL` orqali o'zgartirish mumkin.
- Kalitni qo'shish uchun kod o'zgarishi shart emas: Render'da `GEMINI_API_KEY` ni kiritib, qayta deploy qiling.

## Ma'lum cheklovlar

- Mahsulot nomi bosh so'z bo'yicha moslanadi (masalan "хлопок", "paxta"). Boshqa sinonimlar uchun `core/analytics.py` dagi `UZ_SYNONYMS` ni kengaytiring yoki Gemini rejimidan foydalaning.
- Prognoz taxminiy — kafolatlangan bashorat emas.
- Grafiklar uchun matplotlib xotira qo'shadi (taxminan 60–80 MB). Bepul tarifda (512 MB) odatda yetadi, lekin bot uzoq ishlasa xotirani kuzating.
- Gemini kaliti yoki kvotasi tugasa, bot kalit so'zlar rejimiga o'tadi va javob berishda davom etadi.
- Ma'lumot 2026-yil 30-oktabrgacha.
