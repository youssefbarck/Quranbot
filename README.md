# 📖 بوت الحصون الخمسة لحفظ القرآن الكريم

بوت تلغرام ذكي يحفظ تقدمك في حفظ القرآن بنظام "الحصون الخمسة" المتكامل.

## 🏰 الحصون الخمسة

| # | الحصن | المعنى | التكرار |
|---|------|--------|---------|
| 1️⃣ | الحفظ اليومي | حفظ صفحة جديدة كل يوم | يومياً |
| 2️⃣ | المراجعة اليومية | مراجعة ما حُفظ اليوم | يومياً (مساءً) |
| 3️⃣ | الحفظ الأسبوعي | مراجعة آخر 7 أيام | يومياً |
| 4️⃣ | المراجعة الأسبوعية | 5 مرات: ليلة، ليل، ثلث، اربعاء، خميس | موزعة |
| 5️⃣ | المراجعة الشهرية | مراجعة كل صفحات الشهر | نهاية الشهر |

## ⏰ التذكيرات اليومية

| الوقت | التذكير |
|-------|---------|
| 🌅 08:00 صباحاً | قراءة حزبين (20 صفحة) |
| ☀️ 13:00 ظهراً | الاستماع لحزب (10 صفحات) |
| 🌙 20:00 مساءً | سؤال تفاعلي: "هل أنهيت الحفظ؟" |

> يمكن تغيير الأوقات لاحقاً عبر `/settime`

## 📦 بنية المشروع

```
Quranbot/
├── bot.py              ← كل المنطق في ملف واحد
├── quran_data.py       ← بيانات القرآن (114 سورة + 604 صفحة)
├── requirements.txt
├── runtime.txt
├── render.yaml
├── .env.example
└── README.md
```

## 🚀 النشر على Render (مجاني)

### 1) أنشئ البوت
- افتح [@BotFather](https://t.me/BotFather) في تلغرام
- أرسل `/newbot` واتبع التعليمات
- احفظ التوكن

### 2) أنشئ قاعدة بيانات Neon
- اذهب إلى [neon.tech](https://neon.tech) وسجّل
- أنشئ مشروع جديد → انسخ `DATABASE_URL` (يبدأ بـ `postgresql://`)

### 3) ارفع الكود إلى GitHub
- أنشئ مستودعاً جديداً (مثل `Quranbot`)
- ارفع **كل ملفات المشروع إلى جذر المستودع** (وليس داخل مجلد فرعي)

### 4) اربط Render بـ GitHub
1. اذهب إلى [render.com](https://render.com)
2. اختر **New + → Web Service**
3. اربط GitHub واختر المستودع
4. اترك الإعدادات الافتراضية:
   - Type: **Web Service**
   - Environment: **Python 3**
   - Plan: **Free**
   - Build: `pip install -r requirements.txt`
   - Start: `python bot.py`
   - Health Check Path: `/health`
5. أضف متغيرات البيئة:

| المتغير | القيمة |
|---------|--------|
| `TELEGRAM_BOT_TOKEN` | التوكن من BotFather |
| `DATABASE_URL` | رابط Neon |
| `ADMIN_TELEGRAM_ID` | معرّفك في تلغرام |
| `MORNING_TIME` | `08:00` |
| `MIDDAY_TIME` | `13:00` |
| `EVENING_TIME` | `20:00` |
| `DEFAULT_TIMEZONE` | `Africa/Algiers` |
| `KEEPALIVE_ENABLED` | `true` |
| `KEEPALIVE_INTERVAL` | `280` |

6. اضغط **Create Web Service** وانتظر 1-2 دقيقة

> 📌 `PORT` و `RENDER_EXTERNAL_URL` يُحقنهما Render تلقائياً.

### 5) تفعيل البوت
- ابحث عن البوت في تلغرام
- أرسل `/start`
- أجب على السؤال: "ماذا حفظت؟"
- استخدم `/today` لمهام اليوم

## 📋 الأوامر

| الأمر | الوصف |
|-------|-------|
| `/start` | البدء + التهيئة التفاعلية |
| `/today` | مهام اليوم كاملة |
| `/fortresses` | عرض الحصون الخمسة |
| `/progress` | تقدمك في الحفظ |
| `/setpage <رقم>` | تحديد صفحتك الحالية |
| `/settime morning 08:00` | تغيير وقت الصباح |
| `/settime midday 13:00` | تغيير وقت الظهيرة |
| `/settime evening 20:00` | تغيير وقت المساء |
| `/timezone Africa/Algiers` | تحديد المنطقة الزمنية |
| `/markdone reading` | تسجيل إتمام القراءة |
| `/markdone listening` | تسجيل إتمام الاستماع |
| `/markdone memorize` | تسجيل إتمام الحفظ |
| `/markdone daily_review` | تسجيل إتمام المراجعة اليومية |
| `/markdone weekly <page>` | تسجيل إتمام مراجعة أسبوعية |
| `/reset` | إعادة التهيئة |
| `/help` | دليل الأوامر |

## 🔧 keep-alive مدمج

البوت يستخدم خادم HTTP بسيط على المنفذ الذي يعطيه Render، ومهمة async تصنع self-ping كل 280 ثانية على الـ URL العام. هذا الطلب يأتي من الإنترنت فيعتبره Render نشاطاً ويمنع الخدمة من النوم على الخطة المجانية — دون الحاجة لـ UptimeRobot أو أي منصة خارجية.

## 🛠️ التقنيات المستخدمة

- Python 3.11
- python-telegram-bot v21 (async)
- SQLAlchemy 2.0 + asyncpg (Neon Postgres)
- APScheduler (جدولة التذكيرات)
- aiohttp (خادم keep-alive + self-ping)
- Render Web Service (Free)
