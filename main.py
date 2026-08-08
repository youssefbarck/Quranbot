"""
النقطة الرئيسية لتشغيل البوت — طريقة الحصون الخمسة

الاستراتيجية على Render Free:
- البوت في وضع polling (يستقبل رسائل تيليجرام بـ long polling — آمن وبسيط)
- خادم HTTP صغير على بورت Render (PORT) يقدم endpoint /health
- مهمة self-ping كل 280 ثانية على RENDER_EXTERNAL_URL/health
  ← هذا الطلب يأتي من الإنترنت فيعتبره Render نشاطاً ويبقي الخدمة مستيقظة

لا حاجة لـ UptimeRobot أو منصة خارجية — كل شيء ذاتي.
"""
import asyncio
import logging
import sys

from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ApplicationBuilder,
)

from .config import config
from .database import init_db
from .handlers import (
    start_command, help_command, today_command, fortresses_command,
    progress_command, setpage_command, markdone_command,
    settime_command, timezone_command, reset_command,
    button_callback, handle_free_text,
)
from .scheduler import (
    evening_yes_callback, evening_later_callback,
)
from . import scheduler as bot_scheduler
from .keepalive import start_keepalive_server

logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def build_application() -> Application:
    if not config.BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN غير مضبوط")
        sys.exit(1)

    app = ApplicationBuilder().token(config.BOT_TOKEN).build()

    # الأوامر
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("today", today_command))
    app.add_handler(CommandHandler("fortresses", fortresses_command))
    app.add_handler(CommandHandler("progress", progress_command))
    app.add_handler(CommandHandler("setpage", setpage_command))
    app.add_handler(CommandHandler("markdone", markdone_command))
    app.add_handler(CommandHandler("settime", settime_command))
    app.add_handler(CommandHandler("timezone", timezone_command))
    app.add_handler(CommandHandler("reset", reset_command))

    # معالج الرسائل الحرة (للتهيئة التفاعلية)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text))

    # الأزرار
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^(today|fortresses|progress|settings)$"))
    app.add_handler(CallbackQueryHandler(evening_yes_callback, pattern="^evening_yes$"))
    app.add_handler(CallbackQueryHandler(evening_later_callback, pattern="^evening_later$"))

    return app


async def post_init(app: Application):
    logger.info("🔧 تهيئة قاعدة البيانات...")
    await init_db()
    logger.info("✅ قاعدة البيانات جاهزة")

    logger.info("⏰ تشغيل المجدول...")
    bot_scheduler.start_scheduler(app.bot)
    asyncio.create_task(_periodic_reschedule(app.bot))


async def _periodic_reschedule(bot):
    """يعيد بناء الجدول كل ساعة"""
    while True:
        await asyncio.sleep(3600)
        try:
            await bot_scheduler.reschedule_all(bot)
        except Exception as e:
            logger.error(f"خطأ في إعادة الجدولة: {e}")


async def _run_polling_with_keepalive():
    """يشغّل البوت بـ polling + خادم keep-alive في نفس الـ event loop"""
    app = build_application()

    # بدء خادم keep-alive أولاً (لو احتجنا فحص صحة قبل بدء البوت)
    keepalive_runner = None
    keepalive_task = None
    if config.KEEPALIVE_ENABLED:
        public_url = config.public_health_url()
        logger.info(f"🌐 بدء خادم keep-alive على المنفذ {config.PORT}...")
        keepalive_runner, keepalive_task = await start_keepalive_server(
            port=config.PORT,
            public_health_url=public_url,
            keepalive_interval=config.KEEPALIVE_INTERVAL,
        )
        if public_url:
            logger.info(f"✅ keep-alive نشط — self-ping كل {config.KEEPALIVE_INTERVAL} ثانية إلى {public_url}")
        else:
            logger.warning("⚠️ RENDER_EXTERNAL_URL غير مضبوط — الخدمة قد تنام. "
                           "أضف متغير البيئة RENDER_EXTERNAL_URL في Render")

    # تهيئة البوت والمجدول
    await post_init(app)

    logger.info("🚀 تشغيل البوت في وضع polling...")
    try:
        await app.run_polling(
            poll_interval=3,
            drop_pending_updates=True,
            close_loop=False,
        )
    finally:
        # تنظيف الموارد عند الإغلاق
        if keepalive_task:
            keepalive_task.cancel()
            try:
                await keepalive_task
            except asyncio.CancelledError:
                pass
        if keepalive_runner:
            await keepalive_runner.cleanup()


async def run_polling():
    """وضع polling فقط — للاختبار المحلي"""
    app = build_application()
    await post_init(app)
    logger.info("🚀 تشغيل البوت في وضع polling (محلي)...")
    await app.run_polling(
        poll_interval=3,
        drop_pending_updates=True,
        close_loop=False,
    )


async def run_webhook():
    """وضع webhook — احتياطي (غير مفعّل افتراضياً)"""
    app = build_application()
    await post_init(app)

    if not config.RENDER_EXTERNAL_URL:
        logger.error("❌ RENDER_EXTERNAL_URL غير مضبوط")
        sys.exit(1)

    webhook_url = f"{config.RENDER_EXTERNAL_URL}/{config.BOT_TOKEN}"
    logger.info(f"🌐 تشغيل البوت في وضع webhook: {webhook_url}")
    await app.run_webhook(
        listen="0.0.0.0",
        port=config.PORT,
        url_path=config.BOT_TOKEN,
        webhook_url=webhook_url,
    )


def main():
    logger.info("📖 بوت الحصون الخمسة — البدء")
    logger.info(f"  - الصباح: {config.MORNING_TIME}")
    logger.info(f"  - الظهيرة: {config.MIDDAY_TIME}")
    logger.info(f"  - المساء: {config.EVENING_TIME}")
    logger.info(f"  - المنطقة الزمنية: {config.DEFAULT_TIMEZONE}")
    logger.info(f"  - keep-alive: {'مُفعّل' if config.KEEPALIVE_ENABLED else 'مُعطّل'}")

    # على Render Free نستخدم polling + keep-alive (الأبسط والأكثر موثوقية)
    # على localhost نستخدم polling فقط
    if config.RENDER_EXTERNAL_URL or config.KEEPALIVE_ENABLED:
        asyncio.run(_run_polling_with_keepalive())
    else:
        asyncio.run(run_polling())


if __name__ == "__main__":
    main()
