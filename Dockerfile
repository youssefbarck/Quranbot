FROM python:3.11-slim

# تثبيت الحزم النظامية اللازمة لـ psycopg2
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# تثبيت المتطلبات أولاً (للاستفادة من الكاش)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي الملفات
COPY . .

# تشغيل البوت
CMD ["python", "-m", "bot.main"]
